import os
import pickle
import glob
from pathlib import Path
from dotenv import load_dotenv
from supabase.client import Client, create_client
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_community.retrievers import BM25Retriever

# Load environment variables
load_dotenv(dotenv_path="../.env")

# ── 1. Supabase Client ────────────────────────────────────────────────────────
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    print("❌ Error: SUPABASE_URL or SUPABASE_SERVICE_KEY is missing from .env")
    exit(1)

supabase: Client = create_client(supabase_url, supabase_key)

# ── 2. Embeddings ─────────────────────────────────────────────────────────────
print("🔧 Initializing Google Embeddings (models/gemini-embedding-2)...")
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-2")

# ── 3. Text Splitter ──────────────────────────────────────────────────────────
# chunk_size=800 and chunk_overlap=150 produces more chunks with better context
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    length_function=len,
    separators=["\n\n", "\n", ".", " ", ""]
)


def load_pdfs_individually(pdf_dir: str):
    """Load each PDF one at a time and show per-file progress."""
    pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "**/*.pdf"), recursive=True) +
                       glob.glob(os.path.join(pdf_dir, "*.pdf")))

    if not pdf_files:
        print(f"❌ No PDF files found in '{pdf_dir}'")
        return []

    print(f"\n📂 Found {len(pdf_files)} PDF file(s) in '{pdf_dir}':")
    for i, f in enumerate(pdf_files, 1):
        print(f"   {i}. {Path(f).name}")

    all_docs = []
    for i, pdf_path in enumerate(pdf_files, 1):
        filename = Path(pdf_path).name
        try:
            print(f"\n[{i}/{len(pdf_files)}] Loading: {filename}")
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()
            if not pages:
                print(f"   ⚠️  No text extracted from {filename} (possibly scanned/image PDF)")
                continue
            # Filter out pages with very little content
            valid_pages = [p for p in pages if len(p.page_content.strip()) > 50]
            skipped = len(pages) - len(valid_pages)
            print(f"   ✅ Loaded {len(valid_pages)} pages ({skipped} pages skipped — too short/empty)")
            all_docs.extend(valid_pages)
        except Exception as e:
            print(f"   ❌ Failed to load {filename}: {e}")

    return all_docs


def ingest_pdfs():
    pdf_dir = "../data/pdfs"
    print("=" * 60)
    print("🚀 Starting PDF Ingestion Pipeline")
    print("=" * 60)

    # ── Step 1: Load PDFs ────────────────────────────────────────
    print("\n📖 STEP 1: Loading PDFs...")
    all_docs = load_pdfs_individually(pdf_dir)

    if not all_docs:
        print("❌ No documents loaded. Exiting.")
        return

    total_pages = len(all_docs)
    total_chars = sum(len(d.page_content) for d in all_docs)
    print(f"\n📊 Total pages loaded  : {total_pages}")
    print(f"📊 Total characters    : {total_chars:,}")

    # ── Step 2: Chunking ─────────────────────────────────────────
    print("\n✂️  STEP 2: Splitting text into chunks...")
    print(f"   chunk_size={text_splitter._chunk_size}, chunk_overlap={text_splitter._chunk_overlap}")
    all_splits = text_splitter.split_documents(all_docs)
    print(f"   ✅ Created {len(all_splits)} chunks from {total_pages} pages")

    # Show per-source chunk breakdown
    source_counts: dict = {}
    for chunk in all_splits:
        src = Path(chunk.metadata.get("source", "unknown")).name
        source_counts[src] = source_counts.get(src, 0) + 1
    print("\n   Chunks per PDF:")
    for src, count in sorted(source_counts.items()):
        print(f"      {src}: {count} chunks")

    # ── Step 3: Upload to Supabase ───────────────────────────────
    print(f"\n☁️  STEP 3: Uploading {len(all_splits)} chunks to Supabase...")
    print("   (This may take a while — embedding each chunk via Google API)")

    BATCH_SIZE = 50
    total_batches = (len(all_splits) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_num in range(total_batches):
        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(all_splits))
        batch = all_splits[start:end]
        print(f"   📤 Uploading batch {batch_num + 1}/{total_batches} (chunks {start + 1}–{end})...", end="", flush=True)
        try:
            SupabaseVectorStore.from_documents(
                batch,
                embeddings,
                client=supabase,
                table_name="documents",
                query_name="match_documents"
            )
            print(" ✅")
        except Exception as e:
            print(f" ❌ FAILED: {e}")

    # ── Step 4: BM25 Index ───────────────────────────────────────
    print("\n🔍 STEP 4: Building BM25 keyword index for Hybrid Search...")
    bm25_retriever = BM25Retriever.from_documents(all_splits)
    bm25_path = "../data/bm25_retriever.pkl"
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25_retriever, f)
    print(f"   ✅ BM25 index saved to '{bm25_path}'")

    # ── Done ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("✅ INGESTION COMPLETE!")
    print(f"   Total chunks in Supabase: {len(all_splits)}")
    print("   You can now start the FastAPI server with: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    ingest_pdfs()
