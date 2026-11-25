"""API tests: the agent is replaced by a stub, so no model, index or network is needed."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main

FAKE = {"answer": "ok", "citations": [], "status": "answered", "steps": [],
        "latency_ms": 5, "tokens": {"prompt": 1, "completion": 1}, "cost_usd": 0.0}


@pytest.fixture
def client(monkeypatch):
    main.limiter.reset()
    monkeypatch.setattr(main, "daily_cap", main.DailyCap(1000))
    monkeypatch.setattr(main, "answer_question", lambda q: FAKE)
    return TestClient(main.app, raise_server_exceptions=False)


def test_ask_ok(client):
    r = client.post("/ask", json={"question": "  What is revenue? "})
    assert r.status_code == 200 and r.json()["status"] == "answered"


@pytest.mark.parametrize("q", ["", "   ", "x" * 501])
def test_ask_rejects_bad_length(client, q):
    r = client.post("/ask", json={"question": q})
    assert r.status_code == 422 and "500" in r.json()["detail"]


def test_daily_cap_returns_friendly_429(client, monkeypatch):
    monkeypatch.setattr(main, "daily_cap", main.DailyCap(1))
    assert client.post("/ask", json={"question": "a"}).status_code == 200
    r = client.post("/ask", json={"question": "b"})
    assert r.status_code == 429 and "daily" in r.json()["detail"]


def test_rate_limit_per_ip(client):
    codes = [client.post("/ask", json={"question": "a"}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and 429 in codes[10:]


def test_agent_failure_does_not_leak_details(client, monkeypatch):
    def boom(q):
        raise RuntimeError("secret api key sk-123 in traceback")

    monkeypatch.setattr(main, "answer_question", boom)
    r = client.post("/ask", json={"question": "a"})
    assert r.status_code == 502 and "sk-123" not in r.text and "Traceback" not in r.text


def test_missing_index_gives_503(client, monkeypatch):
    def missing(q):
        raise FileNotFoundError("data/index/faiss.index")

    monkeypatch.setattr(main, "answer_question", missing)
    r = client.post("/ask", json={"question": "a"})
    assert r.status_code == 503 and "faiss" not in r.text


def test_health_and_config(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "model" in client.get("/api/config").json()


def test_docs_list(client, monkeypatch, tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"docs": ["infosys_FY24", "tech_mahindra_FY23"]}))
    monkeypatch.setattr(main, "META_PATH", meta)
    docs = client.get("/api/docs-list").json()["documents"]
    assert docs[1] == {"doc_id": "tech_mahindra_FY23", "company": "tech_mahindra",
                       "fiscal_year": 2023}
    monkeypatch.setattr(main, "META_PATH", tmp_path / "nope.json")
    assert client.get("/api/docs-list").json() == {"documents": []}


def test_eval_results(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "EVAL_RESULTS", tmp_path / "nope.json")
    assert client.get("/api/eval-results").json() == {"available": False}
    f = tmp_path / "results.json"
    f.write_text(json.dumps({"meta": {"n": 1}, "summary": {"A": {}}, "records": [1, 2, 3]}))
    monkeypatch.setattr(main, "EVAL_RESULTS", f)
    data = client.get("/api/eval-results").json()
    assert data["available"] and "records" not in data


def test_cors_locked_down_and_static_served(client):
    r = client.get("/", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200 and "FinRAG" in r.text
    assert "access-control-allow-origin" not in r.headers
    assert client.get("/app.js").status_code == 200
