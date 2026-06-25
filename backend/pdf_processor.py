"""
pdf_processor.py
────────────────
Smart PDF ingestion pipeline with automatic content-type detection.

Flow:
  PDF Upload
    ↓
  detect_content_type()
    ├── "text"    → PyPDFLoader + RecursiveCharacterTextSplitter
    └── "tabular" → pdfplumber table extraction
                      → header reconstruction (multi-row aware)
                      → row → natural-language sentence
                      → each row sentence = one chunk

Returns a list of dicts: [{"content": str, "metadata": dict}, ...]
"""

import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

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


# ── 1. Content-type detection ──────────────────────────────────────────────────

def detect_content_type(pdf_path: str) -> str:
    """
    Returns 'tabular' if the majority of pages contain pdfplumber-extracted
    tables with multiple columns; otherwise returns 'text'.
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            if total == 0:
                return "text"
            tabular_pages = 0
            for page in pdf.pages:
                tables = page.extract_tables()
                # A page counts as tabular if it has at least one table with
                # multi-column rows
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
            print(f"[PDF Processor] {Path(pdf_path).name}: {tabular_pages}/{total} tabular pages → '{content_type}'")
            return content_type
    except ImportError:
        print("[PDF Processor] pdfplumber not installed, falling back to text mode.")
        return "text"
    except Exception as e:
        print(f"[PDF Processor] Content detection error: {e} — falling back to text.")
        return "text"


# ── 2. Text-mode processing ────────────────────────────────────────────────────

def process_text_pdf(pdf_path: str, source_name: str) -> List[Dict[str, Any]]:
    """
    Standard pipeline: PyPDFLoader → filter short pages → text splitter.
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
        meta["content_type"] = "text"
        chunks.append({"content": split.page_content.strip(), "metadata": meta})
    print(f"[PDF Processor] Text mode: {len(valid)} pages → {len(chunks)} chunks")
    return chunks


# ── 3. Tabular-mode processing ─────────────────────────────────────────────────

def _clean_cell(value) -> str:
    """Normalise a table cell: strip whitespace, collapse internal spaces."""
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _reconstruct_headers(table: List[List]) -> Optional[List[str]]:
    """
    Identify header row(s) from a pdfplumber table.

    Strategy:
    1. The first non-empty row is the header candidate.
    2. If the *second* row also has no numeric-looking values, treat both as a
       merged multi-row header and join them column-by-column.
    3. Return a flat list of header strings.
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
        return [f"Col{i+1}" for i in range(n_cols)]

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

        # Determine if this row has a registration-number-like field
        regn_match = None
        for header, value in zip(headers, cells):
            # Registration numbers: 7-digit numbers starting with year (e.g. 2312001)
            if re.match(r"^\d{7}$", value):
                regn_match = value
                break

        meta: Dict[str, Any] = {
            "source": source_name,
            "content_type": "tabular",
            "page": page_num,
            "table_index": table_idx,
        }
        if regn_match:
            meta["regn_no"] = regn_match

        chunks.append({"content": sentence, "metadata": meta})

    return chunks


def process_tabular_pdf(pdf_path: str, source_name: str) -> List[Dict[str, Any]]:
    """
    Tabular pipeline: pdfplumber → header reconstruction → NL sentence per row.
    Falls back to text-mode for pages with no tables.
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
                sentences = _table_to_nl_sentences(table, source_name, page_num, t_idx)
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
                for split in splits:
                    meta = dict(split.metadata)
                    meta["source"] = source_name
                    meta["content_type"] = "text_in_tabular_doc"
                    all_chunks.append({"content": split.page_content.strip(), "metadata": meta})
                print(f"[PDF Processor] + {len(splits)} text chunks from non-table pages")
        except Exception as e:
            print(f"[PDF Processor] Text fallback error: {e}")

    return all_chunks


# ── 4. Main entry point ────────────────────────────────────────────────────────

def process_pdf(pdf_path: str, source_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Auto-detect and process a PDF.

    Args:
        pdf_path:    Absolute or relative path to the PDF file.
        source_name: Label stored in metadata['source']. Defaults to filename.

    Returns:
        List of {"content": str, "metadata": dict} — ready for embedding & upload.
    """
    if source_name is None:
        source_name = Path(pdf_path).name

    content_type = detect_content_type(pdf_path)

    if content_type == "tabular":
        return process_tabular_pdf(pdf_path, source_name)
    else:
        return process_text_pdf(pdf_path, source_name)
