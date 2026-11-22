"""Offline retrieval tests: a tiny corpus, a fake bag-of-words embedder, a fake reranker."""
import faiss
import numpy as np
import pytest

from app.retrieval import Retriever

DOCS = [
    ("infosys", 2024, 1, "revenue grew twelve percent driven by digital services"),
    ("infosys", 2023, 2, "revenue grew eight percent driven by cloud services"),
    ("tcs", 2024, 3, "operating margin improved due to utilization and pricing"),
    ("tcs", 2024, 4, "employee attrition declined during the year"),
    ("wipro", 2024, 5, "the board approved a dividend for shareholders"),
]
CHUNKS = [
    {"chunk_id": i, "company": c, "fiscal_year": y, "doc_id": f"{c}_FY{y % 100}",
     "page": p, "type": "text", "text": t}
    for i, (c, y, p, t) in enumerate(DOCS)
]
VOCAB = sorted({w for _, _, _, t in DOCS for w in t.split()})


def fake_embed(text: str) -> np.ndarray:
    """Normalised word-count vector: cosine similarity ~ word overlap."""
    v = np.array([text.lower().split().count(w) for w in VOCAB], dtype="float32")
    n = np.linalg.norm(v)
    return v / n if n else v


@pytest.fixture
def retriever():
    index = faiss.IndexFlatIP(len(VOCAB))
    index.add(np.stack([fake_embed(c["text"]) for c in CHUNKS]))
    # fake reranker: prefers texts containing "margin" (so we can see reranking changed order)
    rerank = lambda q, texts: [10.0 if "margin" in t else 0.0 for t in texts]  # noqa: E731
    return Retriever(CHUNKS, index, embed_query=fake_embed, rerank=rerank)


def test_vector_finds_best_match(retriever):
    hits = retriever.search("revenue grew digital", mode="vector", top_k=2)
    assert hits[0].page == 1
    assert hits[0].source == "vector"


def test_hybrid_marks_chunk_found_by_both_retrievers(retriever):
    # "attrition" appears in the vocab, so both BM25 and the vector side find it
    hits = retriever.search("attrition", mode="hybrid", top_k=1)
    assert hits[0].page == 4
    assert hits[0].source == "vector+bm25"


def test_company_filter_applies_before_ranking(retriever):
    hits = retriever.search("revenue grew", company="tcs", mode="vector", top_k=5)
    assert hits and all(h.company == "tcs" for h in hits)


def test_year_and_company_filter(retriever):
    hits = retriever.search("revenue", company="Infosys", fiscal_year=2023, mode="hybrid")
    assert [h.page for h in hits] == [2]


def test_filter_with_no_match_returns_empty(retriever):
    assert retriever.search("revenue", company="nonexistent") == []
    assert retriever.search("revenue", company="nonexistent", mode="hybrid_rerank") == []


def test_rerank_reorders_and_sets_score(retriever):
    hits = retriever.search("revenue margin", mode="hybrid_rerank", top_k=3)
    assert hits[0].page == 3  # fake reranker pushes the "margin" chunk to the top
    assert hits[0].score == 10.0


def test_top_k_respected(retriever):
    assert len(retriever.search("revenue", mode="hybrid", top_k=2)) == 2


def test_bad_mode(retriever):
    with pytest.raises(ValueError):
        retriever.search("x", mode="magic")


def test_rrf_rewards_agreement():
    fused = Retriever._rrf([[(1, 0.9), (2, 0.8)], [(2, 5.0), (3, 4.0)]])
    assert fused[0][0] == 2  # chunk 2 appears in both lists, so it wins
