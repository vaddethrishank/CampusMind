"""
notice_agent.py — Agentic Notice Processing Pipeline

3-Stage funnel to classify documents and dispatch targeted notifications
with minimal LLM token usage:

  Stage 1: CLASSIFY  — LLM sees only first 300 chars + filename (~120 tokens)
  Stage 2: EXTRACT   — Pure regex, zero LLM cost
  Stage 3: CRAFT     — LLM sees only doc_type + 1-sentence summary (~80 tokens)
"""

import re
import os
import json
from typing import Optional
from groq import Groq
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Document types that should trigger the notification pipeline
NOTIFY_TYPES = {
    "holiday",
    "exam_notice",
    "fee_notice",
    "student_notice",
    "scholarship",
    "internship",
    "event_notice",
}

# Emoji icons per notice type for the frontend
NOTICE_ICONS = {
    "holiday":        "🏖️",
    "exam_notice":    "📝",
    "fee_notice":     "💰",
    "student_notice": "📢",
    "scholarship":    "🎓",
    "internship":     "💼",
    "event_notice":   "📅",
    "general":        "📄",
}


# ── Stage 1: Classify (cheap — first 300 chars only) ──────────────────────────

def classify_document(first_chunk_text: str, filename: str) -> dict:
    """
    Classify a document using only the first ~300 characters of its first chunk
    plus the filename. Sends approximately 120 tokens to the LLM.

    Returns:
        {
            "doc_type": str,       # see NOTIFY_TYPES or "general"
            "is_targeted": bool,   # True if notice mentions specific students
            "summary": str         # one sentence describing the document
        }
    """
    # Truncate to first 300 chars to keep tokens minimal
    excerpt = first_chunk_text[:300].strip()

    prompt = f"""You are a document classifier for a university system.
Classify the following document excerpt and filename.

Filename: {filename}
Excerpt (first 300 characters):
\"\"\"
{excerpt}
\"\"\"

Respond with a single JSON object only (no markdown, no explanation):
{{
  "doc_type": "<one of: holiday | exam_notice | fee_notice | student_notice | scholarship | internship | event_notice | general>",
  "is_targeted": <true if the notice appears to target specific named/ID'd students, false otherwise>,
  "summary": "<one sentence describing what this document is about>"
}}

Rules:
- "holiday" = holiday list, institute holiday calendar, public holiday notice
- "exam_notice" = examination schedule, hall ticket, supplementary exam, result notice
- "fee_notice" = fee payment reminder, scholarship disbursement, fine notice
- "student_notice" = any circular/notice directed at specific students by name/ID
- "scholarship" = scholarship selection, merit list
- "internship" = internship offer, placement notice
- "event_notice" = fest, workshop, seminar, cultural event
- "general" = syllabus, notes, handbook, timetable, any non-notice academic document
- is_targeted = true ONLY when you see or expect specific registration numbers / roll numbers / names of individual students"""

    try:
        resp = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=120,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip possible markdown fences
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[NoticeAgent] classify_document error: {e}")
        return {"doc_type": "general", "is_targeted": False, "summary": filename}


# ── Stage 2: Extract scholar IDs (pure regex — zero LLM cost) ─────────────────

def extract_scholar_ids(chunk_texts: list[str]) -> list[str]:
    """
    Scan all chunk texts for 7-digit scholar/registration IDs using regex.
    No LLM involved — pure string matching.

    Returns a deduplicated list of 7-digit ID strings.
    """
    scholar_id_pattern = re.compile(r'\b\d{7}\b')
    found: set[str] = set()
    for text in chunk_texts:
        found.update(scholar_id_pattern.findall(text))
    return sorted(found)


# ── Stage 3: Craft notification (minimal context — ~80 tokens) ────────────────

def craft_notification(doc_type: str, summary: str, is_broadcast: bool) -> dict:
    """
    Generate a notification title and message template using minimal context.
    The {name} placeholder in message_template is replaced per-student at dispatch time.

    Returns:
        {
            "title": str,
            "message_template": str   # may contain {name} placeholder
        }
    """
    audience = "all students" if is_broadcast else "specific students"
    prompt = f"""You are writing a brief in-app notification for a university student portal.

Document type: {doc_type}
Summary: {summary}
Audience: {audience}

Write a short notification. Respond with JSON only:
{{
  "title": "<short notification title, max 60 chars>",
  "message_template": "<notification body, max 120 chars, use {{name}} placeholder for student name if targeted>"
}}

Keep it friendly, clear, and actionable. No markdown."""

    try:
        resp = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=100,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[NoticeAgent] craft_notification error: {e}")
        # Fallback notification
        return {
            "title": "New Notice Posted",
            "message_template": f"A new {doc_type.replace('_', ' ')} has been posted. Please check the admin portal.",
        }


# ── Resolve scholar IDs → profile rows ───────────────────────────────────────

def resolve_scholar_ids(scholar_ids: list[str], supabase) -> list[dict]:
    """
    Look up profiles for each scholar ID in a single batched query.
    Returns list of { id, name, scholar_id } dicts for matched students.
    """
    if not scholar_ids:
        return []
    try:
        res = (
            supabase.table("profiles")
            .select("id, name, scholar_id")
            .in_("scholar_id", scholar_ids)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[NoticeAgent] resolve_scholar_ids error: {e}")
        return []


def get_all_students(supabase) -> list[dict]:
    """Fetch all registered student profiles (for broadcast notifications)."""
    try:
        res = supabase.table("profiles").select("id, name, scholar_id").execute()
        return res.data or []
    except Exception as e:
        print(f"[NoticeAgent] get_all_students error: {e}")
        return []


# ── Dispatch: insert user_notifications rows ─────────────────────────────────

def dispatch_notifications(
    notice_id: str,
    users: list[dict],
    title: str,
    message_template: str,
    supabase,
) -> int:
    """
    Bulk-insert one user_notifications row per user.
    Substitutes {name} in message_template for each student.

    Returns number of notifications inserted.
    """
    if not users:
        return 0

    rows = []
    for user in users:
        name = user.get("name") or "Student"
        message = message_template.replace("{name}", name)
        rows.append({
            "notice_id":            notice_id,
            "user_id":              user["id"],
            "scholar_id":           user.get("scholar_id"),
            "notification_title":   title,
            "notification_message": message,
            "is_read":              False,
        })

    try:
        # Insert in batches of 50 to avoid payload limits
        BATCH = 50
        for i in range(0, len(rows), BATCH):
            supabase.table("user_notifications").insert(rows[i : i + BATCH]).execute()
        print(f"[NoticeAgent] Dispatched {len(rows)} notifications for notice {notice_id}")
        return len(rows)
    except Exception as e:
        print(f"[NoticeAgent] dispatch_notifications error: {e}")
        return 0


# ── Text-notice chunker (for Workflow B RAG ingestion) ───────────────────────

def chunk_notice_text(title: str, content: str, notice_id: str, notice_type: str) -> list[dict]:
    """
    Split a text notice into RAG-ingestible chunks (same format as pdf_processor).
    For short notices this is usually a single chunk.
    """
    MAX_CHARS = 800
    full_text = f"{title}\n\n{content}"
    chunks = []
    for i in range(0, len(full_text), MAX_CHARS):
        chunk_text = full_text[i : i + MAX_CHARS]
        chunks.append({
            "content": chunk_text,
            "metadata": {
                "source": "notices",
                "notice_id": notice_id,
                "notice_type": notice_type,
                "title": title,
                "content_type": "notice",
            },
        })
    return chunks
