import os
import requests
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from supabase.client import Client, create_client
from groq import Groq


load_dotenv(dotenv_path="../.env")

# Supabase setup
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Groq setup
groq_api_key = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key)

def get_gemini_embedding(text: str) -> List[float]:
    """Call Google Gemini Embeddings API directly to fetch 3072-dim vector."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={api_key}"
    payload = {
        "model": "models/gemini-embedding-2",
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": 3072
    }
    response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
    response.raise_for_status()
    data = response.json()
    return data["embedding"]["values"]

def retrieve_context(query: str, metadata_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Query Supabase documents table using match_documents RPC."""
    try:
        query_embedding = get_gemini_embedding(query)
        params = {
            "query_embedding": query_embedding,
            "match_count": 3,
            "filter": metadata_filter or {}
        }
        res = supabase.rpc("match_documents", params).execute()
        return res.data or []
    except Exception as e:
        print(f"[RAG] Retrieval error: {e}")
        return []

def get_answer(query: str, metadata_filter: Optional[Dict[str, Any]] = None, user_info: Optional[Dict[str, Any]] = None, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Run the simplified RAG pipeline without LangChain dependencies."""

    # 1. Retrieve matching documents from Supabase vector store
    context_items = retrieve_context(query, metadata_filter)
    
    # 2. Build the context snippet list
    context_text = "\n\n".join(item["content"] for item in context_items)

    # Format active user context if available
    user_context = ""
    if user_info:
        user_context = (
            f"\nActive Logged-In Student Information:\n"
            f"- Name: {user_info.get('name')}\n"
            f"- Scholar ID: {user_info.get('scholar_id')}\n"
            f"- Email: {user_info.get('email')}\n"
            f"- Username: {user_info.get('username')}\n"
        )
    
    # 3. Create the prompt structure
    system_instruction = f"""You are CampusMind, a helpful and friendly AI assistant for the institution's students.
Your goal is to answer student queries naturally, clearly, and concisely.

Information you know:
{context_text}
{user_context}

Guidelines:
1. Use the information above to answer the student's questions. 
2. Speak directly to the student in a conversational, friendly, and professional tone. Do NOT use phrases like "based on the retrieved context," "according to the provided documents," or "the text says." State the answer directly as if you just know it.
3. If the user asks for their personal details (e.g., "what is my scholar id", "what is my name"), answer using the Active Logged-In Student Information provided above.
4. If the information needed to answer the institutional question is not in the provided information, simply say: "I'm sorry, I don't have that information right now." Do not make up or guess answers.
5. If the user's message is a casual greeting (like "hi", "hello", "hey"), respond naturally with a friendly greeting and ask how you can help them today.
6. For queries completely unrelated to the institution, academics, or student life (like general programming, writing code, or general knowledge), politely decline by saying: "Sorry, I am specifically designed to answer queries related to our institution and student life."
"""
    
    # 4. Generate answer using Groq Chat Completions API
    try:
        messages = [{"role": "system", "content": system_instruction}]
        
        if chat_history:
            for msg in chat_history:
                role = "assistant" if msg["role"] == "bot" else "user"
                messages.append({"role": role, "content": msg["content"]})
                
        messages.append({"role": "user", "content": query})

        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            temperature=0.3
        )
        answer = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"[RAG] Generation error: {e}")
        answer = "Sorry, I encountered an error generating the response."

    return {
        "answer": answer,
        "context": [item["content"] for item in context_items],
        "metadata": [item["metadata"] for item in context_items]
    }

