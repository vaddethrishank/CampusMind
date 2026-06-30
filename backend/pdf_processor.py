"""
pdf_processor.py
────────────────
Smart PDF ingestion pipeline with automatic content-type detection.

Flow:
  PDF Upload
    ↓
  detect_content_type()
    ├── "image"   → PyMuPDF renders pages at 300 DPI
    │               → pytesseract OCR per page
    │               → reconstructed text re-classified:
    │                   ├── tabular patterns? → row-sentence chunks  (ocr_tabular)
    │                   └── plain text        → text-splitter chunks (ocr_text)
    ├── "tabular" → pdfplumber table extraction
    │               → header reconstruction (multi-row aware)
    │               → row → natural-language sentence
    │               → each row sentence = one chunk
    └── "text"    → PyPDFLoader + RecursiveCharacterTextSplitter

Returns a list of dicts: [{"content": str, "metadata": dict}, ...]

Prerequisites for OCR:
  - pytesseract  (pip install pytesseract)           ← already installed
  - PyMuPDF/fitz (pip install pymupdf)               ← already installed
  - Tesseract binary  https://github.com/UB-Mannheim/tesseract/wiki
      Windows default path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
"""

import re
import os
import io
import json
import warnings
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Constants ─────────────────────────────────────────────────────────────────
TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],
)

# If tables cover this fraction of pages → classify as tabular
TABULAR_PAGE_THRESHOLD = 0.30

# Minimum cells in a table row to be considered meaningful
MIN_ROW_CELLS = 2

# Minimum extractable characters on a page before it is considered image-only.
# Real text PDFs always have hundreds of chars per page; scanned images have ~0.
IMAGE_CHAR_THRESHOLD = 80

# Fraction of sampled pages that must fall below IMAGE_CHAR_THRESHOLD for the
# whole PDF to be classified as 'image'.  Set high (0.60) to avoid false positives
# on documents that mix a cover image with text pages.
IMAGE_PAGE_THRESHOLD = 0.60

# DPI used when rendering PDF pages to images for OCR
OCR_DPI = 300

# Tesseract binary path (Windows); auto-detected if on PATH
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ── 0. Tesseract bootstrap ─────────────────────────────────────────────────────

def _configure_tesseract() -> bool:
    """
    Point pytesseract at the Tesseract binary.
    Returns True if Tesseract appears to be available, False otherwise.
    """
    try:
        import pytesseract
        # If the default Windows path exists, use it explicitly
        if os.path.isfile(TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        # Quick smoke-test: get version (raises if not found)
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


# ── 1. Image-PDF detection ─────────────────────────────────────────────────────

def _page_char_count(page) -> int:
    """
    Given a fitz Page, return the number of extractable text characters.
    A scanned (image-only) page returns 0 or near-zero.
    A normal text page returns hundreds to thousands.
    """
    text = page.get_text("text")
    return len(text.strip())


def is_image_based_pdf(pdf_path: str) -> bool:
    """
    Use PyMuPDF to sample up to 5 pages and check the text density.
    Returns True if IMAGE_PAGE_THRESHOLD fraction of sampled pages have
    near-zero extractable text (i.e. they are scanned images).
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        total = len(doc)
        if total == 0:
            doc.close()
            return False

        # Sample evenly across the document (max 5 pages)
        sample_indices = sorted(set(
            [0] +
            [total // 4, total // 2, 3 * total // 4] +
            [total - 1]
        ))
        sample_indices = [i for i in sample_indices if 0 <= i < total]

        image_pages = 0
        for idx in sample_indices:
            page = doc[idx]
            chars = _page_char_count(page)
            if chars < IMAGE_CHAR_THRESHOLD:
                image_pages += 1
            print(f"[PDF Processor]   [detect] page {idx+1}: {chars} chars extracted")

        doc.close()
        ratio = image_pages / len(sample_indices)
        print(f"[PDF Processor]   [detect] {image_pages}/{len(sample_indices)} image-like pages (ratio={ratio:.2f}, threshold={IMAGE_PAGE_THRESHOLD})")
        return ratio >= IMAGE_PAGE_THRESHOLD

    except ImportError:
        print("[PDF Processor] PyMuPDF not installed — cannot detect image PDFs.")
        return False
    except Exception as e:
        print(f"[PDF Processor] Image detection error: {e}")
        return False


# ── 2. Content-type detection (3-way) ─────────────────────────────────────────

def detect_content_type(pdf_path: str) -> str:
    """
    Returns one of:
      'image'   — scanned / no extractable text layer
      'tabular' — majority of pages contain pdfplumber-detected tables
      'text'    — standard text-based PDF

    Detection order:
      1. Image check (PyMuPDF text density)  — fastest exclusion
      2. Table check (pdfplumber)
      3. Fallback → text
    """
    # ── Step 1: image-based check ──────────────────────────────────────────────
    if is_image_based_pdf(pdf_path):
        print(f"[PDF Processor] {Path(pdf_path).name}: image-based PDF detected → 'image'")
        return "image"

    # ── Step 2: tabular check ──────────────────────────────────────────────────
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            if total == 0:
                return "text"
            tabular_pages = 0
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        if any(
                            len([c for c in row if c and str(c).strip()]) >= MIN_ROW_CELLS
                            for row in table
                        ):
                            tabular_pages += 1
                            break
            ratio = tabular_pages / total
            content_type = "tabular" if ratio >= TABULAR_PAGE_THRESHOLD else "text"
            print(
                f"[PDF Processor] {Path(pdf_path).name}: "
                f"{tabular_pages}/{total} tabular pages → '{content_type}'"
            )
            return content_type

    except ImportError:
        print("[PDF Processor] pdfplumber not installed, falling back to text mode.")
        return "text"
    except Exception as e:
        print(f"[PDF Processor] Content detection error: {e} — falling back to text.")
        return "text"


# ── 3. Text-mode processing ────────────────────────────────────────────────────

def process_text_pdf(
    pdf_path: str,
    source_name: str,
    content_type_label: str = "text",
) -> List[Dict[str, Any]]:
    """
    Standard pipeline: PyPDFLoader → filter short pages → text splitter.

    Args:
        content_type_label: stored in metadata['content_type'].
                            Callers can pass 'ocr_text' when text came from OCR.
    """
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()
    valid = [p for p in pages if len(p.page_content.strip()) > 50]
    if not valid:
        return []

    splits = TEXT_SPLITTER.split_documents(valid)
    chunks = []
    for split in splits:
        meta = dict(split.metadata)
        meta["source"] = source_name
        meta["content_type"] = content_type_label
        chunks.append({"content": split.page_content.strip(), "metadata": meta})
    print(f"[PDF Processor] Text mode: {len(valid)} pages → {len(chunks)} chunks")
    return chunks


# ── 4. Tabular-mode processing ─────────────────────────────────────────────────

def _clean_cell(value) -> str:
    """Normalise a table cell: strip whitespace, collapse internal spaces."""
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _reconstruct_headers(table: List[List]) -> Optional[Tuple[List[str], int]]:
    """
    Identify header row(s) from a pdfplumber table.

    Strategy:
    1. The first non-empty row is the header candidate.
    2. If the *second* row also has no numeric-looking values, treat both as a
       merged multi-row header and join them column-by-column.
    3. Return a flat list of header strings and the data-start index.
    """
    if not table:
        return None

    def _is_data_row(row: List) -> bool:
        """A row is a data row if it has at least one purely numeric cell."""
        for cell in row:
            c = _clean_cell(cell)
            if re.match(r"^\d+(\.\d+)?$", c):
                return True
        return False

    # Find first non-empty row
    header_rows = []
    data_start = 0
    for i, row in enumerate(table):
        if all(_clean_cell(c) == "" for c in row):
            continue  # skip blank rows
        if not _is_data_row(row):
            header_rows.append(row)
            data_start = i + 1
        else:
            data_start = i
            break

    if not header_rows:
        # No distinct header found — use column indices
        n_cols = max(len(r) for r in table)
        return [f"Col{i+1}" for i in range(n_cols)], 0

    # Merge multi-row headers column-by-column
    n_cols = max(len(r) for r in header_rows)
    headers = []
    for col in range(n_cols):
        parts = []
        for row in header_rows:
            cell = _clean_cell(row[col]) if col < len(row) else ""
            if cell and cell not in parts:
                parts.append(cell)
        headers.append(" ".join(parts) if parts else f"Col{col+1}")

    return headers, data_start


def _table_to_nl_sentences(
    table: List[List],
    source_name: str,
    page_num: int,
    table_idx: int,
    content_type_label: str = "tabular",
) -> List[Dict[str, Any]]:
    """
    Convert a pdfplumber table into a list of natural-language sentences,
    one per data row.
    """
    result = _reconstruct_headers(table)
    if result is None:
        return []

    headers, data_start = result
    chunks = []

    for row in table[data_start:]:
        # Skip completely empty rows
        cells = [_clean_cell(c) for c in row]
        if not any(cells):
            continue

        # Build key=value pairs, skipping blanks
        pairs = []
        for header, value in zip(headers, cells):
            if value and header:
                pairs.append(f"{header}: {value}")

        if not pairs:
            continue

        sentence = " | ".join(pairs)

        # Detect registration-number-like fields (7-digit numbers)
        regn_match = None
        for header, value in zip(headers, cells):
            if re.match(r"^\d{7}$", value):
                regn_match = value
                break

        meta: Dict[str, Any] = {
            "source": source_name,
            "content_type": content_type_label,
            "page": page_num,
            "table_index": table_idx,
        }
        if regn_match:
            meta["regn_no"] = regn_match

        chunks.append({"content": sentence, "metadata": meta})

    return chunks


def process_tabular_pdf(
    pdf_path: str,
    source_name: str,
    content_type_label: str = "tabular",
) -> List[Dict[str, Any]]:
    """
    Tabular pipeline: pdfplumber → header reconstruction → NL sentence per row.
    Falls back to text-mode for pages with no tables.

    Args:
        content_type_label: stored in metadata['content_type'].
                            Callers can pass 'ocr_tabular' when text came from OCR.
    """
    import pdfplumber

    all_chunks: List[Dict[str, Any]] = []
    pages_with_no_tables: List[int] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                pages_with_no_tables.append(page_num)
                continue

            for t_idx, table in enumerate(tables):
                sentences = _table_to_nl_sentences(
                    table, source_name, page_num, t_idx,
                    content_type_label=content_type_label,
                )
                all_chunks.extend(sentences)

    print(f"[PDF Processor] Tabular mode: {len(all_chunks)} row-sentences from tables")

    # Process any non-table pages as regular text
    if pages_with_no_tables:
        try:
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()
            text_pages = [p for i, p in enumerate(pages, start=1) if i in pages_with_no_tables]
            valid = [p for p in text_pages if len(p.page_content.strip()) > 50]
            if valid:
                splits = TEXT_SPLITTER.split_documents(valid)
                fallback_label = (
                    "ocr_text_in_tabular_doc"
                    if "ocr" in content_type_label
                    else "text_in_tabular_doc"
                )
                for split in splits:
                    meta = dict(split.metadata)
                    meta["source"] = source_name
                    meta["content_type"] = fallback_label
                    all_chunks.append({"content": split.page_content.strip(), "metadata": meta})
                print(f"[PDF Processor] + {len(splits)} text chunks from non-table pages")
        except Exception as e:
            print(f"[PDF Processor] Text fallback error: {e}")

    return all_chunks


# ── 5. OCR-mode processing ─────────────────────────────────────────────────────

def ocr_page_to_text(page, dpi: int = OCR_DPI) -> str:
    """
    Render a fitz (PyMuPDF) Page to an image at `dpi` and run Tesseract OCR.

    Returns the extracted text string, or empty string on failure.
    """
    try:
        import fitz  # PyMuPDF — needed here for fitz.Matrix
        import pytesseract
        from PIL import Image

        # Render page to pixmap at the requested DPI.
        # fitz.Matrix(zoom, zoom) is the correct way to build a scale matrix;
        # page.get_matrix() returns the page's own transform and takes no args.
        zoom = dpi / 72  # fitz native resolution is 72 DPI
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Convert pixmap bytes → PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))

        # OCR
        text = pytesseract.image_to_string(img, lang="eng")
        return text

    except Exception as e:
        print(f"[PDF Processor] OCR error on page: {e}")
        return ""


def _ocr_text_looks_tabular(ocr_text: str) -> bool:
    """
    Heuristic: does the OCR-reconstructed text look like a table or list?

    Handles:
    - Results tables  : many digit groups per row (marks, regn numbers)
    - Hostel/allotment: roll no + name + room  → 2+ digit groups
    - General lists   : consistent multi-column whitespace alignment
    """
    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    if len(lines) < 3:
        return False

    # Lines with consistent multi-column spacing (2+ spaces between fields)
    multi_col = sum(
        1 for l in lines
        if re.search(r"\s{2,}", l) and len(l.split()) >= 2
    )

    # Lines with ≥2 numeric tokens (roll no. + room no. is enough)
    digit_rows = sum(
        1 for l in lines
        if len(re.findall(r"\b\d+\b", l)) >= 2
    )

    ratio = multi_col / len(lines)
    print(f"[PDF Processor]   [tabular?] multi_col={multi_col}/{len(lines)} ({ratio:.2f}), digit_rows={digit_rows}")
    return ratio >= 0.35 or digit_rows >= max(3, len(lines) // 5)


def _split_ocr_tabular_rows(
    page_texts: List[Tuple[int, str]],
    source_name: str,
) -> List[Dict[str, Any]]:
    """
    Row-level chunker for tabular OCR output.

    Strategy:
    - A line starting with a digit (roll no., regn no., serial no.) signals a
      new student/data row.  Any following non-digit lines are treated as
      continuation of that row (OCR sometimes wraps long lines).
    - Lines with no alphanumeric content are skipped (OCR noise).
    - Each fully assembled row → one chunk, matching the granularity of
      process_tabular_pdf() for normal table PDFs.
    """
    all_chunks: List[Dict[str, Any]] = []

    for page_num, text in page_texts:
        lines = [l.strip() for l in text.splitlines()]
        lines = [l for l in lines if re.search(r"[A-Za-z0-9]", l)]  # drop noise

        rows: List[str] = []
        current: List[str] = []

        for line in lines:
            # A line beginning with a digit signals the start of a new data row
            if re.match(r"^\d", line):
                if current:
                    rows.append(" | ".join(current))
                current = [line]
            else:
                # Header or continuation — keep as part of current row
                current.append(line)

        if current:
            rows.append(" | ".join(current))

        for row_text in rows:
            row_text = row_text.strip()
            if len(row_text) < 10:
                continue

            meta: Dict[str, Any] = {
                "source": source_name,
                "content_type": "ocr_tabular",
                "page": page_num,
                "ocr": True,
            }

            # Extract 7-digit registration numbers if present
            regn = re.search(r"\b(\d{7})\b", row_text)
            if regn:
                meta["regn_no"] = regn.group(1)

            all_chunks.append({"content": row_text, "metadata": meta})

    return all_chunks


def process_image_pdf(pdf_path: str, source_name: str) -> List[Dict[str, Any]]:
    """
    OCR pipeline for image-based (scanned) PDFs.

    Steps:
      1. Check Tesseract is available.
      2. Open PDF with PyMuPDF, OCR each page.
      3. Collect all page texts into a temporary plain-text file.
      4. Heuristically detect if the OCR content looks tabular.
         - If tabular → write reconstructed text to a temp PDF-like structure
           and route through pdfplumber-style tabular processing.
           (Because OCR text won't have actual table structures pdfplumber can
           detect, we fall through to text mode with ocr_tabular label.)
         - If text    → pass through RecursiveCharacterTextSplitter.
      5. Tag all chunks with content_type = 'ocr_text' or 'ocr_tabular'.

    Note: OCR output rarely contains real pdfplumber-detectable tables, so we
    use a text-based heuristic and split accordingly while preserving the
    correct metadata label for downstream filtering.
    """
    import fitz  # PyMuPDF

    # ── Tesseract availability check ───────────────────────────────────────────
    if not _configure_tesseract():
        print(
            "[PDF Processor] ⚠ Tesseract not found — OCR skipped. "
            "Install from https://github.com/UB-Mannheim/tesseract/wiki"
        )
        return []

    print(f"[PDF Processor] Image-PDF mode: running OCR on '{Path(pdf_path).name}' …")

    # ── OCR all pages ──────────────────────────────────────────────────────────
    doc = fitz.open(pdf_path)
    page_texts: List[Tuple[int, str]] = []  # (1-based page num, ocr text)

    for page_num, page in enumerate(doc, start=1):
        text = ocr_page_to_text(page, dpi=OCR_DPI)
        if text.strip():
            page_texts.append((page_num, text))
        print(f"[PDF Processor]   Page {page_num}/{len(doc)}: {len(text.strip())} chars from OCR")

    doc.close()

    if not page_texts:
        print("[PDF Processor] OCR produced no text — check Tesseract language data.")
        return []

    full_text = "\n\n".join(t for _, t in page_texts)
    is_tabular = _ocr_text_looks_tabular(full_text)
    label = "ocr_tabular" if is_tabular else "ocr_text"
    print(f"[PDF Processor] OCR content classified as: '{label}'")

    # ── Chunk the OCR text ─────────────────────────────────────────────────────
    if is_tabular:
        # Row-level chunking: one chunk per student/data row — same granularity
        # as process_tabular_pdf() for normal PDFs.
        all_chunks = _split_ocr_tabular_rows(page_texts, source_name)
        print(
            f"[PDF Processor] Image-PDF mode: {len(page_texts)} pages OCR'd "
            f"→ {len(all_chunks)} row-chunks (ocr_tabular)"
        )
    else:
        # Prose/notice text: use RecursiveCharacterTextSplitter per page.
        all_chunks: List[Dict[str, Any]] = []
        for page_num, text in page_texts:
            if not text.strip():
                continue
            splits = TEXT_SPLITTER.split_text(text)
            for chunk_text in splits:
                chunk_text = chunk_text.strip()
                if len(chunk_text) < 30:
                    continue
                all_chunks.append({
                    "content": chunk_text,
                    "metadata": {
                        "source": source_name,
                        "content_type": "ocr_text",
                        "page": page_num,
                        "ocr": True,
                    },
                })
        print(
            f"[PDF Processor] Image-PDF mode: {len(page_texts)} pages OCR'd "
            f"→ {len(all_chunks)} chunks (ocr_text)"
        )

    return all_chunks


# ── 6. LLM metadata generation ────────────────────────────────────────────────

def generate_pdf_metadata(
    filename: str,
    first_text: str,
    content_type: str,
) -> Dict[str, str]:
    """
    Use a single cheap Groq LLM call (~150 tokens) to generate structured,
    human-readable metadata for the PDF.

    Args:
        filename:     Original filename (used as fallback and context hint).
        first_text:   First 500 chars of the first extracted chunk.
        content_type: One of 'text', 'tabular', 'image', 'ocr_text', 'ocr_tabular'.

    Returns a dict with keys:
        title        — short human title (e.g. "Fee Payment Notice June 2026")
        category     — doc category (e.g. "notice", "results", "allotment", "syllabus")
        department   — dept/audience (e.g. "CSE 3rd Year", "All Students", "Unknown")
        description  — one sentence describing the document
        audience     — who this is for (e.g. "3rd year students", "all students")
    """
    excerpt = first_text[:500].strip()
    prompt = f"""You are a metadata generator for a university document management system.

Filename  : {filename}
Content   : {content_type}
Excerpt   :
\"\"\"
{excerpt}
\"\"\"

Generate concise, accurate metadata for this document.
Respond with a single JSON object only — no markdown, no explanation:
{{
  "title":       "<short human-readable document title, max 60 chars>",
  "category":    "<one of: notice | results | allotment | syllabus | timetable | handbook | fee | scholarship | event | general>",
  "department":  "<department or branch if identifiable, else 'All Departments'>",
  "description": "<one sentence describing the document, max 100 chars>",
  "audience":    "<who this document is for, max 40 chars, e.g. '3rd year CSE students'>"
}}

Rules:
- title must be human-readable, NOT the raw filename
- category must be exactly one of the listed values
- If department/audience is unclear from the excerpt, use 'All Students'
- Keep every field concise — this is stored as searchable metadata"""

    try:
        from groq import Groq
        from dotenv import load_dotenv
        load_dotenv(dotenv_path="../.env")
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        resp = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=150,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        print(
            f"[PDF Processor] LLM metadata: title='{result.get('title')}' "
            f"category='{result.get('category')}' dept='{result.get('department')}'"
        )
        return result
    except Exception as e:
        print(f"[PDF Processor] Metadata generation failed ({e}) — using filename fallback.")
        # Clean up filename as best-effort title
        clean = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
        return {
            "title":       clean,
            "category":    "general",
            "department":  "All Departments",
            "description": f"Document: {clean}",
            "audience":    "All Students",
        }


# ── 7. Main entry point ────────────────────────────────────────────────────────

def process_pdf(pdf_path: str, source_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Auto-detect and process a PDF through the correct pipeline branch,
    then enrich every chunk's metadata with LLM-generated fields.

    Args:
        pdf_path:    Absolute or relative path to the PDF file.
        source_name: Original filename stored in metadata['filename'].
                     Defaults to the file's basename.

    Returns:
        List of {"content": str, "metadata": dict} — ready for embedding & upload.

    Metadata fields on every chunk:
        source       — LLM-generated human title (replaces raw filename)
        filename     — original filename (preserved for traceability)
        title        — same as source
        category     — document category
        department   — department / audience group
        description  — one-sentence document description
        audience     — who the document targets
        content_type — pipeline branch used (text / tabular / ocr_text / ocr_tabular)
        page         — page number (where applicable)
        ocr          — True if the page was OCR-processed

    Content-type routing:
        "image"   → OCR via PyMuPDF + Tesseract → text/tabular chunks
        "tabular" → pdfplumber table extraction  → NL sentence per row
        "text"    → PyPDFLoader + RecursiveCharacterTextSplitter
    """
    if source_name is None:
        source_name = Path(pdf_path).name

    content_type = detect_content_type(pdf_path)

    if content_type == "image":
        chunks = process_image_pdf(pdf_path, source_name)
    elif content_type == "tabular":
        chunks = process_tabular_pdf(pdf_path, source_name)
    else:
        chunks = process_text_pdf(pdf_path, source_name)

    if not chunks:
        return chunks

    # ── LLM metadata enrichment ────────────────────────────────────────────────
    # Use first chunk's text as the excerpt for the LLM.
    first_text = chunks[0]["content"]
    actual_content_type = chunks[0]["metadata"].get("content_type", content_type)
    llm_meta = generate_pdf_metadata(source_name, first_text, actual_content_type)

    # Stamp every chunk with the rich metadata.
    # 'source' becomes the human title so the RAG retriever surfaces it cleanly.
    for chunk in chunks:
        chunk["metadata"].update({
            "source":      llm_meta.get("title", source_name),
            "filename":    source_name,          # original filename preserved
            "title":       llm_meta.get("title", source_name),
            "category":    llm_meta.get("category", "general"),
            "department":  llm_meta.get("department", "All Departments"),
            "description": llm_meta.get("description", ""),
            "audience":    llm_meta.get("audience", "All Students"),
        })

    print(
        f"[PDF Processor] Metadata enrichment complete: "
        f"{len(chunks)} chunks tagged with title='{llm_meta.get('title')}'"
    )
    return chunks
