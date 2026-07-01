# CampusMind

CampusMind is an AI-powered student information assistant and university management platform designed to streamline communication and grievance resolution. It utilizes a powerful RAG (Retrieval-Augmented Generation) pipeline, agentic workflows, and a native Telegram Bot to provide an integrated campus experience.

## Core Features

### 🤖 Intelligent RAG Assistant
- **Hybrid Search:** Combines semantic vector search (Google Gemini) with exact-keyword full-text search (PostgreSQL tsvector) via Reciprocal Rank Fusion (RRF) for incredibly accurate document retrieval.
- **Persistent Chat:** ChatGPT-style memory! Conversations are saved to the database. The AI seamlessly maintains contextual history (sliding window).
- **Personalized Context:** Identifies the logged-in student to seamlessly answer personalized queries (e.g., "What is my Scholar ID?").

### 📢 Agentic Notice Workflow
- **Smart Classification:** Auto-classification of documents uploaded by admins using Groq (Llama 3).
- **Targeted Delivery:** Automatically extracts Scholar IDs from documents using regex to send personalized in-app notifications.
- **Telegram Push:** When notices are published, students instantly receive a push notification on their linked Telegram account.

### 📝 Complaint & Grievance System
- **Agentic Routing:** Students file complaints which are automatically categorized (Hostel, Academic, Mess, Facility, etc.) by a specialized LLM agent.
- **Smart Grouping:** Uses semantic similarity to find and group related complaints, allowing students to "upvote" existing issues rather than duplicating them.
- **Admin Dashboard:** Administrators can view, manage, and update the status of complaints (Open, In Progress, Resolved).
- **Telegram Integration:** File complaints and check status directly via the CampusMind Telegram Bot using `/complaint` and `/mycomplaints`.

### 📱 Telegram Bot
- **Account Linking:** Securely link your 7-digit Scholar ID to your Telegram account using `/start`.
- **Instant Access:** Ask questions, get notifications, and manage complaints via Telegram without needing to log in to the web portal.

## Tech Stack
- **Frontend:** React, Vite, CSS (Micro-animations, responsive UI).
- **Backend:** FastAPI, Python.
- **Database & Auth:** Supabase (PostgreSQL, pgvector, Supabase Auth).
- **AI/LLMs:** Groq API (Llama 3) for fast generation, Google Gemini API for powerful embeddings.
- **Bot Platform:** Telegram Bot API (Webhook based).

## Local Development Setup

### 1. Clone the repository
```bash
git clone https://github.com/vaddethrishank/CampusMind.git
cd CampusMind
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the root directory with the following variables:
```env
GROQ_API_KEY=your_groq_api_key
GOOGLE_API_KEY=your_google_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_supabase_service_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_URL=https://your-ngrok-url.ngrok-free.app/api/telegram/webhook
```

Run the FastAPI server (also acts as the Telegram webhook receiver):
```bash
uvicorn main:app --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### 4. Database Setup
1. Execute `supabase_setup.sql` in your Supabase SQL Editor to initialize base tables.
2. Execute `notices_migration.sql` to add notification tables.
3. Execute `fix_rls.sql` to set up security policies for complaints.
4. Execute `telegram_migration.sql` to add the `telegram_chat_id` column for bot integration.
