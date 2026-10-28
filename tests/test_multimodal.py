"""
Multimodal ingestion QA (Member 5, Week 3).

Independent checks on the "Giving the AI Eyes" pipeline:

  PDF  ->  figure_extractor (Member 3)  ->  PNG files + figures.json  ->  chart_reader (Member 2)

Part A tests the hand-off the chart reader relies on (what the extractor promises).
Part B keeps regression tests for two bugs found in QA and fixed by Member 3.
Part C checks data/sample_chart_extractions.json once Member 2 pushes it (skipped until then).

All tests are offline and use small synthetic PDFs built with PyMuPDF.
The whole file is skipped if src/ingestion/figure_extractor.py or PyMuPDF is not available.
Run:  python -m pytest tests/test_multimodal.py -v
"""
import json
from pathlib import Path

import pytest

extractor = pytest.importorskip("src.ingestion.figure_extractor")  # skips if the module or PyMuPDF is missing
fitz = extractor.fitz
extract_figures = extractor.extract_figures

REQUIRED_KEYS = {
    "paper_id", "index", "page", "path", "width", "height",
    "bbox", "caption", "figure_number", "kind", "parts",
}


# ---------------------------------------------------------------------------
# Helpers: synthetic PDFs
# ---------------------------------------------------------------------------
def make_image(width, height, color=(0.2, 0.4, 0.8)):
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), 0)
    pix.set_rect(pix.irect, tuple(int(c * 255) for c in color))
    return pix


def add_image(page, rect, width, height, color=(0.2, 0.4, 0.8)):
    page.insert_image(fitz.Rect(rect), pixmap=make_image(width, height, color))


def save_pdf(doc, path):
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def three_figure_pdf(tmp_path):
    """One page, three captioned charts stacked down the page."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i, top in enumerate((50, 300, 550), start=1):
        add_image(page, (72, top, 400, top + 200), 600, 400, (0.2 * i, 0.4, 0.8))
        page.insert_text((72, top + 215), f"Figure {i}: Chart number {i}.", fontsize=10)
    return save_pdf(doc, tmp_path / "three.pdf")


# ---------------------------------------------------------------------------
# Part A: what the chart reader can rely on
# ---------------------------------------------------------------------------
def test_every_manifest_entry_has_all_fields_for_the_chart_reader(three_figure_pdf, tmp_path):
    figures = extract_figures(three_figure_pdf, "paper", out_dir=tmp_path / "out")
    assert len(figures) == 3
    for fig in figures:
        assert REQUIRED_KEYS <= set(fig), f"missing {REQUIRED_KEYS - set(fig)}"


def test_saved_images_exist_and_are_valid_pngs(three_figure_pdf, tmp_path):
    for fig in extract_figures(three_figure_pdf, "paper", out_dir=tmp_path / "out"):
        path = Path(fig["path"])
        assert path.is_file()
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        loaded = fitz.Pixmap(str(path))
        assert (loaded.width, loaded.height) == (fig["width"], fig["height"])


def test_every_image_meets_the_minimum_size(three_figure_pdf, tmp_path):
    for fig in extract_figures(three_figure_pdf, "paper", out_dir=tmp_path / "out"):
        assert fig["width"] >= 300 and fig["height"] >= 300


def test_captions_stay_with_the_right_figure(three_figure_pdf, tmp_path):
    figures = extract_figures(three_figure_pdf, "paper", out_dir=tmp_path / "out")
    assert [f["figure_number"] for f in figures] == [1, 2, 3]
    assert [f["caption"] for f in figures] == [f"Figure {i}: Chart number {i}." for i in (1, 2, 3)]


def test_figures_are_numbered_in_reading_order(tmp_path):
    """The lower figure is drawn first in the file, but must still become fig_2."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    add_image(page, (72, 450, 400, 650), 600, 400)
    page.insert_text((72, 665), "Figure 2: Lower chart.", fontsize=10)
    add_image(page, (72, 100, 400, 300), 600, 400)
    page.insert_text((72, 315), "Figure 1: Upper chart.", fontsize=10)
    pdf = save_pdf(doc, tmp_path / "order.pdf")

    figures = extract_figures(pdf, "paper", out_dir=tmp_path / "out")
    assert [f["index"] for f in figures] == [1, 2]
    assert [f["figure_number"] for f in figures] == [1, 2]
    assert [Path(f["path"]).name for f in figures] == ["fig_1.png", "fig_2.png"]


def test_manifest_on_disk_matches_what_the_loader_returns(three_figure_pdf, tmp_path):
    out = tmp_path / "out"
    returned = extract_figures(three_figure_pdf, "arxiv:1234.5678v1", out_dir=out)
    on_disk = json.loads((out / "arxiv_1234.5678v1" / "figures.json").read_text(encoding="utf-8"))
    assert on_disk == returned
    assert extractor.load_extracted_figures(out, paper_id="arxiv:1234.5678v1") == returned


def test_accented_captions_survive_the_json_round_trip(tmp_path):
    # Characters the PDF's built-in font can draw (Latin-1): plus-minus, u-umlaut, e-acute, degree.
    caption = "Figure 1: Accuracy (\u00b1 std) of the M\u00fcller caf\u00e9 model at 25\u00b0C."
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    add_image(page, (72, 100, 400, 300), 600, 400)
    page.insert_text((72, 315), caption, fontsize=10)
    pdf = save_pdf(doc, tmp_path / "accents.pdf")

    out = tmp_path / "out"
    figure = extract_figures(pdf, "p", out_dir=out)[0]
    loaded = extractor.load_extracted_figures(out)[0]
    assert figure["caption"] == caption
    assert loaded["caption"] == caption


def test_a_large_image_repeated_on_every_page_is_extracted_once(tmp_path):
    """A big journal logo in every page header must not become three figures."""
    doc = fitz.open()
    logo = make_image(500, 500, (0.9, 0.1, 0.1))
    for _ in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_image(fitz.Rect(40, 30, 240, 230), pixmap=logo)
    pdf = save_pdf(doc, tmp_path / "logo.pdf")

    figures = extract_figures(pdf, "p", out_dir=tmp_path / "out")
    assert [f["page"] for f in figures] == [1]


def test_grayscale_figure_is_extracted(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    gray = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 500, 400), 0)
    gray.set_rect(gray.irect, (120,))
    page.insert_image(fitz.Rect(72, 60, 400, 300), pixmap=gray)
    page.insert_text((72, 315), "Figure 1: A grayscale chart.", fontsize=10)
    pdf = save_pdf(doc, tmp_path / "gray.pdf")

    figures = extract_figures(pdf, "p", out_dir=tmp_path / "out")
    assert len(figures) == 1 and figures[0]["caption"].startswith("Figure 1")


def test_paper_ids_can_not_write_outside_the_output_folder(three_figure_pdf, tmp_path):
    out = tmp_path / "out"
    figures = extract_figures(three_figure_pdf, "../../escape", out_dir=out)
    assert figures
    for fig in figures:
        assert out.resolve() in Path(fig["path"]).resolve().parents
    assert not (tmp_path / "escape").exists()


def test_pdf_without_images_or_charts_returns_an_empty_list(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Only text here.")
    pdf = save_pdf(doc, tmp_path / "blank.pdf")
    assert extract_figures(pdf, "p", out_dir=tmp_path / "out") == []


# ---------------------------------------------------------------------------
# Part B: regression tests for bugs found in QA (both fixed by Member 3)
# ---------------------------------------------------------------------------
def test_encrypted_pdf_returns_empty_instead_of_crashing(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "secret")
    pdf = tmp_path / "encrypted.pdf"
    doc.save(pdf, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    assert extract_figures(pdf, "p", out_dir=tmp_path / "out") == []


def test_rerun_does_not_leave_stale_images(three_figure_pdf, tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    add_image(page, (72, 50, 400, 250), 600, 400)
    page.insert_text((72, 265), "Figure 1: Only one chart now.", fontsize=10)
    one_pdf = save_pdf(doc, tmp_path / "one.pdf")

    out = tmp_path / "out"
    extract_figures(three_figure_pdf, "paper", out_dir=out)
    figures = extract_figures(one_pdf, "paper", out_dir=out)

    files = sorted(p.name for p in (out / "paper").glob("fig_*.png"))
    assert files == [Path(f["path"]).name for f in figures]


# ---------------------------------------------------------------------------
# Part C: Member 2's chart extractions (skipped until data/sample_chart_extractions.json exists)
# ---------------------------------------------------------------------------
CHART_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_chart_extractions.json"

# Week 3 plan: chart type, axis labels/units, baseline + peak numbers, trend conclusion.
# Several key spellings are accepted; add Member 2's names here if they differ.
CHART_FIELDS = {
    "chart type": ["chart_type", "type"],
    "x-axis": ["x_axis", "x_axis_label", "x_label", "xaxis"],
    "y-axis": ["y_axis", "y_axis_label", "y_label", "yaxis"],
    "baseline": ["baseline", "baseline_values", "baseline_numbers", "baseline_value"],
    "peak": ["peak", "peak_value", "peak_values", "peak_performance"],
    "trend": ["trend", "trend_conclusion", "overall_trend", "conclusion"],
}


def _find(entry, aliases):
    """Look for any alias as a key, also inside nested dicts."""
    if isinstance(entry, dict):
        for key in aliases:
            if entry.get(key) not in (None, "", [], {}):
                return entry[key]
        for value in entry.values():
            found = _find(value, aliases)
            if found is not None:
                return found
    return None


def _load_chart_entries():
    if not CHART_FILE.exists() or CHART_FILE.stat().st_size == 0:
        pytest.skip("data/sample_chart_extractions.json not pushed yet (Member 2)")
    data = json.loads(CHART_FILE.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        data = lists[0] if lists else [data]
    return data


def test_chart_extractions_cover_at_least_three_charts():
    assert len(_load_chart_entries()) >= 3


def test_every_chart_extraction_has_the_planned_fields():
    for position, entry in enumerate(_load_chart_entries(), start=1):
        for field, aliases in CHART_FIELDS.items():
            assert _find(entry, aliases) is not None, f"chart {position}: no {field} (tried {aliases})"
