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
    """Query Supabase hybrid_search, then filter by score and deduplicate."""
    try:
        query_embedding = get_gemini_embedding(query)
        params = {
            "query_text": query,
            "query_embedding": query_embedding,
            "match_count": 12,          # Retrieve 12 candidates
            "filter": metadata_filter or {}
        }
        res = supabase.rpc("hybrid_search", params).execute()
        candidates = res.data or []

        # ── 1. Score filtering: drop chunks below relevance threshold ──────────
        MIN_SCORE = 0.005
        scored = [c for c in candidates if (c.get("similarity") or 0) >= MIN_SCORE]

        # ── 2. Deduplication: skip near-identical overlapping chunks ───────────
        seen_fingerprints: list[str] = []
        unique: list[Dict[str, Any]] = []
        for chunk in scored:
            fingerprint = chunk["content"][:200].strip()
            # Check if this chunk is >85% similar to any already-selected chunk
            is_duplicate = any(
                len(set(fingerprint) & set(fp)) / max(len(set(fingerprint)), len(set(fp)), 1) > 0.85
                for fp in seen_fingerprints
            )
            if not is_duplicate:
                seen_fingerprints.append(fingerprint)
                unique.append(chunk)

        # ── 3. Cap at top-6 highest-score unique chunks ────────────────────────
        top_chunks = unique[:6]
        print(f"[RAG] Retrieved {len(candidates)} candidates → {len(scored)} above threshold → {len(unique)} unique → {len(top_chunks)} sent to LLM")
        return top_chunks

    except Exception as e:
        print(f"[RAG] Retrieval error: {e}")
        return []

def fetch_personal_record(scholar_id: str) -> Optional[Dict[str, Any]]:
    """Directly fetch a student's own result record by registration number (scholar_id).
    This bypasses vector search entirely — a 100% reliable metadata lookup."""
    try:
        res = supabase.table("documents") \
            .select("content, metadata") \
            .eq("metadata->>regn_no", scholar_id) \
            .limit(1) \
            .execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"[RAG] Personal record lookup error: {e}")
    return None

# Keywords that indicate a query is about the user's own academic record
PERSONAL_RESULT_KEYWORDS = [
    "my result", "my marks", "my sgpa", "my cgpa", "my grade", "my score",
    "my semester", "my performance", "my subject", "how did i", "did i pass",
    "my gpa", "my points", "my transcript", "my academic"
]

def is_personal_result_query(query: str) -> bool:
    """Detect if the query is asking about the logged-in student's own results."""
    q = query.lower()
    return any(kw in q for kw in PERSONAL_RESULT_KEYWORDS)

def get_answer(query: str, metadata_filter: Optional[Dict[str, Any]] = None, user_info: Optional[Dict[str, Any]] = None, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Run the RAG pipeline with smart retrieval and structured context."""

    scholar_id = user_info.get("scholar_id") if user_info else None
    personal_context = ""

    # ── Pinned personal record: direct metadata lookup by scholar_id ──────────
    # This runs for every result-related query — no vector search needed for the
    # student's own record. scholar_id in the profile = regn_no in the PDF.
    if scholar_id and is_personal_result_query(query):
        record = fetch_personal_record(scholar_id)
        if record:
            personal_context = (
                f"\n\n[STUDENT'S OWN ACADEMIC RECORD — Directly retrieved by Registration Number]\n"
                f"{record['content']}\n"
            )
            print(f"[RAG] Personal record found for scholar_id={scholar_id}")
        else:
            print(f"[RAG] No personal record found for scholar_id={scholar_id}")

    # 1. Retrieve best matching chunks via hybrid vector search
    context_items = retrieve_context(query, metadata_filter)
    
    # 2. Build structured context with source labels for each chunk
    if context_items:
        context_parts = []
        for item in context_items:
            source = item.get("metadata", {}).get("source", "unknown")
            # Only keep the filename, strip any path prefix
            source_name = source.split("/")[-1].split("\\")[-1]
            context_parts.append(f"[Source: {source_name}]\n{item['content'].strip()}")
        context_text = "\n\n---\n\n".join(context_parts)
    else:
        context_text = "(No relevant documents found for this query.)"

    # 3. Format active user context
    user_context = ""
    if user_info:
        user_context = (
            f"\nActive Logged-In Student:\n"
            f"- Name: {user_info.get('name')}\n"
            f"- Scholar ID: {user_info.get('scholar_id')}\n"
            f"- Email: {user_info.get('email')}\n"
            f"- Username: {user_info.get('username')}\n"
        )
    
    # 4. Build system prompt
    system_instruction = f"""You are CampusMind, a helpful and friendly AI assistant for the institution's students.
{personal_context}
You have access to the following institutional document excerpts to answer student queries:

{context_text}
{user_context}

Rules you must follow:
1. Answer directly and conversationally — never say phrases like "based on the context" or "the document says". Speak as if you already know the information.
2. When the answer is found in a specific document, you may naturally mention the source (e.g., "According to the hostel allotment list..." or "The internship advertisement states...").
3. If the user asks about their own results, marks, SGPA, CGPA, or grades — use the [STUDENT'S OWN ACADEMIC RECORD] section above (if present). That record belongs specifically to this student.
4. If the user asks about their own personal details (name, scholar ID, email), use the Active Logged-In Student info above.
5. If the information is NOT present in the document excerpts provided, honestly say: "I don't have that specific information right now. Please check with the administration or the relevant department."
6. For casual greetings (hi, hello, hey), respond warmly and ask how you can help.
7. Keep responses clear, concise, and helpful. Use bullet points or numbered lists when listing multiple items.
"""
    
    # 5. Generate answer via Groq
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
            temperature=0.2,
            max_tokens=1024
        )
        answer = chat_completion.choices[0].message.content
    except Exception as e:
        print(f"[RAG] Generation error: {e}")
        answer = "Sorry, I encountered an error generating the response. Please try again."

    return {
        "answer": answer,
        "context": [item["content"] for item in context_items],
        "metadata": [item["metadata"] for item in context_items]
    }

