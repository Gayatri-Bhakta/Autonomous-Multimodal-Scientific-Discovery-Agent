import hashlib
import json
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAPERS_FILE = PROJECT_ROOT / "data" / "sample_papers.json"
VECTOR_STORE_DIR = PROJECT_ROOT / "data" / "vector_store"

COLLECTION_NAME = "scientific_papers"
MODEL_NAME = "all-MiniLM-L6-v2"

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
)

_collection = None


def get_collection():
    """Open or create the persistent ChromaDB collection."""
    global _collection

    if _collection is None:
        VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        embedding_function = SentenceTransformerEmbeddingFunction(
            model_name=MODEL_NAME
        )

        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_function,
        )

    return _collection


def add_papers(papers: list[dict[str, Any]]) -> int:
    """Split papers into chunks and store them in ChromaDB."""
    ids = []
    documents = []
    metadatas = []

    for paper in papers:
        paper_id = str(paper.get("paper_id") or paper.get("source_id") or "")
        title = str(paper.get("title") or "").strip()
        abstract = str(paper.get("abstract") or "").strip()

        text = f"{title}\n\n{abstract}".strip()
        if not paper_id or not text:
            continue

        chunks = _splitter.split_text(text)

        for chunk_number, chunk in enumerate(chunks):
            chunk_id = hashlib.sha256(
                f"{paper_id}:{chunk_number}".encode("utf-8")
            ).hexdigest()

            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append(
                {
                    "paper_id": paper_id,
                    "title": title,
                    "source": str(paper.get("source") or "unknown"),
                    "authors": ", ".join(paper.get("authors") or []),
                    "published_date": str(paper.get("published_date") or ""),
                    "url": str(paper.get("url") or ""),
                    "categories": ", ".join(paper.get("categories") or []),
                    "chunk_number": chunk_number,
                }
            )

    if ids:
        get_collection().upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    return len(ids)


def load_papers_from_json(json_path: Path = PAPERS_FILE) -> int:
    """Read Member 3's paper list from a JSON file and store it."""
    with json_path.open("r", encoding="utf-8") as file:
        papers = json.load(file)

    if not isinstance(papers, list):
        raise ValueError("The papers JSON file must contain a list of papers.")

    return add_papers(papers)


def query_papers(query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Return the most relevant paper chunks for a search query."""
    if not query_text.strip():
        return []
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    collection = get_collection()
    if collection.count() == 0:
        return []

    matches = collection.query(
        query_texts=[query_text],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    results = []
    for document, metadata, distance in zip(
        matches["documents"][0],
        matches["metadatas"][0],
        matches["distances"][0],
    ):
        results.append(
            {
                "text": document,
                "metadata": metadata,
                "distance": distance,
            }
        )

    return results

class ScientificVectorDB:
    """Class interface used by the rest of the project."""

    def __init__(self):
        self.collection = get_collection()

    def add_papers(self, papers: list[dict[str, Any]]) -> int:
        return add_papers(papers)

    def load_from_json(self, json_path: str = str(PAPERS_FILE)) -> int:
        return load_papers_from_json(Path(json_path))

    def count(self) -> int:
        return self.collection.count()

    def search(
        self, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        return query_papers(query, top_k)


if __name__ == "__main__":
    chunk_count = load_papers_from_json()
    print(f"Stored {chunk_count} paper chunks.")

    for result in query_papers("AI time horizons and benchmarks", top_k=3):
        print(f"\nTitle: {result['metadata']['title']}")
        print(result["text"])
