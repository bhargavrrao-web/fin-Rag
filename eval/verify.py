"""Mark questions as human-verified (only verified questions are scored).

  python -m eval.verify L01 L02 M03     mark these ids as verified
  python -m eval.verify --checklist     regenerate eval/verify_checklist.md

Verify by opening the PDF at the stated page in a PDF viewer. Pages are PDF-viewer page
numbers (1 = first page), NOT the page number printed on the page itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

QUESTIONS = Path("eval/questions.json")
CHECKLIST = Path("eval/verify_checklist.md")


def mark_verified(ids: list[str], path: Path = QUESTIONS) -> list[str]:
    data = json.loads(path.read_text("utf-8"))
    known = {q["id"] for q in data}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise SystemExit(f"Unknown question ids: {unknown}")
    for q in data:
        if q["id"] in ids:
            q["verified"] = True
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    return ids


def render_checklist(path: Path = QUESTIONS) -> str:
    lines = [
        "# Verification checklist", "",
        "For each question: open the PDF at the page, confirm the expected answer is really "
        "there, then run `python -m eval.verify <id>`. Pages are PDF-viewer page numbers.", "",
    ]
    for q in json.loads(path.read_text("utf-8")):
        mark = "x" if q["verified"] else " "
        lines.append(f"- [{mark}] **{q['id']}** ({q['category']}) {q['question']}")
        lines.append(f"  - Expected: {q['expected_answer']}")
        for p in q["expected_pages"]:
            fy = p["fiscal_year"] % 100
            lines.append(f"  - Open `data/raw/{p['company']}_FY{fy}.pdf` at page {p['page']}")
        if not q["expected_pages"]:
            lines.append("  - Unanswerable: confirm the reports really do not contain this "
                         "(search the PDFs for the key terms).")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = sys.argv[1:]
    if args == ["--checklist"] or not args:
        CHECKLIST.write_text(render_checklist(), "utf-8")
        print(f"Wrote {CHECKLIST}")
        return
    done = mark_verified(args)
    CHECKLIST.write_text(render_checklist(), "utf-8")
    print(f"Marked verified: {', '.join(done)}")


if __name__ == "__main__":
    main()
