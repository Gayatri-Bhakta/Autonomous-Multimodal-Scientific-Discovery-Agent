# Autonomous Multimodal Scientific Discovery Agent

An enterprise-grade autonomous AI researcher framework powered by Large Language Models (LLMs) and Multi-Agent Orchestration. The system autonomously retrieves scientific papers, analyzes literature, formulates testable hypotheses, executes simulated experimental code, and validates research metrics without human intervention.

Developed for **Zaalima Development Pvt. Ltd.** (Enterprise-Level Project | Data Science & Machine Learning).

---

## 🚀 Key Capabilities

- **Autonomous Literature Retrieval:** Ingestion pipelines connecting directly to the **arXiv** and **PubMed** APIs.
- **Multi-Agent Orchestration:** Linear state machine engineered using **LangGraph** with a centralized state dictionary and immutable audit logging.
- **Literature Reviewer Agent:** Synthesizes state-of-the-art papers, analyzes methodology, and pinpoints research bottlenecks.
- **Hypothesis Generator Agent:** Formulates novel, falsifiable scientific hypotheses grounded in peer-reviewed literature.
- **Code Executor Agent:** Automatically generates Python benchmark experiments and executes them in an isolated runtime environment with metric verification.
- **Vector Search Engine:** Ingests paper embeddings into a searchable vector database (**ChromaDB**) for semantic literature retrieval.

---

## 🏛 Multi-Agent Architecture

```
[arXiv & PubMed APIs] ──> [Data Ingestion & Dedup] ──> [Scientific Vector DB]
                                                                │
                                                                ▼
[START] ──> [Literature Reviewer] ──> [Hypothesis Generator] ──> [Code Executor] ──> [END]
                     │                          │                         │
                     └──────────────────────────┴─────────────────────────┘
                                                  │
                                                  ▼
                                       [Shared State & Audit Logs]
```

Detailed technical specifications and state contracts are available in [`docs/role_specifications.md`](docs/role_specifications.md).

---

## 📂 Project Structure

```
Autonomous-Multimodal-Scientific-Discovery-Agent/
├── .github/
│   └── pull_request_template.md    # Pull request submission template
├── data/
│   ├── sample_papers.json          # Pre-ingested arXiv and PubMed sample papers
├── docs/
│   ├── role_specifications.md      # Multi-Agent architecture & state contracts
│   ├── ingestion.md                # Data ingestion pipelines documentation
│   └── pr_review_standards.md      # Team PR review guidelines
├── src/
│   ├── __init__.py
│   ├── orchestrator.py             # LangGraph state machine & multi-agent pipeline
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── literature_agent.py     # Literature Reviewer Agent
│   │   ├── hypothesis_agent.py     # Hypothesis Generator Agent
│   │   └── code_executor_agent.py  # Code Executor Agent
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── arxiv_scraper.py        # arXiv API client
│   │   ├── pubmed_scraper.py       # PubMed API client
│   │   ├── pipeline.py             # Unified ingestion & deduplication
│   │   ├── schema.py               # Normalized Paper dataclass
│   │   └── state.py                # Incremental crawl tracking
│   └── rag/
│       ├── __init__.py
│       └── vector_db.py            # Scientific Vector DB & semantic retrieval
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest environment setup
│   ├── test_agents.py              # Sub-agent unit tests
│   ├── test_orchestrator.py        # LangGraph pipeline integration tests
│   ├── test_scrapers.py            # Scraper schema tests
│   └── test_vector_db.py           # Vector database search tests
├── .gitignore
├── requirements.txt                # Unified project dependencies
└── README.md
```
---

## 🛠 Setup & Installation

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/Gayatri-Bhakta/Autonomous-Multimodal-Scientific-Discovery-Agent.git
cd Autonomous-Multimodal-Scientific-Discovery-Agent

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Multi-Agent Pipeline
```bash
python -m src.orchestrator
```

### 3. Run the Test Suite
```bash
pytest -v
```

---

