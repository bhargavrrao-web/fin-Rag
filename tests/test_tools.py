import json

import pytest

from app.retrieval import Hit
from app.tools import ToolBox, safe_eval, tool_schemas


# ---------------------------------------------------------------- calculator
@pytest.mark.parametrize(
    "expr, expected",
    [("1+2*3", 7), ("(1+2)*3", 9), ("2**10", 1024), ("-5 + 10", 5), ("10/4", 2.5),
     ("(1200-1000)/1000*100", 20.0)],
)
def test_safe_eval_ok(expr, expected):
    assert safe_eval(expr) == expected


@pytest.mark.parametrize(
    "expr",
    ["__import__('os').system('echo hi')", "abs(-1)", "x + 1", "'a' * 3", "True + 1",
     "2 ** 1000", "1 +", "[1,2]", "1 if 1 else 2"],
)
def test_safe_eval_rejects_unsafe_or_invalid(expr):
    with pytest.raises(ValueError):
        safe_eval(expr)


def test_calculator_tool_errors_are_text():
    box = ToolBox(retriever=None)
    assert box.call("calculator", {"expression": "1/0"}) == "ERROR: division by zero"
    assert box.call("calculator", '{"expression": "2+2"}') == "4"
    assert box.call("calculator", {"expression": "100*1.1"}).startswith("110")
    assert box.call("calculator", {"expression": "os"}).startswith("ERROR")


# ---------------------------------------------------------------- dispatch + validation
def test_unknown_tool_and_bad_args_return_errors():
    box = ToolBox(retriever=None)
    assert "unknown tool" in box.call("hack", {})
    assert box.call("calculator", "not json").startswith("ERROR: invalid arguments")
    assert box.call("calculator", {}).startswith("ERROR: invalid arguments")


def test_schemas_cover_three_tools():
    names = [s["function"]["name"] for s in tool_schemas()]
    assert names == ["search_documents", "get_pages", "calculator"]


# ---------------------------------------------------------------- get_pages
def chunk(i, page, text, kind="text", company="acme", fy=2024):
    return {"chunk_id": i, "company": company, "fiscal_year": fy, "doc_id": f"{company}_FY24",
            "page": page, "type": kind, "text": text}


class FakeRetriever:
    def __init__(self, chunks=(), hits=()):
        self.chunks, self.hits = list(chunks), list(hits)

    def search(self, query, company, fiscal_year, top_k, mode):
        assert mode == "hybrid_rerank"
        return self.hits


def test_get_pages_rebuilds_text_without_overlap_and_adds_tables():
    # second chunk repeats the last 2 words ("c d") of the first: overlap_words=2
    r = FakeRetriever([chunk(0, 1, "a b c d"), chunk(1, 1, "c d e f"),
                       chunk(2, 1, "| x | 1 |", kind="table")])
    out = ToolBox(r, overlap_words=2).call(
        "get_pages", {"company": "ACME", "fiscal_year": 24, "start_page": 1, "end_page": 1}
    )
    assert "a b c d e f" in out
    assert "Tables on this page" in out and "| x | 1 |" in out


def test_get_pages_limits_and_missing():
    box = ToolBox(FakeRetriever([chunk(0, 1, "a b c")]))
    too_many = box.call("get_pages", {"company": "acme", "fiscal_year": 2024,
                                      "start_page": 1, "end_page": 4})
    assert too_many.startswith("ERROR: invalid arguments")
    missing = box.call("get_pages", {"company": "acme", "fiscal_year": 2024,
                                     "start_page": 9, "end_page": 9})
    assert missing.startswith("ERROR") and "acme_FY24" in missing


# ---------------------------------------------------------------- search + refusal signal
def hit(score):
    return Hit(1, "revenue text", "acme", 2024, 7, score, "vector+bm25")


def test_search_flags_weak_evidence():
    weak = json.loads(ToolBox(FakeRetriever(hits=[hit(-4.0)]), weak_threshold=0.0)
                      .call("search_documents", {"query": "q"}))
    strong = json.loads(ToolBox(FakeRetriever(hits=[hit(5.0)]), weak_threshold=0.0)
                        .call("search_documents", {"query": "q"}))
    empty = json.loads(ToolBox(FakeRetriever(hits=[]), weak_threshold=0.0)
                       .call("search_documents", {"query": "q"}))
    assert weak["evidence_weak"] and "note" in weak
    assert not strong["evidence_weak"] and strong["hits"][0]["page"] == 7
    assert empty["evidence_weak"] and empty["best_score"] is None
