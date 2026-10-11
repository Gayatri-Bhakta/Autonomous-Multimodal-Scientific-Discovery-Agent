"""
Combined ingestion pipeline: arXiv + PubMed -> one de-duplicated JSON file.

This is what produces the Week 1 deliverable data/sample_scraped_papers.json
(5 arXiv + 5 PubMed) and what Member 4 will call to feed the vector DB.

Usage (from repo root):
    python -m src.ingestion.pipeline --arxiv-max 5 --pubmed-max 5
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from src.ingestion.arxiv_scraper import ArxivScraper
from src.ingestion.pubmed_scraper import PubMedScraper
from src.ingestion.schema import Paper, deduplicate, save_papers

logger = logging.getLogger(__name__)


def run_ingestion(
    arxiv_categories: List[str],
    pubmed_query: str,
    days: int = 30,
    arxiv_max: int = 5,
    pubmed_max: int = 5,
) -> List[Paper]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    arxiv_papers = ArxivScraper().search(arxiv_categories, start, end, arxiv_max)
    pubmed_papers = PubMedScraper().search(pubmed_query, start, end, pubmed_max)
    papers = deduplicate(arxiv_papers + pubmed_papers)
    logger.info("Ingestion done: %d arXiv + %d PubMed = %d unique",
                len(arxiv_papers), len(pubmed_papers), len(papers))
    return papers


def main() -> None:
    ap = argparse.ArgumentParser(description="Run arXiv + PubMed ingestion")
    ap.add_argument("--categories", nargs="+", default=["cs.AI", "q-bio.BM"])
    ap.add_argument("--query", default="machine learning drug discovery")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--arxiv-max", type=int, default=5)
    ap.add_argument("--pubmed-max", type=int, default=5)
    ap.add_argument("--out", default="data/sample_scraped_papers.json")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    papers = run_ingestion(args.categories, args.query, args.days,
                           args.arxiv_max, args.pubmed_max)
    path = save_papers(papers, args.out)
    print(f"Saved {len(papers)} papers -> {path}")


if __name__ == "__main__":
    main()
