"""
PDF Figure Extractor (Member 3 - Week 3: "Giving the AI Eyes").

Finds the figures (charts, plots, diagrams) inside a paper PDF, drops logos and
tiny icons, pairs each figure with its "Figure X:" / "Fig. X." caption, and saves
it as a PNG for the Vision-Language Model chart reader (Member 2):

    data/extracted_figures/<paper_id>/fig_1.png
    data/extracted_figures/<paper_id>/fig_2.png
    data/extracted_figures/<paper_id>/figures.json   <- captions, pages, sizes

Usage (from repo root):
    python -m src.ingestion.figure_extractor path/to/paper.pdf --paper-id arxiv:2610.12445v1

    from src.ingestion.figure_extractor import extract_figures
    figures = extract_figures("paper.pdf", paper_id="arxiv:2610.12445v1")
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:                                  # PyMuPDF >= 1.24 prefers `import pymupdf`
    import pymupdf as fitz
except ImportError:                   # older releases only provide `fitz`
    import fitz  # type: ignore

logger = logging.getLogger(__name__)

DEFAULT_OUT_DIR = Path("data/extracted_figures")
MIN_WIDTH = 300                       # pixels - smaller images are logos / icons / headshots
MIN_HEIGHT = 300
RENDER_ZOOM = 2.0                     # render figures at 2x (144 dpi) for the VLM
CAPTION_MAX_GAP = 120                 # points between a figure and its caption

CAPTION_RE = re.compile(r"^\s*(?:Figure|Fig\.?)\s*(\d+)\s*[:.]", re.IGNORECASE)

Rect = Tuple[float, float, float, float]


@dataclass
class Figure:
    """One extracted figure."""
    paper_id: str
    index: int                        # fig_<index>.png, in reading order
    page: int                         # 1-based page number
    path: str                         # saved PNG
    width: int                        # saved image size in pixels
    height: int
    bbox: List[float]                 # position on the page (points): x0, y0, x1, y1
    caption: str = ""
    figure_number: Optional[int] = None   # the "X" in "Figure X:"


# ------------------------------------------------------------------ helpers
def safe_folder_name(paper_id: str) -> str:
    """'arxiv:2610.12445v1' -> 'arxiv_2610.12445v1' (safe on every OS)."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(paper_id)).strip("._")
    return name or "paper"


def clean_caption(text: str) -> str:
    return " ".join((text or "").split())


def find_captions(page: Any) -> List[Tuple[Rect, str, int]]:
    """Text blocks on the page that start with 'Figure X:' / 'Fig. X.'."""
    captions = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text = block[:5]
        text = clean_caption(text)
        match = CAPTION_RE.match(text)
        if match:
            captions.append(((x0, y0, x1, y1), text, int(match.group(1))))
    return captions


def horizontal_overlap(a: Rect, b: Rect) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))


def pair_caption(bbox: Rect, captions: List[Tuple[Rect, str, int]],
                 used: set) -> Optional[Tuple[Rect, str, int]]:
    """
    The caption closest to the figure, preferring one just BELOW it (the usual
    layout), then one just ABOVE it. Captions must overlap the figure horizontally.
    """
    best, best_gap = None, None
    for cap in captions:
        if id(cap) in used:
            continue
        crect = cap[0]
        if horizontal_overlap(bbox, crect) <= 0:
            continue
        below_gap = crect[1] - bbox[3]                 # caption top - figure bottom
        above_gap = bbox[1] - crect[3]                 # figure top - caption bottom
        if -5 <= below_gap <= CAPTION_MAX_GAP:
            gap = below_gap
        elif -5 <= above_gap <= CAPTION_MAX_GAP:
            gap = above_gap + CAPTION_MAX_GAP          # rank captions above as 2nd choice
        else:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = cap, gap
    return best


def image_placements(page: Any) -> List[Dict[str, Any]]:
    """Raster images drawn on the page, with native pixel size and page position."""
    placements = []
    for info in page.get_image_info(xrefs=True):
        bbox = tuple(info.get("bbox") or ())
        if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        placements.append({
            "xref": info.get("xref", 0),
            "bbox": bbox,
            "width": int(info.get("width", 0)),         # native pixels of the image
            "height": int(info.get("height", 0)),
        })
    placements.sort(key=lambda p: (p["bbox"][1], p["bbox"][0]))   # reading order
    return placements


def is_big_enough(width: int, height: int,
                  min_width: int = MIN_WIDTH, min_height: int = MIN_HEIGHT) -> bool:
    return width >= min_width and height >= min_height


# ---------------------------------------------------------------- main API
def extract_figures(
    pdf_path: str | Path,
    paper_id: Optional[str] = None,
    out_dir: str | Path = DEFAULT_OUT_DIR,
    min_width: int = MIN_WIDTH,
    min_height: int = MIN_HEIGHT,
    zoom: float = RENDER_ZOOM,
) -> List[Dict[str, Any]]:
    """
    Extract the figures from one PDF.

    Returns a list of dicts (paper_id, index, page, path, width, height, bbox,
    caption, figure_number) and writes the PNGs plus a figures.json manifest to
    <out_dir>/<paper_id>/.
    """
    pdf_path = Path(pdf_path)
    paper_id = paper_id or pdf_path.stem
    target = Path(out_dir) / safe_folder_name(paper_id)

    figures: List[Figure] = []
    seen_xrefs = set()
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        logger.error("Cannot open %s: %s", pdf_path, exc)
        return []

    with doc:
        for page_number, page in enumerate(doc, start=1):
            captions = find_captions(page)
            used_captions: set = set()
            for img in image_placements(page):
                # 1. noise filter: logos, icons and headshots are small images
                if not is_big_enough(img["width"], img["height"], min_width, min_height):
                    continue
                # the same image (e.g. a journal logo) repeated on every page
                if img["xref"] and img["xref"] in seen_xrefs:
                    continue
                seen_xrefs.add(img["xref"])

                # 2. render exactly the area the figure occupies on the page
                bbox = img["bbox"]
                clip = fitz.Rect(bbox) & page.rect
                if clip.is_empty:
                    continue
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
                if not is_big_enough(pix.width, pix.height, min_width, min_height):
                    # drawn small on the page but stored large: keep native resolution
                    try:
                        pix = fitz.Pixmap(doc, img["xref"])
                        if pix.n - pix.alpha >= 4:          # CMYK -> RGB for PNG
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                    except Exception:
                        continue

                # 3. pair with "Figure X:" caption
                cap = pair_caption(bbox, captions, used_captions)
                if cap:
                    used_captions.add(id(cap))

                # 4. save
                index = len(figures) + 1
                target.mkdir(parents=True, exist_ok=True)
                path = target / f"fig_{index}.png"
                pix.save(str(path))
                figures.append(Figure(
                    paper_id=paper_id, index=index, page=page_number, path=str(path),
                    width=pix.width, height=pix.height,
                    bbox=[round(v, 1) for v in bbox],
                    caption=cap[1] if cap else "",
                    figure_number=cap[2] if cap else None,
                ))

    result = [asdict(f) for f in figures]
    if result:
        (target / "figures.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info("%s: %d figure(s) extracted -> %s", paper_id, len(result), target)
    return result


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Extract figures + captions from a paper PDF")
    ap.add_argument("pdf", help="path to a PDF file")
    ap.add_argument("--paper-id", default=None, help="e.g. arxiv:2610.12445v1")
    ap.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    ap.add_argument("--min-size", type=int, default=MIN_WIDTH,
                    help="minimum width and height in pixels (default 300)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    figs = extract_figures(args.pdf, args.paper_id, args.out, args.min_size, args.min_size)
    for f in figs:
        caption = f["caption"][:80] or "(no caption found)"
        print(f"fig_{f['index']}  page {f['page']}  {f['width']}x{f['height']}  {caption}")
    if not figs:
        print("No figures found (vector-drawn charts are added in the next step).")


if __name__ == "__main__":
    main()
