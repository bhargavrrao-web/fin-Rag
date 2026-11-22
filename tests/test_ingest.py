import pymupdf
import pytest

from app.ingest import (
    chunk_text,
    extract_chunks,
    is_garbage,
    parse_filename,
    split_table,
    table_to_text,
)


def test_parse_filename():
    assert parse_filename("data/raw/infosys_FY24.pdf") == ("infosys", 2024, "infosys_FY24")
    assert parse_filename("tech_mahindra_FY23.pdf")[0] == "tech_mahindra"


def test_parse_filename_rejects_bad_names():
    with pytest.raises(ValueError):
        parse_filename("infosys_2024.pdf")


def test_chunk_text_size_and_overlap():
    text = " ".join(str(i) for i in range(100))
    chunks = chunk_text(text, size=40, overlap=10)
    assert all(len(c.split()) <= 40 for c in chunks)
    # consecutive chunks share exactly `overlap` words
    assert chunks[0].split()[-10:] == chunks[1].split()[:10]
    # nothing is lost: the last word appears in the last chunk
    assert chunks[-1].split()[-1] == "99"


def test_chunk_text_empty_and_short():
    assert chunk_text("") == []
    assert chunk_text("a b c", size=40, overlap=10) == ["a b c"]


def test_chunk_text_bad_overlap():
    with pytest.raises(ValueError):
        chunk_text("a b c", size=5, overlap=5)


def test_is_garbage():
    assert is_garbage("")
    assert is_garbage("42")
    assert is_garbage(" ".join(["1234"] * 30))  # long but no letters
    assert not is_garbage("revenue grew strongly in the year " * 5)


def test_table_to_text_drops_empty_rows():
    rows = [["Metric", "FY24"], [None, ""], ["Revenue", "100\n200"]]
    assert table_to_text(rows) == "| Metric | FY24 |\n| Revenue | 100 200 |"


def test_split_table_repeats_header():
    text = "\n".join(["| h1 | h2 |"] + [f"| row{i} | a b c d |" for i in range(20)])
    parts = split_table(text, size=20)
    assert len(parts) > 1
    assert all(p.startswith("| h1 | h2 |") for p in parts)


def make_pdf(path, pages: list[str]):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(40, 40, 550, 800), text, fontsize=9)
    doc.save(path)


def test_extract_chunks_never_cross_pages_and_skip_empty(tmp_path):
    pdf = tmp_path / "acme_FY24.pdf"
    page1 = "alpha " * 120
    page3 = "omega " * 120
    make_pdf(pdf, [page1, "", page3])  # page 2 is empty
    chunks = extract_chunks(pdf, size=50, overlap=10)

    assert {c.page for c in chunks} == {1, 3}  # empty page 2 produces nothing
    for c in chunks:
        # a chunk from page 1 holds only page-1 words (no leakage across pages)
        assert ("alpha" in c.text) != ("omega" in c.text)
        assert (c.page == 1) == ("alpha" in c.text)
        assert (c.company, c.fiscal_year, c.doc_id) == ("acme", 2024, "acme_FY24")
