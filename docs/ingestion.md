# Data Ingestion (Member 3)

Pulls recent papers from **arXiv** and **PubMed** and normalises them into one schema.

| File | Purpose |
|---|---|
| `src/ingestion/schema.py` | `Paper` dataclass (unified schema), dedup, save/load JSON |
| `src/ingestion/arxiv_scraper.py` | arXiv by category + date range (`arxiv` client) |
| `src/ingestion/pubmed_scraper.py` | PubMed via `Entrez.esearch` + `Entrez.efetch` (Biopython) |
| `src/ingestion/pipeline.py` | Runs both, de-duplicates, writes `data/sample_scraped_papers.json` |
| `tests/test_ingestion.py` | Offline tests (APIs mocked) |

## Unified schema
`paper_id, source, source_id, title, abstract, authors[], published_date (YYYY-MM-DD), url, pdf_url, doi, categories[], journal, retrieved_at`

## Run
```bash
pip install -r requirements-ingestion.txt
cp .env.example .env          # add your email
python -m src.ingestion.pipeline --categories cs.AI q-bio.BM --query "machine learning drug discovery" --arxiv-max 5 --pubmed-max 5
pytest tests/test_ingestion.py -v
```

## For Member 4 (vector DB)
```python
from src.ingestion import load_papers
papers = load_papers("data/sample_scraped_papers.json")
text = f"{p.title}\n\n{p.abstract}"   # embed this; store p.to_dict() as metadata
```
