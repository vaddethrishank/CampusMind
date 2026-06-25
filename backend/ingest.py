"""
ingest.py – Batch ingestion script for all PDFs in ../data/pdfs/
Uses the smart pdf_processor module for auto content-type detection.
Run: python ingest.py
"""
import os
import sys
import glob
import time
from pathlib import Path
from dotenv import load_dotenv
from supabase.client import Client, create_client
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from pdf_processor import process_pdf

load_dotenv(dotenv_path="../.env")

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    print("ERROR: SUPABASE_URL or SUPABASE_SERVICE_KEY is missing from .env")
    sys.exit(1)

supabase: Client = create_client(supabase_url, supabase_key)

print("Initializing Google Gemini Embeddings...")
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-2")


def embed_with_retry(texts: list[str], max_retries: int = 5) -> list:
    for attempt in range(max_retries):
        try:
            return embeddings.embed_documents(texts)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 15 * (2 ** attempt)
                print(f"  Rate limit hit — waiting {wait}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Embedding failed after max retries.")


def ingest_all():
    pdf_dir = "../data/pdfs"
    pdf_files = sorted(set(glob.glob(os.path.join(pdf_dir, "**/*.pdf"), recursive=True)))

    if not pdf_files:
        print(f"ERROR: No PDF files found in '{pdf_dir}'")
        return

    print("\n" + "=" * 60)
    print("CAMPUSMIND BATCH INGESTION PIPELINE")
    print("=" * 60)
    print(f"\nFound {len(pdf_files)} PDF file(s):")
    for i, f in enumerate(pdf_files, 1):
        print(f"  {i}. {Path(f).name}")

    total_chunks_all = 0

    for pdf_path in pdf_files:
        filename = Path(pdf_path).name
        print(f"\n{'─' * 50}")
        print(f"Processing: {filename}")

        try:
            # Auto-detect content type and produce chunks
            chunks = process_pdf(pdf_path, source_name=filename)

            if not chunks:
                print(f"  WARNING: No content extracted from '{filename}' (possibly scanned image PDF)")
                continue

            content_type = chunks[0]["metadata"].get("content_type", "text")
            print(f"  Content type detected: {content_type}")
            print(f"  Total chunks: {len(chunks)}")

            # Embed & upload with rate-limit protection
            BATCH_SIZE = 10
            SLEEP_SECS = 7
            uploaded = 0
            total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

            for i in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[i:i + BATCH_SIZE]
                texts = [c["content"] for c in batch]
                batch_embs = embed_with_retry(texts)
                rows = [
                    {"content": c["content"], "metadata": c["metadata"], "embedding": emb}
                    for c, emb in zip(batch, batch_embs)
                ]
                supabase.table("documents").insert(rows).execute()
                uploaded += len(rows)
                batch_num = i // BATCH_SIZE + 1
                print(f"  Batch {batch_num}/{total_batches}: {uploaded}/{len(chunks)} uploaded")
                if i + BATCH_SIZE < len(chunks):
                    time.sleep(SLEEP_SECS)

            print(f"  DONE: {uploaded} chunks indexed for '{filename}'")
            total_chunks_all += uploaded

        except Exception as e:
            print(f"  ERROR processing '{filename}': {e}")

    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print(f"  Total chunks indexed across all PDFs: {total_chunks_all}")
    print("=" * 60)


if __name__ == "__main__":
    ingest_all()
