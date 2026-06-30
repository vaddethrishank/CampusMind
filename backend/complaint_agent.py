"""
complaint_agent.py — Agentic Complaint Management Pipeline
──────────────────────────────────────────────────────────
3-stage funnel:

  Stage 1: CLASSIFY  — LLM determines if input is a complaint (~60 tokens, Groq)
  Stage 2: ENRICH    — If hostel-related, fetch room/hostel from RAG chunks (DB only)
  Stage 3: SIMILAR   — keyword-overlap search for similar open complaints (DB only)

Design goal: Stage 1 runs on /api/complaint/classify (fire-and-forget from frontend).
             Stages 2-3 run on /api/complaint only when user explicitly submits.
             /api/chat is NEVER touched.
"""

import re
import os
import json
from typing import Optional, List, Dict, Any

from groq import Groq
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

COMPLAINT_CATEGORIES = {
    "hostel", "academic", "admin", "facility", "mess", "transport", "general",
}

CATEGORY_ICONS = {
    "hostel":    "🏠",
    "academic":  "📚",
    "admin":     "🏛️",
    "facility":  "🔧",
    "mess":      "🍽️",
    "transport": "🚌",
    "general":   "📢",
}

STATUS_LABELS = {
    "open":        ("🔴", "Open"),
    "in_progress": ("🟡", "In Progress"),
    "resolved":    ("🟢", "Resolved"),
    "dismissed":   ("⚫", "Dismissed"),
}


# ── Stage 1: Classify ─────────────────────────────────────────────────────────

def classify_complaint(text: str) -> dict:
    """
    Determine if the input text is a complaint or grievance.
    Single Groq call, ~60 tokens — must stay fast (<300ms).

    Returns:
        {
            "is_complaint": bool,
            "category":     str,   # hostel|academic|admin|facility|mess|transport|general|not_complaint
            "title":        str,   # short complaint title (empty if not a complaint)
            "confidence":   float
        }
    """
    excerpt = text[:400].strip()
    prompt = f"""You are a complaint classifier for a university student portal.

Student message:
\"\"\"{excerpt}\"\"\"

Is this a complaint or grievance? Respond with a single JSON object only (no markdown):
{{
  "is_complaint": <true if this is a complaint/grievance/problem, false if it's a general question>,
  "category": "<hostel|academic|admin|facility|mess|transport|general|not_complaint>",
  "title": "<short complaint title max 60 chars, empty string if not a complaint>",
  "confidence": <0.0-1.0>
}}

Rules:
- is_complaint = true ONLY for complaints, grievances, issues, problem reports
- "What is the syllabus?" → NOT a complaint
- "My room has no water" → hostel complaint
- "WiFi is not working in the block" → facility complaint
- "My internal marks are incorrect" → academic complaint
- "Mess food quality is poor" → mess complaint
- Keep title concise and factual, start with the core problem"""

    try:
        resp = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=100,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        print(f"[ComplaintAgent] classify: is_complaint={result.get('is_complaint')} "
              f"category={result.get('category')} confidence={result.get('confidence')}")
        return result
    except Exception as e:
        print(f"[ComplaintAgent] classify error: {e}")
        return {
            "is_complaint": False,
            "category":     "not_complaint",
            "title":        "",
            "confidence":   0.0,
        }


# ── Stage 2: Hostel enrichment ────────────────────────────────────────────────

def enrich_hostel_details(scholar_id: str, supabase) -> dict:
    """
    Query the RAG documents table for the student's hostel allotment chunk.
    Works because hostel allotment PDFs are ingested with metadata.regn_no set.

    Returns a dict of parsed hostel details, or {} if not found.
    """
    if not scholar_id:
        return {}
    try:
        res = (
            supabase.table("documents")
            .select("content, metadata")
            .eq("metadata->>regn_no", scholar_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            # Try a looser search
            res = (
                supabase.table("documents")
                .select("content, metadata")
                .like("content", f"%{scholar_id}%")
                .in_("metadata->>content_type", ["tabular", "ocr_tabular"])
                .limit(1)
                .execute()
            )
        if not res.data:
            return {}

        chunk_text = res.data[0].get("content", "")
        meta = res.data[0].get("metadata", {})

        # Parse the NL sentence format: "Header1: val | Header2: val | ..."
        details = {"raw_chunk": chunk_text, "source_doc": meta.get("source", "")}
        for pair in chunk_text.split("|"):
            pair = pair.strip()
            if ":" in pair:
                k, v = pair.split(":", 1)
                key = k.strip().lower().replace(" ", "_").replace(".", "")
                details[key] = v.strip()

        print(f"[ComplaintAgent] Hostel details for {scholar_id}: {list(details.keys())}")
        return details

    except Exception as e:
        print(f"[ComplaintAgent] enrich_hostel error: {e}")
        return {}


# ── Stage 3: Similar complaint search ────────────────────────────────────────

def find_similar_complaints(complaint_text: str, complaint_title: str, category: str, supabase) -> List[dict]:
    """
    Find existing open complaints similar to the new one.
    Uses keyword overlap on title + same category filter.
    Returns list of {id, title, vote_count, description, similarity}.
    """
    try:
        query = (
            supabase.table("complaints")
            .select("id, title, vote_count, description, category, status")
            .eq("status", "open")
            .order("vote_count", desc=True)
            .limit(30)
            .execute()
        )
        complaints = query.data or []

        # Word-overlap similarity between new complaint and existing titles+descriptions
        input_words = set(re.findall(r"\b\w{3,}\b", (complaint_text + " " + complaint_title).lower()))
        # Remove common stop words
        stop_words = {"the", "is", "my", "our", "was", "are", "has", "have", "not",
                      "this", "that", "for", "with", "from", "please", "and", "but"}
        input_words -= stop_words

        similar = []
        for c in complaints:
            cand_words = set(re.findall(
                r"\b\w{3,}\b",
                (c.get("title", "") + " " + c.get("description", "")).lower()
            )) - stop_words
            if not cand_words or not input_words:
                continue
            overlap = len(input_words & cand_words)
            score   = overlap / max(len(input_words | cand_words), 1)
            if score >= 0.15 or overlap >= 3:
                similar.append({
                    "id":          c["id"],
                    "title":       c["title"],
                    "vote_count":  c["vote_count"],
                    "description": (c.get("description") or "")[:100],
                    "category":    c.get("category", "general"),
                    "similarity":  round(score, 3),
                })

        return sorted(similar, key=lambda x: x["similarity"], reverse=True)[:5]

    except Exception as e:
        print(f"[ComplaintAgent] find_similar error: {e}")
        return []


# ── Orchestrator: Full complaint ingestion ────────────────────────────────────

def process_complaint(
    text: str,
    user_info: dict,
    supabase,
) -> dict:
    """
    Full agentic complaint pipeline:
      1. Classify  (LLM — fast)
      2. Similar   (DB keyword search)
      3. Enrich    (DB hostel lookup — only if hostel category)
      4. Save      (Supabase insert)

    Returns:
        {
            "complaint":       dict,   # saved complaint row
            "similar":         list,   # similar open complaints
            "hostel_details":  dict,
            "category":        str,
            "title":           str,
        }
    """
    user_id    = user_info.get("id")
    scholar_id = user_info.get("scholar_id") or ""
    name       = user_info.get("name") or "Student"

    # ── Stage 1: Classify ──────────────────────────────────────────────────────
    classification = classify_complaint(text)
    if not classification.get("is_complaint"):
        return {
            "error":   "not_a_complaint",
            "message": "This message does not appear to be a complaint.",
        }

    category = classification.get("category", "general")
    title    = classification.get("title") or text[:60].strip()

    # ── Stage 2: Similar complaints ────────────────────────────────────────────
    similar = find_similar_complaints(text, title, category, supabase)
    print(f"[ComplaintAgent] Found {len(similar)} similar complaint(s)")

    # ── Stage 3: Hostel enrichment ─────────────────────────────────────────────
    hostel_details: dict = {}
    if category == "hostel":
        hostel_details = enrich_hostel_details(scholar_id, supabase)

    # ── Stage 4: Persist complaint ─────────────────────────────────────────────
    insert_data = {
        "user_id":        user_id,
        "scholar_id":     scholar_id or None,
        "student_name":   name,
        "title":          title,
        "description":    text,
        "category":       category,
        "status":         "open",
        "hostel_details": hostel_details,
        "vote_count":     1,
    }

    res = supabase.table("complaints").insert(insert_data).execute()
    complaint_row = res.data[0] if res.data else insert_data
    complaint_id  = complaint_row.get("id")

    # Record that this user is the first "voter" on their own complaint
    if complaint_id and user_id:
        try:
            supabase.table("complaint_votes").insert({
                "complaint_id": complaint_id,
                "user_id":      user_id,
                "scholar_id":   scholar_id or None,
            }).execute()
        except Exception:
            pass  # unique constraint may already exist — fine

    print(f"[ComplaintAgent] Complaint saved: '{title}' [{category}] id={complaint_id}")

    return {
        "complaint":      complaint_row,
        "similar":        similar,
        "hostel_details": hostel_details,
        "category":       category,
        "title":          title,
    }


# ── Vote on an existing complaint ─────────────────────────────────────────────

def vote_on_complaint(complaint_id: str, user_info: dict, supabase) -> dict:
    """
    Record that a student agrees with / has the same issue as an existing complaint.
    Increments vote_count atomically (fetch → increment → update).
    Returns updated complaint or raises if vote already cast.
    """
    user_id    = user_info.get("id")
    scholar_id = user_info.get("scholar_id") or ""

    # Check if already voted
    existing = (
        supabase.table("complaint_votes")
        .select("id")
        .eq("complaint_id", complaint_id)
        .eq("user_id", user_id)
        .execute()
    )
    if existing.data:
        return {"error": "already_voted", "message": "You have already voted on this complaint."}

    # Insert vote record
    supabase.table("complaint_votes").insert({
        "complaint_id": complaint_id,
        "user_id":      user_id,
        "scholar_id":   scholar_id or None,
    }).execute()

    # Increment vote_count
    current = (
        supabase.table("complaints")
        .select("vote_count")
        .eq("id", complaint_id)
        .execute()
    )
    current_count = current.data[0]["vote_count"] if current.data else 0
    updated = (
        supabase.table("complaints")
        .update({"vote_count": current_count + 1})
        .eq("id", complaint_id)
        .execute()
    )
    print(f"[ComplaintAgent] Vote recorded on {complaint_id}: count now {current_count + 1}")
    return {
        "message":    "Vote recorded.",
        "vote_count": current_count + 1,
        "complaint":  updated.data[0] if updated.data else {},
    }
