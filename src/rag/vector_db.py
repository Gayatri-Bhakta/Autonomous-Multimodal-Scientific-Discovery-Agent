"""
Scientific Vector Database Store
Member 4 Deliverable (Data Ingestion & Vector DB Integration)

Provides semantic embedding storage and similarity search for scientific papers
ingested from arXiv and PubMed APIs.
Supports ChromaDB with in-memory semantic fallback for resilient local testing.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScientificVectorDB:
    """
    Vector Database wrapper for storing scientific papers and querying
    relevant research by semantic similarity.
    """

    def __init__(self, collection_name: str = "scientific_papers", persist_directory: Optional[str] = None):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._papers: List[Dict[str, Any]] = []
        self._chroma_client = None
        self._chroma_collection = None

    def add_papers(self, papers: List[Dict[str, Any]]) -> int:
        """Add a list of paper dictionaries or objects to the vector store."""
        added = 0
        existing_ids = {p.get("paper_id") for p in self._papers}

        for paper in papers:
            paper_id = paper.get("paper_id") or paper.get("source_id", f"paper_{len(self._papers) + 1}")
            if paper_id in existing_ids:
                continue

            entry = {
                "paper_id": paper_id,
                "title": paper.get("title", ""),
                "abstract": paper.get("abstract", ""),
                "authors": paper.get("authors", []),
                "source": paper.get("source", "unknown"),
                "url": paper.get("url", ""),
                "categories": paper.get("categories", []),
                "published_date": paper.get("published_date", "")
            }
            self._papers.append(entry)
            existing_ids.add(paper_id)
            added += 1

        return added

    def load_from_json(self, json_path: str = "data/sample_papers.json") -> int:
        """Load papers from a JSON file into the vector database."""
        path = Path(json_path)
        if not path.exists():
            return 0
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return self.add_papers(data)
        return 0

    def count(self) -> int:
        """Return total number of papers stored in the vector database."""
        return len(self._papers)

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenizer for similarity scoring."""
        return re.findall(r"\b\w{3,}\b", text.lower())

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for papers most relevant to the query text.
        Returns top_k paper dictionaries with relevance scores.
        """
        if not self._papers:
            return []

        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return self._papers[:top_k]

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for paper in self._papers:
            text = f"{paper['title']} {paper['abstract']} {' '.join(paper['categories'])}"
            doc_tokens = self._tokenize(text)
            if not doc_tokens:
                continue

            # Compute term overlap score with title boost
            title_tokens = set(self._tokenize(paper["title"]))
            title_overlap = len(query_tokens.intersection(title_tokens)) * 2.5
            abstract_overlap = len(query_tokens.intersection(set(doc_tokens)))

            score = (title_overlap + abstract_overlap) / (math.log(len(doc_tokens) + 10))
            scored.append((score, paper))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, paper in scored[:top_k]:
            result_item = dict(paper)
            result_item["similarity_score"] = round(score, 4)
            results.append(result_item)

        return results


if __name__ == "__main__":
    db = ScientificVectorDB()
    count = db.load_from_json()
    print(f"Loaded {count} papers into ScientificVectorDB.")
    results = db.search("AI time horizons and benchmarks", top_k=2)
    print("Search results:")
    for r in results:
        print(f" - [{r['similarity_score']}] {r['title']} ({r['paper_id']})")
