# PDF Figure Extractor (Member 3, Week 3)

`src/ingestion/figure_extractor.py` pulls the figures (charts, plots, diagrams) out of paper PDFs, so the vision-language chart reader (Member 2) can read the numbers in them.

## Output

```
data/extracted_figures/<paper_id>/fig_1.png
data/extracted_figures/<paper_id>/fig_2.png
data/extracted_figures/<paper_id>/figures.json   # caption, page, size, position of each figure
```

Each entry in `figures.json`: `paper_id, index, page, path, width, height, bbox, caption, figure_number, kind, parts`.

## How it works

| Step | What happens |
| --- | --- |
| 1. Find images | PyMuPDF lists every image drawn on each page, with its position and pixel size. |
| 2. Filter noise | Images smaller than 300 px on both sides (logos, icons, headshots) are dropped, as is any image repeated on later pages (journal logos). |
| 3. Merge strips | Papers often store one figure as several stacked image strips. Strips in the same column, 40 pt or less apart, with no caption or body-text paragraph between them, are merged into one figure. Small-print labels (prompts, legends, model names) stay inside the figure. Body-text size is measured across the whole document. |
| 4. Vector charts | Many arXiv charts are drawn with lines and shapes, not images. When a "Figure X:" caption has no image, the drawings next to it are cropped; short, wide charts are rendered sharper (up to 4×) to reach the minimum size. |
| 5. Pair captions | Each figure is paired with the closest "Figure X:" / "Fig. X." caption below it (or above it). Appendix numbers ("Figure A6:") and sub-figure labels ("(a) (b) Figure 6:") are recognised. |
| 6. Save | Figures are rendered at close to their original resolution and saved as PNG in reading order. |

Robustness: password-protected PDFs are skipped (returns `[]`), PDFs with only an owner password are still read, broken files return `[]`, and a re-run clears that paper's old `fig_*.png` and `figures.json` first.

## Results on real papers

From `python examples/extract_sample_figures.py` (summary in `data/sample_figure_extractions.json`):

| Paper | Figures | With caption |
| --- | --- | --- |
| arXiv 2610.12466 (AI time horizons) | 9 | 9 |
| arXiv 2610.12463 (Reactive containment to proactive assurance) | 1 | 1 |
| arXiv 2610.12452 (BrickBench) | 13 | 13 |

On BrickBench, the first version produced 17 loose image strips with 4 captions. The current version produces 13 complete figures (Figures 1–6 and A1–A8, except A3), all with captions.

## Usage

```bash
python -m src.ingestion.figure_extractor paper.pdf --paper-id arxiv:2610.12452v1
python examples/extract_sample_figures.py            # downloads 3 sample arXiv papers
```

```python
from src.ingestion.figure_extractor import extract_figures, load_extracted_figures

figures = extract_figures("paper.pdf", paper_id="arxiv:2610.12452v1")

# For the chart reader (Member 2): every saved figure with its caption
for fig in load_extracted_figures():
    fig["path"], fig["caption"], fig["paper_id"], fig["figure_number"]
```

## Tests

```bash
python -m pytest tests/test_figure_extractor.py -v
```

24 tests on small generated PDFs: logo filtering, caption pairing (above / below / appendix / sub-figure labels), strip merging with small-print labels, vector charts, password-protected PDFs, stale-file cleanup and the requirements file format.

## Known limits

- A figure made of a vector chart next to an image (e.g. "(a)" drawn, "(b)" an image) is saved as the image part only.
- Captions placed beside a figure, rather than above or below it, are not paired.
- PubMed papers often have no free PDF; arXiv PDFs work best.

## Figure report

`src/ingestion/figure_report.py` summarises every figure extracted so far, so we can check the extractor at a glance.

```bash
python -m src.ingestion.figure_report          # table per paper
python -m src.ingestion.figure_report --json   # same summary as JSON
```

Example output on the 3 sample papers:

| Paper | Figures | Captioned | Vector |
| --- | --- | --- | --- |
| arxiv:2610.12452v1 | 13 | 13 | 8 |
| arxiv:2610.12463v1 | 1 | 1 | 1 |
| arxiv:2610.12466v1 | 9 | 9 | 9 |

23 figures from 3 papers, 23 with captions (100%).

For the chart reader (Member 2), `figures_for_chart_reader(figures)` returns only figures that have a caption and whose image file exists:

```python
from src.ingestion.figure_extractor import load_extracted_figures
from src.ingestion.figure_report import figures_for_chart_reader

for fig in figures_for_chart_reader(load_extracted_figures()):
    fig["path"], fig["caption"], fig["paper_id"]
```

Tests: `python -m pytest tests/test_figure_report.py -v` (4 tests).
