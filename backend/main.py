from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Any, Dict, Optional, List
import uvicorn
import re
import os
import time
import shutil
from pathlib import Path
from supabase.client import create_client
from rag import get_answer, supabase, supabase_url
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pdf_processor import process_pdf

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str
    metadata_filter: Optional[Dict[str, Any]] = None
    user_info: Optional[Dict[str, Any]] = None
    chat_id: Optional[str] = None

# Auth request schemas
class SignUpRequest(BaseModel):
    name: str
    email: str
    username: str
    scholar_id: str
    password: str

class LoginRequest(BaseModel):
    identifier: str
    password: str

class ForgotPasswordRequest(BaseModel):
    identifier: str

class ResetPasswordRequest(BaseModel):
    access_token: str
    password: str

@app.post("/api/chat")
async def chat(request: QueryRequest):
    chat_id = request.chat_id
    user_id = request.user_info.get("id") if request.user_info else None
    
    if not user_id:
        # Fallback to no history if unauthenticated
        result = get_answer(request.query, metadata_filter=request.metadata_filter, user_info=request.user_info)
        return result

    # If no chat_id, create a new chat
    if not chat_id:
        title = request.query[:50] + "..." if len(request.query) > 50 else request.query
        chat_res = supabase.table("chats").insert({"user_id": user_id, "title": title}).execute()
        chat_id = chat_res.data[0]["id"]
        chat_title = title
    else:
        # Get chat title
        chat_res = supabase.table("chats").select("title").eq("id", chat_id).execute()
        chat_title = chat_res.data[0]["title"] if chat_res.data else "Chat"

    # Save user message
    supabase.table("messages").insert({
        "chat_id": chat_id,
        "role": "user",
        "content": request.query
    }).execute()

    # Fetch last 6 messages for context (excluding the one just inserted? Wait, I will include it)
    # Actually, we shouldn't send the current query twice. Let's fetch history BEFORE inserting the current message,
    # OR fetch last 7 and exclude the last one.
    # It's cleaner to just fetch history BEFORE saving user message.
    msg_res = supabase.table("messages").select("role, content").eq("chat_id", chat_id).order("created_at", desc=True).limit(6).execute()
    
    # We just saved the user message, so msg_res.data[0] is the current message.
    # The history we pass to RAG should be everything BEFORE the current message.
    history_messages = msg_res.data[1:] if msg_res.data else []
    chat_history = history_messages[::-1]

    # Get answer
    result = get_answer(request.query, metadata_filter=request.metadata_filter, user_info=request.user_info, chat_history=chat_history)
    
    # Save bot message
    supabase.table("messages").insert({
        "chat_id": chat_id,
        "role": "bot",
        "content": result["answer"]
    }).execute()

    result["chat_id"] = chat_id
    result["title"] = chat_title
    return result

@app.get("/api/chats")
async def get_chats(user_id: str):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    try:
        res = supabase.table("chats").select("id, title, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    try:
        supabase.table("chats").delete().eq("id", chat_id).execute()
        return {"message": "Chat deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chats/{chat_id}/messages")
async def get_messages(chat_id: str):
    try:
        res = supabase.table("messages").select("id, role, content, created_at").eq("chat_id", chat_id).order("created_at", desc=False).execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/signup")
async def signup(req: SignUpRequest):
    # Validate scholar_id: exactly 7 digits
    if not re.match(r"^\d{7}$", req.scholar_id):
        raise HTTPException(status_code=400, detail="Scholar ID must be exactly 7 digits.")
    
    # Simple email check
    if not re.match(r"[^@]+@[^@]+\.[^@]+", req.email):
        raise HTTPException(status_code=400, detail="Invalid email format.")

    try:
        res = supabase.auth.sign_up({
            "email": req.email,
            "password": req.password,
            "options": {
                "data": {
                    "name": req.name,
                    "username": req.username,
                    "scholar_id": req.scholar_id
                }
            }
        })
        if not res.user:
            raise HTTPException(status_code=400, detail="Signup failed.")
        return {"message": "Sign up successful! Please check your email for confirmation."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    email = req.identifier
    # Resolve username to email if it doesn't contain "@"
    if "@" not in req.identifier:
        try:
            profile_res = supabase.table("profiles").select("email").eq("username", req.identifier).execute()
            if not profile_res.data or len(profile_res.data) == 0:
                raise HTTPException(status_code=400, detail="Username not found.")
            email = profile_res.data[0]["email"]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Username resolution failed: {str(e)}")

    try:
        res = supabase.auth.sign_in_with_password({
            "email": email,
            "password": req.password
        })
        
        # Fetch public profile
        profile_res = supabase.table("profiles").select("*").eq("id", res.user.id).execute()
        profile = profile_res.data[0] if profile_res.data else {}

        return {
            "session": {
                "access_token": res.session.access_token,
                "refresh_token": res.session.refresh_token,
                "expires_at": res.session.expires_at
            },
            "user": {
                "id": res.user.id,
                "email": res.user.email,
                "name": profile.get("name"),
                "username": profile.get("username"),
                "scholar_id": profile.get("scholar_id")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    email = req.identifier
    if "@" not in req.identifier:
        try:
            profile_res = supabase.table("profiles").select("email").eq("username", req.identifier).execute()
            if not profile_res.data or len(profile_res.data) == 0:
                raise HTTPException(status_code=400, detail="Username not found.")
            email = profile_res.data[0]["email"]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Username resolution failed: {str(e)}")

    try:
        supabase.auth.reset_password_for_email(email, {
            "redirect_to": "http://localhost:3000"
        })
        return {"message": "Password reset email sent. Please check your inbox."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    try:
        # Create user client using the user's access token to authorize the update
        user_client = create_client(supabase_url, req.access_token)
        user_client.auth.update_user({"password": req.password})
        return {"message": "Password has been reset successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── Admin Document Ingestion Pipeline ──────────────────────────────────────────
gemini_embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-2")

def _embed_with_retry(texts: List[str], max_retries: int = 5) -> List[List[float]]:
    """Embed texts with exponential backoff on Gemini rate-limit errors."""
    for attempt in range(max_retries):
        try:
            return gemini_embeddings.embed_documents(texts)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 15 * (2 ** attempt)
                print(f"[Upload] Rate limit hit, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Embedding failed after max retries.")

@app.post("/api/admin/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents are supported.")
    
    pdf_dir = Path("../data/pdfs")
    pdf_dir.mkdir(parents=True, exist_ok=True)
    file_path = pdf_dir / file.filename

    # Save uploaded file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    try:
        # ── Smart processing: auto-detects text vs tabular PDF ────────────────
        chunks = process_pdf(str(file_path), source_name=file.filename)

        if not chunks:
            raise HTTPException(status_code=400, detail="No readable content extracted from PDF.")

        # ── Embed & upload in rate-limit-safe batches ─────────────────────────
        BATCH_SIZE = 10
        SLEEP_SECS = 7
        total_uploaded = 0
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            texts = [c["content"] for c in batch]
            embeddings = _embed_with_retry(texts)
            rows = [
                {"content": c["content"], "metadata": c["metadata"], "embedding": emb}
                for c, emb in zip(batch, embeddings)
            ]
            supabase.table("documents").insert(rows).execute()
            total_uploaded += len(rows)
            if i + BATCH_SIZE < len(chunks):
                time.sleep(SLEEP_SECS)

        # Determine content type detected for the response
        detected_type = chunks[0]["metadata"].get("content_type", "text") if chunks else "text"

        return {
            "message": f"Successfully ingested '{file.filename}'!",
            "content_type_detected": detected_type,
            "chunks_created": total_uploaded
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@app.get("/api/admin/documents")
async def list_documents():
    try:
        res = supabase.table("documents").select("metadata").execute()
        docs = {}
        for row in (res.data or []):
            meta = row.get("metadata") or {}
            src = meta.get("source")
            if src:
                filename = Path(src).name
                docs[filename] = docs.get(filename, 0) + 1
        
        doc_list = [{"filename": k, "chunks": v} for k, v in sorted(docs.items())]
        return doc_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/documents/{filename}")
async def delete_document(filename: str):
    try:
        supabase.table("documents").delete().like("metadata->>source", f"%{filename}").execute()

        file_path = Path("../data/pdfs") / filename
        if file_path.exists():
            file_path.unlink()

        return {"message": f"Deleted document '{filename}' successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

