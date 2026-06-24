# CampusMind

CampusMind is an AI-powered student information assistant designed to provide accurate and contextual answers to student queries. It utilizes a RAG (Retrieval-Augmented Generation) pipeline, retrieving institutional documents to provide grounded, reliable answers.

## Features
- **Student Authentication:** Secure login and sign-up flows using Supabase Auth. Students register with their unique 7-digit Scholar ID, Name, Email, and Username.
- **Intelligent RAG Assistant:** Answers institution-specific questions using embedded documents retrieved from the vector database.
- **Personalized Context:** Identifies the logged-in student to seamlessly answer personalized queries (e.g., "What is my Scholar ID?").
- **Modern Interface:** Built with a beautiful, responsive frontend UI.

## Tech Stack
- **Frontend:** React, Vite, TailwindCSS (if applicable), and vanilla CSS for rich aesthetics.
- **Backend:** FastAPI, Python.
- **Database & Auth:** Supabase (PostgreSQL, pgvector, Supabase Auth).
- **AI/LLMs:** Groq API (Llama 3) for fast generation, Google Gemini API for powerful embeddings.

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
```

Run the FastAPI server:
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
Execute the SQL commands in `supabase_setup.sql` in your Supabase SQL Editor to initialize the `profiles` table, the `documents` table, row-level security (RLS), and vector search functions.
