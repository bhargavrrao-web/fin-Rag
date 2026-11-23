# Data

Raw PDFs are **not committed** (size and copyright). Download the annual reports yourself and
save them in `data/raw/` as `<company>_FY<yy>.pdf` (lowercase company, two-digit fiscal year):

| File | Report | Where to get it (investor pages) |
|---|---|---|
| `infosys_FY25.pdf`, `infosys_FY26.pdf` | Infosys Integrated Annual Report 2024-25, 2025-26 | https://www.infosys.com/investors/reports-filings/annual-report.html |
| `tcs_FY25.pdf`, `tcs_FY26.pdf` | TCS Integrated Annual Report 2024-25, 2025-26 | https://www.tcs.com/investor-relations/financial-statements |
| `wipro_FY25.pdf`, `wipro_FY26.pdf` | Wipro Integrated Annual Report 2024-25, 2025-26 | https://www.wipro.com/investors/annual-reports/ |

Some investor sites block scripted downloads, so download in a browser. (Investor-page links
can change; search for "<company> integrated annual report <year>" if one is dead.)

Built artifacts (committed, about 20 MB):

- `data/processed/chunks.jsonl`: one JSON chunk per line (company, fiscal_year, page, type, text)
- `data/index/faiss.index` and `data/index/meta.json`: the vector index and its settings

Rebuild with `python -m app.ingest --pdf-dir data/raw` (about 30 minutes on a laptop CPU).

Page numbers everywhere (chunks, citations, evaluation questions) are **PDF-viewer page
numbers** (the first page is 1), not the number printed on the page.
