"""Ingestion: PDF -> page-level chunks -> embeddings -> FAISS index.

Run:  python -m app.ingest --pdf-dir data/raw
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

# bge models want this prefix on QUERIES only, never on documents.
# Phase 2 imports it from here so both sides stay in sync.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

# Chunk sizes are counted in WORDS, not tokens: it needs no tokenizer and is easy to explain.
# ~1 token = 0.75 words, so 350 words is roughly 470 tokens - safely under bge's 512 limit.
CHUNK_WORDS = 350
OVERLAP_WORDS = 60
MIN_WORDS = 15  # shorter chunks (page numbers, headers) are noise

FILENAME_RE = re.compile(r"^(?P<company>.+)_FY(?P<yy>\d{2})$", re.IGNORECASE)


@dataclass
class Chunk:
    chunk_id: int
    company: str
    fiscal_year: int  # 4-digit, e.g. 2024 for FY24
    doc_id: str
    page: int  # 1-based, matches what a human sees in the PDF viewer
    type: str  # "text" | "table"
    text: str


def parse_filename(path: str | Path) -> tuple[str, int, str]:
    """'infosys_FY24.pdf' -> ('infosys', 2024, 'infosys_FY24')."""
    stem = Path(path).stem
    m = FILENAME_RE.match(stem)
    if not m:
        raise ValueError(f"Bad filename '{stem}': expected <company>_FY<yy>.pdf")
    return m["company"].lower(), 2000 + int(m["yy"]), stem


def is_garbage(text: str) -> bool:
    """True for empty / too-short / mostly non-letter chunks."""
    if len(text.split()) < MIN_WORDS:
        return True
    letters = sum(c.isalpha() for c in text)
    return letters / max(len(text), 1) < 0.3


def chunk_text(
    text: str, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS
) -> list[str]:
    """Sliding window over words. Overlap keeps sentences cut at a boundary retrievable."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
        start += size - overlap
    return chunks


def table_to_text(rows: list[list[str | None]]) -> str:
    """Rows -> markdown-like lines. Cells are cleaned; fully empty rows are dropped."""
    lines = []
    for row in rows:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if any(cells):
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def split_table(text: str, size: int = CHUNK_WORDS) -> list[str]:
    """Split a big table by rows (never mid-row) and repeat the header row in each part."""
    lines = text.split("\n")
    if len(text.split()) <= size or len(lines) < 3:
        return [text]
    header, parts, cur, cur_words = lines[0], [], [], 0
    for line in lines[1:]:
        n = len(line.split())
        if cur and cur_words + n > size:
            parts.append("\n".join([header, *cur]))
            cur, cur_words = [], 0
        cur.append(line)
        cur_words += n
    if cur:
        parts.append("\n".join([header, *cur]))
    return parts


def extract_chunks(
    pdf_path: str | Path, size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS
) -> list[Chunk]:
    """All chunks of one PDF. chunk_id is assigned later (globally unique across PDFs)."""
    import pymupdf

    company, fy, doc_id = parse_filename(pdf_path)
    chunks: list[Chunk] = []

    def add(page_no: int, kind: str, text: str) -> None:
        if not is_garbage(text):
            chunks.append(Chunk(-1, company, fy, doc_id, page_no, kind, text))

    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            # Chunking per page => every citation maps to exactly one page.
            for piece in chunk_text(page.get_text("text"), size, overlap):
                add(i + 1, "text", piece)
            # Tables become their own chunks so numbers keep their row/column structure.
            # The same numbers also appear in the page text; the duplication is accepted.
            for table in page.find_tables().tables:
                text = table_to_text(table.extract())
                for part in split_table(text, size):
                    add(i + 1, "table", part)
    return chunks


def embed_texts(texts: list[str], batch_size: int = 32):
    """Normalized embeddings, so inner product == cosine similarity."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL)
    return model.encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=True
    ).astype("float32")


def build_index(
    pdf_dir: str | Path,
    chunks_path: str | Path = "data/processed/chunks.jsonl",
    index_path: str | Path = "data/index/faiss.index",
    meta_path: str | Path = "data/index/meta.json",
    size: int = CHUNK_WORDS,
    overlap: int = OVERLAP_WORDS,
) -> int:
    import faiss

    pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {pdf_dir}")

    chunks: list[Chunk] = []
    for pdf in pdfs:
        got = extract_chunks(pdf, size, overlap)
        print(f"{pdf.name}: {len(got)} chunks")
        chunks.extend(got)
    for i, c in enumerate(chunks):
        c.chunk_id = i  # chunk_id == row number in the FAISS index

    vectors = embed_texts([c.text for c in chunks])
    index = faiss.IndexFlatIP(vectors.shape[1])  # exact search; fine for a few thousand chunks
    index.add(vectors)

    for p in (chunks_path, index_path, meta_path):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(chunks_path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    faiss.write_index(index, str(index_path))
    meta = {
        "embed_model": EMBED_MODEL,
        "dim": int(vectors.shape[1]),
        "n_chunks": len(chunks),
        "chunk_words": size,
        "overlap_words": overlap,
        "docs": sorted({c.doc_id for c in chunks}),
    }
    Path(meta_path).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Indexed {len(chunks)} chunks from {len(pdfs)} PDFs")
    return len(chunks)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the FinRAG index from PDFs")
    ap.add_argument("--pdf-dir", default="data/raw")
    ap.add_argument("--chunk-words", type=int, default=CHUNK_WORDS)
    ap.add_argument("--overlap-words", type=int, default=OVERLAP_WORDS)
    args = ap.parse_args()
    build_index(args.pdf_dir, size=args.chunk_words, overlap=args.overlap_words)


if __name__ == "__main__":
    main()
