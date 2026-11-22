"""Retrieval: vector | hybrid (vector + BM25 via RRF) | hybrid_rerank (+ cross-encoder).

Try it:  python -m app.retrieval "total revenue" --company infosys --year 2024
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from app.ingest import EMBED_MODEL, QUERY_PREFIX

RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CANDIDATES = 50  # per retriever
RRF_K = 60  # standard constant from the RRF paper; damps the impact of top ranks
RERANK_POOL = 20  # cross-encoder is slow, so only rerank the best fused candidates

MODES = ("vector", "hybrid", "hybrid_rerank")


@dataclass
class Hit:
    chunk_id: int
    text: str
    company: str
    fiscal_year: int
    page: int
    score: float  # meaning depends on mode: cosine | RRF score | cross-encoder logit
    source: str  # which retriever(s) found it: "vector", "bm25" or "vector+bm25"


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class Retriever:
    def __init__(
        self,
        chunks: list[dict],
        index: faiss.Index,
        embed_query: Callable[[str], np.ndarray] | None = None,
        rerank: Callable[[str, list[str]], list[float]] | None = None,
    ):
        """embed_query / rerank can be injected (tests use fakes); otherwise real models
        are loaded lazily on first use so importing this module stays cheap."""
        self.chunks = chunks  # chunks[i] is the chunk stored at FAISS row i
        self.index = index
        self._embed_query = embed_query
        self._rerank = rerank
        # One global BM25 index. Filters are applied to its scores afterwards.
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in chunks])

    @classmethod
    def from_disk(
        cls,
        chunks_path: str | Path = "data/processed/chunks.jsonl",
        index_path: str | Path = "data/index/faiss.index",
    ) -> Retriever:
        with open(chunks_path, encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f if line.strip()]
        return cls(chunks, faiss.read_index(str(index_path)))

    # ---- lazy model loading -------------------------------------------------
    def embed_query(self, query: str) -> np.ndarray:
        if self._embed_query is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(EMBED_MODEL)
            self._embed_query = lambda q: model.encode(
                QUERY_PREFIX + q, normalize_embeddings=True
            )  # prefix on queries only, not documents
        return np.asarray(self._embed_query(query), dtype="float32")

    def rerank_scores(self, query: str, texts: list[str]) -> list[float]:
        if self._rerank is None:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(RERANK_MODEL)
            self._rerank = lambda q, ts: model.predict([(q, t) for t in ts]).tolist()
        return self._rerank(query, texts)

    # ---- the three building blocks -----------------------------------------
    def _allowed_ids(self, company: str | None, fiscal_year: int | None) -> np.ndarray:
        """Filtering happens BEFORE ranking, so the top-k is never wasted on other companies."""
        ids = [
            i
            for i, c in enumerate(self.chunks)
            if (company is None or c["company"] == company.lower())
            and (fiscal_year is None or c["fiscal_year"] == fiscal_year)
        ]
        return np.array(ids, dtype="int64")

    def _vector_search(self, query: str, allowed: np.ndarray) -> list[tuple[int, float]]:
        if len(allowed) == 0:
            return []
        params = faiss.SearchParameters()
        params.sel = faiss.IDSelectorBatch(allowed)  # FAISS only considers these rows
        q = self.embed_query(query).reshape(1, -1)
        scores, ids = self.index.search(q, CANDIDATES, params=params)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0], strict=True) if i != -1]

    def _bm25_search(self, query: str, allowed: np.ndarray) -> list[tuple[int, float]]:
        if len(allowed) == 0:
            return []
        scores = self.bm25.get_scores(tokenize(query))[allowed]
        order = np.argsort(-scores)[:CANDIDATES]
        # score 0 means no query word matched: not a real hit
        return [(int(allowed[j]), float(scores[j])) for j in order if scores[j] > 0]

    @staticmethod
    def _rrf(rankings: list[list[tuple[int, float]]]) -> list[tuple[int, float]]:
        """Reciprocal Rank Fusion: score = sum over lists of 1 / (k + rank).
        Uses ranks only, so cosine scores and BM25 scores need no normalising."""
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, (cid, _) in enumerate(ranking, start=1):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        return sorted(fused.items(), key=lambda x: -x[1])

    def _hit(self, cid: int, score: float, source: str) -> Hit:
        c = self.chunks[cid]
        return Hit(cid, c["text"], c["company"], c["fiscal_year"], c["page"], score, source)

    # ---- public API ---------------------------------------------------------
    def search(
        self,
        query: str,
        company: str | None = None,
        fiscal_year: int | None = None,
        top_k: int = 5,
        mode: str = "hybrid_rerank",
    ) -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got '{mode}'")
        allowed = self._allowed_ids(company, fiscal_year)
        vec = self._vector_search(query, allowed)

        if mode == "vector":
            return [self._hit(cid, s, "vector") for cid, s in vec[:top_k]]

        kw = self._bm25_search(query, allowed)
        in_vec, in_kw = {c for c, _ in vec}, {c for c, _ in kw}

        def source(cid: int) -> str:
            return "vector+bm25" if cid in in_vec and cid in in_kw else (
                "vector" if cid in in_vec else "bm25"
            )

        fused = self._rrf([vec, kw])
        if mode == "hybrid":
            return [self._hit(cid, s, source(cid)) for cid, s in fused[:top_k]]

        # hybrid_rerank: the cross-encoder reads (query, chunk) together, so it is more
        # accurate than the bi-encoder but too slow to run on every chunk.
        pool = fused[:RERANK_POOL]
        if not pool:
            return []
        scores = self.rerank_scores(query, [self.chunks[cid]["text"] for cid, _ in pool])
        ranked = sorted(zip(pool, scores, strict=True), key=lambda x: -x[1])
        return [self._hit(cid, float(s), source(cid)) for (cid, _), s in ranked[:top_k]]


def main() -> None:
    ap = argparse.ArgumentParser(description="Query the FinRAG index")
    ap.add_argument("query")
    ap.add_argument("--company")
    ap.add_argument("--year", type=int, help="4-digit fiscal year, e.g. 2024")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--mode", choices=MODES, default="hybrid_rerank")
    args = ap.parse_args()
    hits = Retriever.from_disk().search(
        args.query, args.company, args.year, args.top_k, args.mode
    )
    for h in hits:
        print(f"[{h.score:.3f}] {h.company} FY{h.fiscal_year % 100} p.{h.page} ({h.source})")
        print("   " + h.text[:200].replace("\n", " ") + "...")


if __name__ == "__main__":
    main()
