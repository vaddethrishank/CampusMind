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
from notice_agent import (
    classify_document,
    extract_scholar_ids,
    craft_notification,
    resolve_scholar_ids,
    get_all_students,
    dispatch_notifications,
    chunk_notice_text,
    NOTICE_ICONS,
    NOTIFY_TYPES,
)
from complaint_agent import (
    classify_complaint,
    process_complaint,
    vote_on_complaint,
    CATEGORY_ICONS,
    STATUS_LABELS,
)

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

class NoticeRequest(BaseModel):
    title: str
    content: str

class ComplaintClassifyRequest(BaseModel):
    text: str
    user_info: Optional[Dict[str, Any]] = None

class ComplaintRequest(BaseModel):
    text: str
    user_info: Optional[Dict[str, Any]] = None

class ComplaintStatusRequest(BaseModel):
    status: str   # open | in_progress | resolved | dismissed

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

        # ── AGENTIC LAYER: classify → extract → notify ─────────────────────
        agent_result = {"notified": 0, "doc_type": "general", "skipped": False}
        try:
            # Stage 1: Classify using ONLY first 300 chars of first chunk + filename
            first_excerpt = chunks[0]["content"][:300] if chunks else ""
            classification = classify_document(first_excerpt, file.filename)
            doc_type = classification.get("doc_type", "general")
            summary = classification.get("summary", file.filename)
            is_targeted = classification.get("is_targeted", False)
            agent_result["doc_type"] = doc_type

            print(f"[Agent] '{file.filename}' classified as: {doc_type} | targeted: {is_targeted}")

            if doc_type in NOTIFY_TYPES:
                # Stage 2: Regex extract scholar IDs from all chunks — zero LLM cost
                all_texts = [c["content"] for c in chunks]
                found_ids = extract_scholar_ids(all_texts)
                is_broadcast = len(found_ids) == 0

                print(f"[Agent] Scholar IDs found via regex: {found_ids or 'none (broadcast)'}") 

                # Stage 3: Single LLM call with minimal context to craft notification
                notif = craft_notification(doc_type, summary, is_broadcast)

                # Resolve users
                if is_broadcast:
                    users = get_all_students(supabase)
                else:
                    users = resolve_scholar_ids(found_ids, supabase)

                # Save notice record
                notice_insert = supabase.table("notices").insert({
                    "title":          file.filename,
                    "content":        summary,
                    "notice_type":    doc_type,
                    "source_type":    "pdf",
                    "source_file":    file.filename,
                    "scholar_ids":    found_ids,
                    "is_broadcast":   is_broadcast,
                    "notified_count": len(users),
                }).execute()
                notice_id = notice_insert.data[0]["id"]

                # Dispatch notifications
                sent = dispatch_notifications(
                    notice_id, users,
                    notif["title"], notif["message_template"],
                    supabase
                )
                agent_result["notified"] = sent
                print(f"[Agent] Notifications dispatched: {sent}")
            else:
                agent_result["skipped"] = True
                print(f"[Agent] doc_type='{doc_type}' → no notification needed")

        except Exception as agent_err:
            # Agent failure must NOT break the main upload response
            print(f"[Agent] Pipeline error (non-fatal): {agent_err}")

        return {
            "message": f"Successfully ingested '{file.filename}'!",
            "content_type_detected": detected_type,
            "chunks_created": total_uploaded,
            "agent": {
                "doc_type":         agent_result["doc_type"],
                "notifications_sent": agent_result["notified"],
                "notification_skipped": agent_result["skipped"],
            }
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


# ── Workflow B: Admin Text Notice ───────────────────────────────────────────────

@app.post("/api/admin/notices")
async def post_notice(req: NoticeRequest):
    """Admin posts a text notice. Agent extracts scholar IDs, dispatches notifications,
    and ingests notice into RAG documents table."""
    if not req.title.strip() or not req.content.strip():
        raise HTTPException(status_code=400, detail="Title and content are required.")

    try:
        # Stage 1: Single LLM call on full notice text (it's short, so this is fine)
        from notice_agent import classify_document, extract_scholar_ids, craft_notification
        classification = classify_document(req.content[:600], req.title)
        doc_type = classification.get("doc_type", "student_notice")
        summary  = classification.get("summary", req.title)

        # Stage 2: Regex extract scholar IDs from notice content
        found_ids = extract_scholar_ids([req.content])
        is_broadcast = len(found_ids) == 0

        # Stage 3: Craft notification
        notif = craft_notification(doc_type, summary, is_broadcast)

        # Resolve users
        if is_broadcast:
            users = get_all_students(supabase)
        else:
            users = resolve_scholar_ids(found_ids, supabase)

        not_found_ids = [sid for sid in found_ids if sid not in {u["scholar_id"] for u in users}]

        # Persist notice
        notice_insert = supabase.table("notices").insert({
            "title":          req.title,
            "content":        req.content,
            "notice_type":    doc_type,
            "source_type":    "text",
            "scholar_ids":    found_ids,
            "is_broadcast":   is_broadcast,
            "notified_count": len(users),
        }).execute()
        notice_id = notice_insert.data[0]["id"]

        # Dispatch in-app notifications
        sent = dispatch_notifications(
            notice_id, users,
            notif["title"], notif["message_template"],
            supabase
        )

        # ── RAG Ingestion: chunk + embed notice into documents table ──────────
        rag_chunks = chunk_notice_text(req.title, req.content, notice_id, doc_type)
        rag_texts = [c["content"] for c in rag_chunks]
        rag_embeddings = _embed_with_retry(rag_texts)
        rag_rows = [
            {"content": c["content"], "metadata": c["metadata"], "embedding": emb}
            for c, emb in zip(rag_chunks, rag_embeddings)
        ]
        supabase.table("documents").insert(rag_rows).execute()

        return {
            "message":         "Notice posted and notifications dispatched.",
            "notice_id":       notice_id,
            "notice_type":     doc_type,
            "icon":            NOTICE_ICONS.get(doc_type, "📄"),
            "is_broadcast":    is_broadcast,
            "students_notified": sent,
            "scholar_ids_found": found_ids,
            "scholar_ids_not_found": not_found_ids,
            "rag_chunks_indexed": len(rag_rows),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Notice pipeline failed: {str(e)}")


@app.get("/api/admin/notices-list")
async def list_notices():
    """Return all notices for the admin panel."""
    try:
        res = supabase.table("notices").select("*").order("created_at", desc=True).limit(50).execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── User Notification Endpoints ────────────────────────────────────────────────

@app.get("/api/notifications")
async def get_notifications(user_id: str):
    """Fetch all notifications for a specific user (newest first)."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        res = (
            supabase.table("user_notifications")
            .select("id, notice_id, notification_title, notification_message, is_read, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        # Enrich with notice type for icon display
        notifications = res.data or []
        if notifications:
            notice_ids = list({n["notice_id"] for n in notifications if n["notice_id"]})
            notice_res = supabase.table("notices").select("id, notice_type").in_("id", notice_ids).execute()
            type_map = {n["id"]: n["notice_type"] for n in (notice_res.data or [])}
            for notif in notifications:
                ntype = type_map.get(notif["notice_id"], "general")
                notif["notice_type"] = ntype
                notif["icon"] = NOTICE_ICONS.get(ntype, "📄")
        return notifications
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str):
    """Mark a single notification as read."""
    try:
        supabase.table("user_notifications").update({"is_read": True}).eq("id", notif_id).execute()
        return {"message": "Notification marked as read."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/notifications/read-all")
async def mark_all_notifications_read(user_id: str):
    """Mark all notifications as read for a user."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        supabase.table("user_notifications").update({"is_read": True}).eq("user_id", user_id).eq("is_read", False).execute()
        return {"message": "All notifications marked as read."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ── Complaint Management Endpoints ─────────────────────────────────────────────

@app.post("/api/complaint/classify")
async def complaint_classify(req: ComplaintClassifyRequest):
    """
    Fast classification-only endpoint — used fire-and-forget from the frontend
    in parallel with /api/chat.  No DB writes, no enrichment.
    Returns {is_complaint, category, title, confidence} within ~300ms.
    """
    try:
        result = classify_complaint(req.text)
        return result
    except Exception as e:
        # Never propagate errors — frontend ignores failures silently
        return {"is_complaint": False, "category": "not_complaint", "title": "", "confidence": 0.0}


@app.post("/api/complaint")
async def submit_complaint(req: ComplaintRequest):
    """
    Full complaint submission: classify → similar → hostel enrich → save.
    Only fires when user explicitly clicks 'Submit Complaint'.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Complaint text is required.")
    if not req.user_info or not req.user_info.get("id"):
        raise HTTPException(status_code=401, detail="You must be logged in to submit a complaint.")
    try:
        result = process_complaint(
            text=req.text,
            user_info=req.user_info,
            supabase=supabase,
        )
        if result.get("error") == "not_a_complaint":
            raise HTTPException(status_code=400, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Complaint submission failed: {str(e)}")


@app.post("/api/complaint/{complaint_id}/vote")
async def vote_complaint(complaint_id: str, req: ComplaintClassifyRequest):
    """
    Student agrees with / has the same issue as an existing complaint.
    Increments vote_count, records in complaint_votes for deduplication.
    """
    if not req.user_info or not req.user_info.get("id"):
        raise HTTPException(status_code=401, detail="You must be logged in to vote.")
    try:
        result = vote_on_complaint(complaint_id, req.user_info, supabase)
        if result.get("error") == "already_voted":
            raise HTTPException(status_code=409, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vote failed: {str(e)}")


@app.get("/api/my-complaints")
async def get_my_complaints(user_id: str):
    """Return all complaints submitted by a specific student, newest first."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        res = (
            supabase.table("complaints")
            .select("id, title, description, category, status, vote_count, hostel_details, created_at, updated_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        complaints = res.data or []
        for c in complaints:
            cat  = c.get("category", "general")
            stat = c.get("status", "open")
            c["category_icon"] = CATEGORY_ICONS.get(cat, "📢")
            c["status_icon"]   = STATUS_LABELS.get(stat, ("🔴", "Open"))[0]
            c["status_label"]  = STATUS_LABELS.get(stat, ("🔴", "Open"))[1]
        return complaints
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/complaints")
async def list_complaints(
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
):
    """
    Admin endpoint: all complaints, filterable by status and category.
    Returns complaints with enriched icon labels.
    """
    try:
        query = (
            supabase.table("complaints")
            .select("id, user_id, scholar_id, student_name, title, description, "
                    "category, status, hostel_details, vote_count, created_at, updated_at")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if status:
            query = query.eq("status", status)
        if category:
            query = query.eq("category", category)

        res = query.execute()
        complaints = res.data or []

        # Enrich each complaint with icon/label metadata
        for c in complaints:
            cat  = c.get("category", "general")
            stat = c.get("status", "open")
            c["category_icon"]  = CATEGORY_ICONS.get(cat, "📢")
            c["status_icon"]    = STATUS_LABELS.get(stat, ("🔴", "Open"))[0]
            c["status_label"]   = STATUS_LABELS.get(stat, ("🔴", "Open"))[1]

        return complaints
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/admin/complaints/{complaint_id}/status")
async def update_complaint_status(complaint_id: str, req: ComplaintStatusRequest):
    """
    Admin action: update a complaint's status.
    Valid values: open | in_progress | resolved | dismissed
    """
    valid = {"open", "in_progress", "resolved", "dismissed"}
    if req.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid)}")
    try:
        res = (
            supabase.table("complaints")
            .update({"status": req.status, "updated_at": "now()"})
            .eq("id", complaint_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="Complaint not found.")
        return {"message": f"Status updated to '{req.status}'.", "complaint": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

