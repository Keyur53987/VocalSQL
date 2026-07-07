# VocalSQL — Natural Language to SQL

🚀 **Live:** [https://vocalsql.onrender.com/](https://vocalsql.onrender.com/)

> **Production-grade** VocalSQL system powered by **LangGraph**, **RAG**, and **Groq** (free tier).
> Convert natural language questions into accurate SQL queries with built-in self-correction, validation, and anti-hallucination layers.

## ✨ Features

- 🧠 **LangGraph State Machine** — 7-node agentic pipeline with self-correction loops
- 📚 **RAG-Powered Context** — Schema & few-shot retrieval via ChromaDB (local, free)
- 🤖 **Groq Llama 3.3** — Blazing fast, free-tier LLM with deterministic output
- 🔍 **Confidence & Ambiguity X-Ray** — Dual-path confidence scoring with interactive clarification UI
- ✅ **9-Layer Anti-Hallucination** — Syntax validation, schema compliance, safety guards
- 🔄 **Self-Correction Loop** — Automatic SQL repair (up to 3 retries)
- 🗄️ **Multi-Database Support** — Connect any SQLite, PostgreSQL, or MySQL database
- 🌐 **Beautiful Web UI** — Dark glassmorphism design with real-time results
- 📊 **Complex Demo Database** — 15-table e-commerce schema with 2000+ records
- 📝 **Feedback Learning** — Submit corrections to improve future queries

## 🚀 Quick Start

### 1. Get a Free Groq API Key

Visit [Groq Console](https://console.groq.com/keys) and create a free API key.

### 2. Setup

```bash
# Clone/navigate to the project
cd nl2sql

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env and add your GROQ_API_KEY
```

### 3. Initialize Demo Database

```bash
python scripts/init_demo_db.py
```

### 4. Run the Server

```bash
python -m app.main
# Or: uvicorn app.main:app --reload --port 8000
```

### 5. Open the UI

Navigate to **http://localhost:8000** in your browser.

## 🏗️ Architecture

```mermaid
graph TD
    User([User Query]) --> Router
    Router --> SchemaR[Schema Retriever <br/><i>RAG</i>]
    Router --> FewShotR[Few-Shot Retriever <br/><i>RAG</i>]
    SchemaR --> Generator
    FewShotR --> Generator
    Generator[SQL Generator <br/><i>Groq Llama 3</i>] --> Analyzer[Confidence Analyzer]
    Analyzer -- "High Confidence" --> Validator[SQL Validator]
    Analyzer -- "Low Confidence" --> Clarify([Ask for Clarification])
    Clarify -. "Updated Query" .-> Router
    Validator -- "Valid" --> Executor[SQL Executor]
    Validator -- "Invalid" --> Corrector[SQL Corrector]
    Corrector --> Validator
    Executor --> Formatter[Response Formatter <br/><i>Groq Llama 3</i>]
    Formatter --> Out([Natural Language Answer <br/>& Data Table])
```

### Anti-Hallucination Layers

| # | Technique | Type | Cost |
|---|---|---|---|
| 1 | Schema scoping via RAG | Preventive | ~50ms |
| 2 | Few-shot examples | Preventive | ~30ms |
| 3 | Temperature 0.0 | Preventive | Free |
| 4 | Structured prompts | Preventive | Free |
| 5 | sqlglot syntax check | Detective | <5ms |
| 6 | Schema compliance | Detective | <1ms |
| 7 | Safety guards | Detective | <1ms |
| 8 | Self-correction loop | Corrective | ~500ms/retry |
| 9 | Graceful failure | Fallback | Free |

## 📁 Project Structure

```
nl2sql/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py             # Configuration (pydantic-settings)
│   ├── services.py           # Service registry (singletons)
│   ├── graph/
│   │   ├── state.py          # LangGraph state definition
│   │   ├── workflow.py       # Graph assembly & compilation
│   │   └── nodes/            # Pipeline nodes (router, generator, validator, etc.)
│   ├── rag/
│   │   ├── schema_indexer.py # Schema → ChromaDB indexing
│   │   └── fewshot_store.py  # Few-shot example store
│   ├── db/
│   │   ├── connection.py     # Multi-DB connection manager
│   │   └── introspector.py   # Schema metadata extraction
│   ├── models/               # Pydantic request/response models
│   ├── utils/                # Security & caching utilities
│   └── static/               # Web UI (HTML/CSS/JS)
├── data/
│   ├── few_shots.json        # Curated NL→SQL examples
│   └── schema_descriptions.json  # Table/column descriptions
├── scripts/
│   └── init_demo_db.py       # Demo database initialization
└── requirements.txt
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/query` | Convert NL to SQL and execute |
| `POST` | `/api/feedback` | Submit a correction |
| `GET` | `/api/databases` | List registered databases |
| `POST` | `/api/databases` | Register a new database |
| `DELETE` | `/api/databases/{id}` | Remove a database |
| `POST` | `/api/databases/{id}/reindex` | Re-index schema |
| `GET` | `/api/health` | Health check |

## 🗄️ Adding Your Own Database

### Via the UI
Click **Databases** in the header → fill in the connection string → **Add Database**.

### Via API
```bash
curl -X POST http://localhost:8000/api/databases \
  -H "Content-Type: application/json" \
  -d '{"db_id": "my_db", "connection_string": "sqlite:///path/to/my.db", "name": "My Database"}'
```

### Connection String Examples
- **SQLite**: `sqlite:///path/to/database.db`
- **PostgreSQL**: `postgresql://user:pass@host:5432/dbname`
- **MySQL**: `mysql+pymysql://user:pass@host:3306/dbname`

> For PostgreSQL: `pip install psycopg2-binary`
> For MySQL: `pip install pymysql`

## ⚙️ Configuration

All settings are in `.env`:

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | (required) | Groq API key |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | LLM model name |
| `LLM_TEMPERATURE` | `0.0` | Generation temperature |
| `MAX_CORRECTION_RETRIES` | `3` | Max self-correction attempts |
| `QUERY_TIMEOUT_SECONDS` | `10` | SQL execution timeout |
| `SCHEMA_TOP_K` | `5` | Number of tables to retrieve |
| `FEWSHOT_TOP_K` | `3` | Number of examples to retrieve |

## 📄 License

MIT
