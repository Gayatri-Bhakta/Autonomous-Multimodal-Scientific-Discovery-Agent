# Literature Retriever (Member 3, Week 2)

`src/rag/retriever.py` turns a research topic into a short, ranked, citable context block for the Hypothesis agent (Member 2). It queries the team's ChromaDB store, `ScientificVectorDB` in `src/rag/vector_db.py`.

## How a query works

1. **Vector search:** `ScientificVectorDB.search()` over the paper chunks stored in ChromaDB (`data/vector_store`, all-MiniLM-L6-v2 embeddings).
2. **Cosine similarity:** computed from the Chroma distance. The collection uses L2 distance on unit-length vectors, so cosine = 1 − distance / 2 (collections in cosine space use 1 − distance).
3. **Score threshold:** chunks with cosine below `min_score` (default **0.20**) are discarded.
4. **Metadata filters:** `year_from`, `year_to`, `categories` (any match, e.g. `["cs.AI"]` or MeSH terms), `sources` (`["arxiv"]` / `["pubmed"]`).
5. **Best chunk per paper**, then the top `top_k` papers, highest similarity first.
6. **Formatting** for the LLM prompt, capped at 4,000 characters:

```
[Paper 1: Title (First Author et al., 2026)]
ID: arxiv:2610.12445v1 | Similarity: 0.57
Abstract snippet: ...
```

## Usage

```python
from src.rag.retriever import get_relevant_literature, format_context, retrieve_for_hypothesis

papers = get_relevant_literature("deep learning for drug discovery", top_k=5)
papers = get_relevant_literature("agent safety", top_k=3, year_from=2026, categories=["cs.AI"])
prompt_context = format_context(papers)

# For the Hypothesis agent: context + the only paper IDs it may cite
bundle = retrieve_for_hypothesis("antimicrobial resistance", top_k=5)
bundle["context"], bundle["valid_paper_ids"], bundle["papers"]
```

Each result: `rank, paper_id, title, authors, year, source, categories, url, similarity, snippet`.

## Command line

```bash
python -m src.rag.retriever "deep learning drug discovery" --top-k 3
python -m src.rag.retriever "agent safety" --categories cs.AI --year-from 2026 --min-score 0.1
```

## Tests

```bash
python -m pytest tests/test_retriever.py -v
```

The tests build a throwaway ChromaDB store in a temporary folder (the real `data/vector_store` is never touched). They use 6 mock papers and 6 mock queries with known answers, and assert 100% top-1 accuracy. They also cover thresholding, year/tag/source filters, cosine conversion, formatting and the context budget.

## Note on embeddings

If `sentence-transformers` cannot load (for example on Intel Macs, where PyTorch is capped at 2.2), `vector_db.py` falls back to a word-hash embedding. Retrieval still works, but it matches words rather than meaning, so vague queries score lower. Machines with the real MiniLM model get sharper results.
