"""
Tests for Scientific Vector Database (Member 4 Deliverable).
"""

import pytest
from src.rag.vector_db import ScientificVectorDB


def test_vector_db_initialization():
    db = ScientificVectorDB()
    assert db.count() == 0


def test_vector_db_add_papers():
    db = ScientificVectorDB()
    papers = [
        {
            "paper_id": "test:001",
            "title": "Scaling Transformer Memory Systems",
            "abstract": "We investigate KV cache compression techniques.",
            "categories": ["cs.AI", "cs.LG"],
        },
        {
            "paper_id": "test:002",
            "title": "Autonomous Robotics Planning",
            "abstract": "Trajectory optimization using model predictive control.",
            "categories": ["cs.RO"],
        },
    ]
    added = db.add_papers(papers)
    assert added == 2
    assert db.count() == 2


def test_vector_db_search():
    db = ScientificVectorDB()
    papers = [
        {
            "paper_id": "test:001",
            "title": "Scaling Transformer Memory Systems",
            "abstract": "We investigate KV cache compression techniques.",
            "categories": ["cs.AI", "cs.LG"],
        },
        {
            "paper_id": "test:002",
            "title": "Autonomous Robotics Planning",
            "abstract": "Trajectory optimization using model predictive control.",
            "categories": ["cs.RO"],
        },
    ]
    db.add_papers(papers)
    results = db.search("Transformer Memory Cache", top_k=1)
    assert len(results) == 1
    assert results[0]["paper_id"] == "test:001"
    assert "similarity_score" in results[0]


def test_vector_db_load_from_sample_json():
    db = ScientificVectorDB()
    count = db.load_from_json("data/sample_papers.json")
    assert count == 10
    assert db.count() == 10
