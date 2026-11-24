"""FastAPI app: POST /ask, a few read-only endpoints, and the static web UI.

Run:  uvicorn app.main:app --port 7860
"""
from __future__ import annotations

import json
import logging
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.agent import result_to_dict, run_agent
from app.config import get_settings
from app.retrieval import Retriever
from app.tools import ToolBox

log = logging.getLogger("finrag")
settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"
EVAL_RESULTS = Path("eval/results.json")
META_PATH = Path("data/index/meta.json")
MAX_QUESTION_CHARS = 500


class AskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def _check(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= MAX_QUESTION_CHARS:
            raise ValueError(f"Question must be 1-{MAX_QUESTION_CHARS} characters.")
        return v


# ---------------------------------------------------------------- global daily cap
class DailyCap:
    """Protects the LLM bill: at most `limit` questions per calendar day, across all users.
    In-memory, so it resets on restart: fine for a single-container demo."""

    def __init__(self, limit: int):
        self.limit, self.day, self.count = limit, date.today(), 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self.day != date.today():
                self.day, self.count = date.today(), 0
            if self.count >= self.limit:
                return False
            self.count += 1
            return True


daily_cap = DailyCap(settings.daily_limit)
limiter = Limiter(key_func=get_remote_address)  # per-IP

def _warm_up() -> None:
    """Load the index and both models once, so the first real user doesn't wait ~1 minute."""
    try:
        r = get_retriever()
        r.search("warm up", top_k=1, mode="hybrid_rerank")
    except Exception:  # noqa: BLE001 - e.g. index not built yet; /ask reports that clearly
        log.warning("warm-up skipped", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()  # don't block startup
    yield


app = FastAPI(title="FinRAG Agent", docs_url=None, redoc_url=None, lifespan=lifespan)
app.state.limiter = limiter

# Locked down: with no CORS_ORIGINS set, no cross-origin site may call the API.
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"]
)


# ---------------------------------------------------------------- error handling
def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(request: Request, exc: RateLimitExceeded):
    return _err(429, "You're asking too fast. Please wait a minute and try again.")


@app.exception_handler(RequestValidationError)
async def _bad_request(request: Request, exc: RequestValidationError):
    return _err(422, f"Question must be 1-{MAX_QUESTION_CHARS} characters.")


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    log.exception("unhandled error")  # full trace goes to the server log only
    return _err(500, "Something went wrong on our side. Please try again.")


# ---------------------------------------------------------------- retriever (lazy, cached)
_retriever: Retriever | None = None
_retriever_lock = threading.Lock()


def get_retriever() -> Retriever:
    global _retriever
    with _retriever_lock:
        if _retriever is None:
            _retriever = Retriever.from_disk()
        return _retriever


def answer_question(question: str) -> dict:
    """Separate function so tests can replace it without any model or index."""
    retriever = get_retriever()
    box = ToolBox(retriever, weak_threshold=settings.weak_score_threshold)
    res = result_to_dict(run_agent(question, box, settings))
    for c in res.get("citations", []):
        if not c.get("passage"):
            try:
                chunks = [
                    ch["text"]
                    for ch in retriever.chunks
                    if ch.get("company") == c.get("company")
                    and ch.get("fiscal_year") == c.get("fiscal_year")
                    and ch.get("page") == c.get("page")
                ]
                if chunks:
                    c["passage"] = "\n\n".join(chunks)
            except Exception:
                pass
    return res


# ---------------------------------------------------------------- routes
@app.post("/ask")
@limiter.limit(settings.rate_limit)  # default "10/minute"
def ask(request: Request, body: AskRequest):
    if not daily_cap.try_acquire():
        return _err(429, "The demo hit its daily question limit. Please come back tomorrow.")
    try:
        result = answer_question(body.question)
    except FileNotFoundError:
        return _err(503, "The document index has not been built yet.")
    except Exception:
        log.exception("agent failed")
        return _err(502, "The AI model could not answer right now. Please try again.")
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {
        "model": settings.llm_model,
        "github_url": settings.github_url,
        "daily_limit": settings.daily_limit,
        "daily_count": daily_cap.count,
        "weak_score_threshold": settings.weak_score_threshold,
    }


@app.get("/api/docs-list")
def docs_list():
    if not META_PATH.exists():
        return {"documents": []}
    docs = json.loads(META_PATH.read_text("utf-8")).get("docs", [])
    out = []
    for d in docs:  # doc_id looks like "infosys_FY24"
        company, _, yy = d.rpartition("_FY")
        out.append({"doc_id": d, "company": company, "fiscal_year": 2000 + int(yy)})
    return {"documents": out}


@app.get("/api/eval-results")
def eval_results():
    if not EVAL_RESULTS.exists():
        return {"available": False}
    data = json.loads(EVAL_RESULTS.read_text("utf-8"))
    # per-question records can be large; the UI only needs the summary
    return {"available": True, "meta": data["meta"], "summary": data["summary"]}


# Mounted last so it only handles paths the API routes did not claim.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
