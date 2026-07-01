import os
import requests
import json
import httpx
from typing import Dict, Any, Optional

from rag import get_answer
from complaint_agent import classify_complaint, process_complaint, STATUS_LABELS

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# In-memory state: {chat_id: "awaiting_scholar_id" | "awaiting_complaint" | None}
_bot_state: dict = {}

def send_message(chat_id: str, text: str, parse_mode: str = "Markdown", reply_markup: Optional[Dict] = None):
    """Send any text message to a Telegram chat."""
    if not BOT_TOKEN:
        return
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        # Fire and forget mostly, but we use httpx for non-blocking if possible,
        # but here we can just use requests since this is in a background task
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[TelegramBot] send_message error: {e}")

def send_telegram_push(chat_id: str, title: str, message: str, icon: str = "📢"):
    """Used by notice_agent — push a notice to a student's Telegram."""
    text = f"{icon} *{title}*\n\n{message}"
    send_message(chat_id, text)


def _link_scholar_id(chat_id: str, scholar_id_text: str, supabase):
    """
    1. Strip/validate 7-digit scholar ID from user text
    2. Query profiles WHERE scholar_id = ?
    3. If found: UPDATE profiles SET telegram_chat_id = chat_id
    4. Reply: "✅ Linked! Welcome, [Name]."
    5. If not found: reply error, stay in AWAITING_SCHOLAR_ID state
    """
    scholar_id = scholar_id_text.strip()
    if len(scholar_id) != 7 or not scholar_id.isdigit():
        send_message(chat_id, "⚠️ Invalid Scholar ID format. Please enter a 7-digit number.")
        return

    try:
        # Check if scholar ID exists
        res = supabase.table("profiles").select("id, name, telegram_chat_id").eq("scholar_id", scholar_id).execute()
        if not res.data:
            send_message(chat_id, f"❌ Scholar ID {scholar_id} not found in our records. Please try again or contact administration.")
            return

        user_id = res.data[0]["id"]
        name = res.data[0]["name"]
        existing_chat = res.data[0].get("telegram_chat_id")

        if existing_chat and existing_chat != str(chat_id):
             send_message(chat_id, f"⚠️ This Scholar ID is already linked to another Telegram account.")
             _bot_state[chat_id] = None
             return

        # Link it
        supabase.table("profiles").update({"telegram_chat_id": str(chat_id)}).eq("id", user_id).execute()
        
        _bot_state[chat_id] = None # Clear state
        
        welcome_text = (
            f"✅ *Account linked!*\n\n"
            f"Welcome, {name} 👋\n"
            f"Scholar ID: {scholar_id}\n\n"
            f"You can now:\n"
            f"• Type any question to query the knowledge base\n"
            f"• /complaint — File a complaint\n"
            f"• /mycomplaints — Track your complaints\n"
            f"• /notifications — View recent notices"
        )
        send_message(chat_id, welcome_text)

    except Exception as e:
        print(f"[TelegramBot] _link_scholar_id error: {e}")
        send_message(chat_id, "❌ An error occurred while linking your account. Please try again later.")
        _bot_state[chat_id] = None


def _handle_my_complaints(chat_id: str, user_id: str, supabase):
    """
    Fetches complaints WHERE user_id = ?
    Formats as a readable list with status icons and vote counts
    """
    try:
        res = supabase.table("complaints").select("id, title, status, category, vote_count, created_at").eq("user_id", user_id).order("created_at", desc=True).limit(5).execute()
        complaints = res.data or []
        
        if not complaints:
            send_message(chat_id, "You have not filed any complaints.")
            return

        open_count = sum(1 for c in complaints if c["status"] == "open")
        text = f"📋 *Your Complaints* ({open_count} open)\n\n"
        
        for c in complaints:
            status_info = STATUS_LABELS.get(c["status"], ("❓", "Unknown"))
            icon = status_info[0]
            status_label = status_info[1]
            title = c["title"]
            votes = c["vote_count"]
            
            # Very rough time ago logic (just keeping it simple for display or omit)
            text += f"{icon} {title}\n   {icon} {status_label} · 👥 {votes} votes\n\n"
            
        send_message(chat_id, text.strip())
    except Exception as e:
        print(f"[TelegramBot] _handle_my_complaints error: {e}")
        send_message(chat_id, "❌ Could not fetch complaints.")

def _handle_notifications(chat_id: str, user_id: str, supabase):
    """
    Fetches last 5 user_notifications WHERE user_id = ? ORDER BY created_at DESC
    """
    try:
        res = supabase.table("user_notifications").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(5).execute()
        notifs = res.data or []
        
        if not notifs:
            send_message(chat_id, "No recent notifications.")
            return

        text = "🔔 *Recent Notifications*\n\n"
        for n in notifs:
            title = n.get("notification_title", "Notice")
            msg = n.get("notification_message", "")
            is_read = "O" if n.get("is_read") else "🔴"
            text += f"{is_read} *{title}*\n{msg}\n\n"
            
        send_message(chat_id, text.strip())
    except Exception as e:
        print(f"[TelegramBot] _handle_notifications error: {e}")
        send_message(chat_id, "❌ Could not fetch notifications.")


def _handle_complaint_submission(chat_id: str, text: str, user_info: dict, supabase):
    """
    Calls classify_complaint(text)
    If is_complaint → calls process_complaint() → formats result
    Shows: "✅ Filed as [category]! X similar complaints found."
    If not_complaint → "This doesn't look like a complaint. Just type normally to ask questions."
    """
    send_message(chat_id, "⏳ Analyzing your complaint...")
    
    classification = classify_complaint(text)
    
    if not classification.get("is_complaint"):
        send_message(chat_id, "ℹ️ This doesn't look like a complaint. If you meant to ask a question, just type it normally!")
        _bot_state[chat_id] = None
        return
        
    try:
        # Submit the complaint
        result = process_complaint(text, classification, user_info, supabase)
        
        if "error" in result:
             send_message(chat_id, f"❌ Failed to submit complaint: {result['error']}")
        else:
             cat = classification.get("category", "general").capitalize()
             msg = f"✅ *Complaint Filed!*\n\nCategory: {cat}\n\nYour complaint has been logged and sent to administration."
             
             similar = result.get("similar_complaints", [])
             if similar:
                 msg += f"\n\nWe found {len(similar)} similar open complaints. We've grouped yours for higher visibility."
                 
             send_message(chat_id, msg)
             
    except Exception as e:
         print(f"[TelegramBot] _handle_complaint_submission error: {e}")
         send_message(chat_id, "❌ An error occurred filing your complaint.")
         
    _bot_state[chat_id] = None


def _handle_rag_query(chat_id: str, query: str, user_info: dict):
    """
    Calls get_answer(query, user_info=user_info) from rag.py
    Formats the answer (strip markdown if too long for Telegram)
    """
    send_message(chat_id, "🔍 Thinking...")
    try:
        result = get_answer(query, user_info=user_info)
        answer = result.get("answer", "I couldn't find an answer to that.")
        
        # Simple cleanup for Telegram markdown compatibility (Telegrams Markdown is a bit strict, but we'll try)
        # We might need to handle Telegram MarkdownV2 or just rely on basic Markdown
        # Telegram Markdown doesn't support **, it supports * for bold.
        answer = answer.replace("**", "*")
        
        send_message(chat_id, answer)
    except Exception as e:
        print(f"[TelegramBot] _handle_rag_query error: {e}")
        send_message(chat_id, "❌ Error retrieving answer.")


def handle_update(update: dict, supabase):
    """
    Main entry point called from the FastAPI webhook endpoint.
    1. Extract chat_id, text, username from update dict
    2. Look up profile by telegram_chat_id → get user_info
    3. Route to correct handler based on command or state
    """
    message = update.get("message")
    if not message:
        return
        
    chat_id = str(message.get("chat", {}).get("id"))
    text = message.get("text", "").strip()
    
    if not chat_id or not text:
        return
        
    print(f"[TelegramBot] Received message from {chat_id}: {text[:50]}")

    # Check for linked account
    user_info = None
    try:
        res = supabase.table("profiles").select("*").eq("telegram_chat_id", chat_id).execute()
        if res.data:
            user_info = res.data[0]
    except Exception as e:
        print(f"[TelegramBot] User lookup error: {e}")

    state = _bot_state.get(chat_id)

    # 1. State Handlers First
    if state == "awaiting_scholar_id":
        if text.startswith("/"):
            _bot_state[chat_id] = None # Cancel state if command
        else:
            _link_scholar_id(chat_id, text, supabase)
            return
            
    elif state == "awaiting_complaint":
        if text.startswith("/"):
            _bot_state[chat_id] = None # Cancel state if command
        else:
            _handle_complaint_submission(chat_id, text, user_info, supabase)
            return

    # 2. Command Handlers
    if text.startswith("/start"):
        _bot_state[chat_id] = "awaiting_scholar_id"
        send_message(chat_id, "👋 Welcome to *CampusMind*!\n\nPlease enter your 7-digit Scholar ID to link your account:")
        return
        
    elif text.startswith("/help"):
        help_text = (
            "🤖 *CampusMind Bot Help*\n\n"
            "/start - Link your account\n"
            "/complaint - File a new complaint\n"
            "/mycomplaints - View your complaints\n"
            "/notifications - View recent notices\n"
            "/help - Show this message\n\n"
            "You can also just type any question to search the university knowledge base!"
        )
        send_message(chat_id, help_text)
        return

    # 3. Requires Authentication Beyond This Point
    if not user_info:
        send_message(chat_id, "⚠️ You need to link your account first. Please type /start and enter your Scholar ID.")
        return

    if text.startswith("/complaint"):
        _bot_state[chat_id] = "awaiting_complaint"
        send_message(chat_id, "📝 Please describe your issue or complaint in a few sentences:")
        return
        
    elif text.startswith("/mycomplaints"):
        _handle_my_complaints(chat_id, user_info["id"], supabase)
        return
        
    elif text.startswith("/notifications"):
        _handle_notifications(chat_id, user_info["id"], supabase)
        return
        
    # 4. Default: RAG Query
    _handle_rag_query(chat_id, text, user_info)


async def setup_webhook():
    """
    Called on FastAPI startup.
    Calls https://api.telegram.org/bot{TOKEN}/setWebhook
    with TELEGRAM_WEBHOOK_URL from .env
    """
    webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL")
    if not BOT_TOKEN or not webhook_url:
        print("[TelegramBot] TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_URL not set. Skipping webhook setup.")
        return
        
    url = f"{TELEGRAM_API}/setWebhook"
    try:
        # Need an async client for startup
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json={"url": webhook_url})
            res.raise_for_status()
            print(f"[TelegramBot] Webhook registered successfully: {res.json()}")
    except Exception as e:
        print(f"[TelegramBot] Failed to set webhook: {e}")
