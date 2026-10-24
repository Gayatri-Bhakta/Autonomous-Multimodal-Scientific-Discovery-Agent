"""
Tests for the PDF figure extractor (Member 3 - Week 3).

Builds small synthetic "paper" PDFs with PyMuPDF (charts, a logo, captions above
and below), so no downloads are needed.

Run:  python -m pytest tests/test_figure_extractor.py -v
"""

import json

import pytest

from src.ingestion.figure_extractor import (
    CAPTION_RE,
    extract_figures,
    fitz,
    safe_folder_name,
)


def make_image(width, height, color=(0.2, 0.4, 0.8)):
    """A solid-colour RGB image of width x height pixels."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), 0)
    pix.set_rect(pix.irect, tuple(int(c * 255) for c in color))
    return pix


def add_image(page, rect, width, height, color=(0.2, 0.4, 0.8)):
    page.insert_image(fitz.Rect(rect), pixmap=make_image(width, height, color))


@pytest.fixture
def paper_pdf(tmp_path):
    """
    Page 1: journal logo (80x80 px) + Figure 1 chart (600x400 px, caption below)
    Page 2: caption ABOVE Figure 2 (500x500 px) + an uncaptioned big image
    """
    doc = fitz.open()
    p1 = doc.new_page(width=612, height=792)
    add_image(p1, (40, 30, 90, 80), 80, 80, (0.9, 0.1, 0.1))                 # logo
    p1.insert_text((72, 120), "Introduction. Deep models need lots of memory.", fontsize=10)
    add_image(p1, (72, 150, 540, 462), 600, 400)                            # Figure 1
    p1.insert_text((72, 480), "Figure 1: Accuracy versus training epochs.", fontsize=10)

    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((72, 90), "Fig. 2. Loss curves for three optimisers.", fontsize=10)
    add_image(p2, (72, 100, 400, 428), 500, 500, (0.1, 0.7, 0.3))           # Figure 2
    add_image(p2, (72, 500, 400, 700), 640, 400, (0.5, 0.5, 0.5))           # no caption
    path = tmp_path / "paper.pdf"
    doc.save(path)
    doc.close()
    return path


def test_extracts_big_figures_and_skips_logo(paper_pdf, tmp_path):
    figs = extract_figures(paper_pdf, "arxiv:1234.5678v1", out_dir=tmp_path / "out")
    assert len(figs) == 3                          # logo (80x80) filtered out
    assert all(f["width"] >= 300 and f["height"] >= 300 for f in figs)
    assert [f["page"] for f in figs] == [1, 2, 2]


def test_caption_below_is_paired(paper_pdf, tmp_path):
    fig1 = extract_figures(paper_pdf, "p1", out_dir=tmp_path / "out")[0]
    assert fig1["figure_number"] == 1
    assert fig1["caption"] == "Figure 1: Accuracy versus training epochs."


def test_caption_above_is_paired_and_uncaptioned_figure_kept(paper_pdf, tmp_path):
    figs = extract_figures(paper_pdf, "p1", out_dir=tmp_path / "out")
    assert figs[1]["figure_number"] == 2
    assert figs[1]["caption"].startswith("Fig. 2. Loss curves")
    assert figs[2]["caption"] == "" and figs[2]["figure_number"] is None


def test_files_and_manifest_are_saved(paper_pdf, tmp_path):
    out = tmp_path / "out"
    figs = extract_figures(paper_pdf, "arxiv:1234.5678v1", out_dir=out)
    folder = out / "arxiv_1234.5678v1"
    assert [p.name for p in sorted(folder.glob("fig_*.png"))] == ["fig_1.png", "fig_2.png", "fig_3.png"]
    manifest = json.loads((folder / "figures.json").read_text())
    assert manifest == figs
    saved = fitz.Pixmap(str(folder / "fig_1.png"))
    assert saved.width >= 300 and saved.height >= 300


def test_min_size_is_configurable(paper_pdf, tmp_path):
    figs = extract_figures(paper_pdf, "p1", out_dir=tmp_path / "out",
                           min_width=50, min_height=50)
    assert len(figs) == 4                          # the logo is now kept too


def test_small_on_page_but_high_resolution_image_is_kept(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    add_image(page, (72, 72, 172, 139), 900, 600)  # drawn 100x67 pt, stored 900x600 px
    pdf = tmp_path / "small_drawn.pdf"
    doc.save(pdf)
    figs = extract_figures(pdf, "p", out_dir=tmp_path / "out")
    assert len(figs) == 1 and figs[0]["width"] == 900 and figs[0]["height"] == 600


def test_pdf_without_figures_returns_empty_and_writes_nothing(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Text only. Figure 1: mentioned but not drawn.")
    pdf = tmp_path / "text_only.pdf"
    doc.save(pdf)
    out = tmp_path / "out"
    assert extract_figures(pdf, "p", out_dir=out) == []
    assert not (out / "p").exists()


def test_broken_or_missing_pdf_returns_empty(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"this is not a pdf")
    assert extract_figures(bad, out_dir=tmp_path / "out") == []
    assert extract_figures(tmp_path / "missing.pdf", out_dir=tmp_path / "out") == []


def test_caption_pattern_and_safe_folder_name():
    assert CAPTION_RE.match("Figure 3: Results").group(1) == "3"
    assert CAPTION_RE.match("Fig. 12. Ablation").group(1) == "12"
    assert CAPTION_RE.match("FIG 4: x").group(1) == "4"
    assert CAPTION_RE.match("As shown in Figure 3: x") is None    # must start the block
    assert safe_folder_name("arxiv:2610.12445v1") == "arxiv_2610.12445v1"
    assert safe_folder_name("pubmed:42827724") == "pubmed_42827724"
