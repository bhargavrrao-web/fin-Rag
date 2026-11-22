"""The agent's three tools: search_documents, get_pages, calculator.

Each tool has a Pydantic model for its arguments (validation + the JSON schema we send to the
LLM). ToolBox.call() NEVER raises: any problem is returned as text so the model can recover.
"""
from __future__ import annotations

import ast
import json
import operator
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.ingest import OVERLAP_WORDS

MAX_PAGES = 3
SNIPPET_CHARS = 1200  # keep tool output small: it is re-sent to the LLM on every later step


# ---------------------------------------------------------------- argument models
def _year(v: Any) -> Any:
    # LLMs often say 24 for FY24; accept it and normalise to 2024.
    if isinstance(v, int) and 0 <= v < 100:
        return 2000 + v
    return v


class SearchArgs(BaseModel):
    """Search the annual reports. Returns the most relevant passages with page numbers."""

    query: str = Field(min_length=1, description="What to look for, in natural language")
    company: str | None = Field(None, description="Lowercase company name, e.g. 'infosys'")
    fiscal_year: int | None = Field(None, description="4-digit year, e.g. 2024 for FY24")
    top_k: int = Field(5, ge=1, le=10)

    _norm_year = field_validator("fiscal_year", mode="before")(_year)


class GetPagesArgs(BaseModel):
    """Read the full text of up to 3 consecutive pages of one report."""

    company: str
    fiscal_year: int = Field(description="4-digit year, e.g. 2024 for FY24")
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)

    _norm_year = field_validator("fiscal_year", mode="before")(_year)

    @field_validator("end_page")
    @classmethod
    def _check_range(cls, end: int, info) -> int:
        start = info.data.get("start_page", end)
        if end < start or end - start + 1 > MAX_PAGES:
            raise ValueError(f"page range must be 1 to {MAX_PAGES} pages, start <= end")
        return end


class CalculatorArgs(BaseModel):
    """Evaluate an arithmetic expression. Use for ALL arithmetic (growth %, margins)."""

    expression: str = Field(
        min_length=1, max_length=200, description="e.g. '(1200 - 1000) / 1000 * 100'"
    )


TOOL_MODELS: dict[str, type[BaseModel]] = {
    "search_documents": SearchArgs,
    "get_pages": GetPagesArgs,
    "calculator": CalculatorArgs,
}


def tool_schemas() -> list[dict]:
    """OpenAI function-calling format (LiteLLM translates it for other providers)."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": (model.__doc__ or "").strip(),
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in TOOL_MODELS.items()
    ]


# ---------------------------------------------------------------- safe calculator
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
MAX_EXPONENT = 100  # stops things like 9**9**9 from hanging the server


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic by walking the AST and allowing ONLY numbers and + - * / **.
    eval() would run arbitrary code (e.g. __import__('os')); this cannot."""

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
                raise ValueError(f"exponent too large (max {MAX_EXPONENT})")
            return _BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](walk(node.operand))
        raise ValueError("only numbers and + - * / ** ( ) are allowed")

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"invalid expression: {e.msg}") from e
    return walk(tree)


# ---------------------------------------------------------------- the toolbox
class ToolBox:
    def __init__(
        self,
        retriever,
        weak_threshold: float = 0.0,
        overlap_words: int = OVERLAP_WORDS,
    ):
        self.retriever = retriever
        self.weak_threshold = weak_threshold
        self.overlap_words = overlap_words

    def call(self, name: str, raw_args: str | dict) -> str:
        """Run a tool; always returns a string (errors are returned, not raised)."""
        model = TOOL_MODELS.get(name)
        if model is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(TOOL_MODELS)}"
        try:
            data = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            args = model.model_validate(data)
            return getattr(self, name)(args)
        except (json.JSONDecodeError, ValidationError) as e:
            return f"ERROR: invalid arguments: {e}"
        except Exception as e:  # noqa: BLE001 - tool failures must go back to the model
            return f"ERROR: {type(e).__name__}: {e}"

    def search_documents(self, args: SearchArgs) -> str:
        # Always the strongest mode; its rerank score is also our refusal signal.
        hits = self.retriever.search(
            args.query, args.company, args.fiscal_year, args.top_k, mode="hybrid_rerank"
        )
        best = max((h.score for h in hits), default=None)
        weak = best is None or best < self.weak_threshold
        out: dict[str, Any] = {
            "evidence_weak": weak,
            "best_score": None if best is None else round(best, 3),
            "hits": [
                {
                    "company": h.company,
                    "fiscal_year": h.fiscal_year,
                    "page": h.page,
                    "score": round(h.score, 3),
                    "text": h.text[:SNIPPET_CHARS],
                }
                for h in hits
            ],
        }
        if weak:
            out["note"] = (
                "Evidence is weak. Try one differently-worded search; if still weak, "
                "answer with status not_found."
            )
        return json.dumps(out, ensure_ascii=False)

    def get_pages(self, args: GetPagesArgs) -> str:
        company = args.company.lower()
        parts = []
        for page in range(args.start_page, args.end_page + 1):
            rows = [
                c
                for c in self.retriever.chunks
                if c["company"] == company
                and c["fiscal_year"] == args.fiscal_year
                and c["page"] == page
            ]
            text_chunks = [c["text"] for c in rows if c["type"] == "text"]
            tables = [c["text"] for c in rows if c["type"] == "table"]
            # Consecutive text chunks overlap by overlap_words; drop that repeat on rebuild.
            words: list[str] = []
            for i, t in enumerate(text_chunks):
                w = t.split()
                words.extend(w if i == 0 else w[self.overlap_words :])
            body = " ".join(words)
            if tables:
                body += "\n\nTables on this page:\n" + "\n\n".join(tables)
            parts.append(f"--- {company} FY{args.fiscal_year % 100} page {page} ---\n{body}")
        if not any(p.split("\n", 1)[1].strip() for p in parts):
            docs = sorted({c["doc_id"] for c in self.retriever.chunks})
            return f"ERROR: no text found for those pages. Indexed documents: {docs}"
        return "\n\n".join(parts)

    def calculator(self, args: CalculatorArgs) -> str:
        try:
            result = safe_eval(args.expression)
        except ZeroDivisionError:
            return "ERROR: division by zero"
        except (ValueError, OverflowError) as e:
            return f"ERROR: {e}"
        return str(round(result, 6) if isinstance(result, float) else result)
