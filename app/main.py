"""
FastAPI application — serves the NL2SQL API and web UI.

Endpoints:
    POST /api/query          — Main NL2SQL pipeline
    POST /api/feedback       — Submit corrections for learning
    GET  /api/databases      — List registered databases
    POST /api/databases      — Register a new database
    DELETE /api/databases/{id} — Remove a database
    POST /api/databases/{id}/reindex — Re-index schema
    GET  /api/health         — Health check
    GET  /                   — Web UI (served from static files)
"""

import os
import json
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.models.request import QueryRequest, DatabaseRegisterRequest, FeedbackRequest
from app.models.response import QueryResponse, DatabaseInfo, HealthResponse
from app.services import (
    get_db_manager,
    get_introspector,
    get_schema_indexer,
    get_fewshot_store,
)
from app.graph.workflow import get_graph

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Application Lifecycle ────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("=" * 60)
    logger.info("🚀 NL2SQL Server starting up...")
    logger.info("=" * 60)

    # Initialize demo database if it exists
    _init_demo_database()

    yield

    # Cleanup
    logger.info("Shutting down NL2SQL Server...")
    get_db_manager().dispose_all()


def _init_demo_database():
    """Register and index the demo database on startup if it exists."""
    demo_path = settings.DEMO_DB_PATH
    if not os.path.exists(demo_path):
        logger.info(f"Demo database not found at '{demo_path}'. Auto-creating for stateless deployment...")
        from scripts.init_demo_db import main as init_db
        init_db()
        logger.info("Demo database created successfully.")

    db_manager = get_db_manager()
    abs_path = os.path.abspath(demo_path)
    conn_str = f"sqlite:///{abs_path}"

    # Register if not already
    if not db_manager.has_database("demo_ecommerce"):
        db_manager.register_database(
            db_id="demo_ecommerce",
            connection_string=conn_str,
            name="Demo E-Commerce",
            description="Complex 15-table e-commerce database with customers, products, orders, reviews, and more.",
        )
        logger.info("Registered demo e-commerce database")

    # Index schema if not already indexed
    indexer = get_schema_indexer()
    if not indexer.is_indexed("demo_ecommerce"):
        _index_database("demo_ecommerce")

    # Load few-shot examples
    fewshot_path = "./data/few_shots.json"
    if os.path.exists(fewshot_path):
        store = get_fewshot_store()
        if store.get_example_count("demo_ecommerce") == 0:
            store.load_from_file("demo_ecommerce", fewshot_path)
            logger.info("Loaded few-shot examples for demo database")


def _index_database(db_id: str):
    """Introspect and index a database's schema."""
    introspector = get_introspector()
    indexer = get_schema_indexer()

    tables_metadata = introspector.introspect(db_id)

    # Load descriptions if available
    descriptions = {}
    desc_path = "./data/schema_descriptions.json"
    if os.path.exists(desc_path):
        with open(desc_path, "r") as f:
            all_descriptions = json.load(f)
            descriptions = all_descriptions.get(db_id, {})

    indexer.index_schema(db_id, tables_metadata, descriptions)
    logger.info(f"Indexed {len(tables_metadata)} tables for database '{db_id}'")


# ── FastAPI App ──────────────────────────────────────────────────

app = FastAPI(
    title="NL2SQL — Natural Language to SQL",
    description="Production-grade NL2SQL system powered by LangGraph & RAG",
    version="1.0.0",
    lifespan=lifespan,
)


# ── API Endpoints ────────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResponse)
async def query_database(request: QueryRequest):
    """
    Convert a natural language question to SQL, execute it, and return results.
    """
    start_time = time.time()

    # Verify database exists
    db_manager = get_db_manager()
    if not db_manager.has_database(request.database_id):
        raise HTTPException(
            status_code=404,
            detail=f"Database '{request.database_id}' is not registered.",
        )

    # Run the LangGraph pipeline
    graph = get_graph()

    try:
        result = graph.invoke({
            "user_query": request.question,
            "database_id": request.database_id,
            "correction_attempts": 0,
        })
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        elapsed = (time.time() - start_time) * 1000
        return QueryResponse(
            success=False,
            question=request.question,
            error=f"Pipeline error: {str(e)}",
            execution_time_ms=round(elapsed, 1),
        )

    elapsed = (time.time() - start_time) * 1000
    final = result.get("final_response", {})

    return QueryResponse(
        success=final.get("success", False),
        question=request.question,
        generated_sql=final.get("generated_sql"),
        natural_language_response=final.get("natural_language_response"),
        results=final.get("results"),
        error=final.get("error"),
        intent=final.get("intent"),
        correction_attempts=final.get("correction_attempts", 0),
        execution_time_ms=round(elapsed, 1),
        confidence_report=final.get("confidence_report"),
        needs_clarification=final.get("needs_clarification", False),
        clarification_questions=final.get("clarification_questions"),
    )


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Submit a correct NL→SQL pair for continuous learning."""
    store = get_fewshot_store()
    store.add_example(request.database_id, request.question, request.correct_sql)
    return {"status": "ok", "message": "Feedback recorded. Thank you!"}


@app.get("/api/databases")
async def list_databases():
    """List all registered databases."""
    db_manager = get_db_manager()
    databases = db_manager.list_databases()

    result = []
    indexer = get_schema_indexer()
    for db_id, info in databases.items():
        is_connected = db_manager.test_connection(db_id)
        table_names = indexer.get_all_table_names(db_id)
        result.append(DatabaseInfo(
            db_id=db_id,
            name=info["name"],
            description=info["description"],
            is_connected=is_connected,
            table_count=len(table_names),
        ))

    return result


@app.post("/api/databases")
async def register_database(request: DatabaseRegisterRequest):
    """Register a new database connection."""
    db_manager = get_db_manager()

    # Register the connection
    db_manager.register_database(
        db_id=request.db_id,
        connection_string=request.connection_string,
        name=request.name,
        description=request.description,
    )

    # Test connection
    if not db_manager.test_connection(request.db_id):
        db_manager.remove_database(request.db_id)
        raise HTTPException(
            status_code=400,
            detail="Could not connect to the database. Check your connection string.",
        )

    # Index the schema
    try:
        _index_database(request.db_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Connected but failed to index schema: {str(e)}",
        )

    return {"status": "ok", "message": f"Database '{request.db_id}' registered and indexed."}


@app.delete("/api/databases/{db_id}")
async def remove_database(db_id: str):
    """Remove a registered database."""
    db_manager = get_db_manager()
    if not db_manager.has_database(db_id):
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")

    if db_id == "demo_ecommerce":
        raise HTTPException(status_code=400, detail="Cannot remove the demo database.")

    db_manager.remove_database(db_id)
    return {"status": "ok", "message": f"Database '{db_id}' removed."}


@app.post("/api/databases/{db_id}/reindex")
async def reindex_database(db_id: str):
    """Re-index a database's schema (useful after schema changes)."""
    db_manager = get_db_manager()
    if not db_manager.has_database(db_id):
        raise HTTPException(status_code=404, detail=f"Database '{db_id}' not found.")

    try:
        _index_database(db_id)
        return {"status": "ok", "message": f"Schema re-indexed for '{db_id}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Re-indexing failed: {str(e)}")


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    db_manager = get_db_manager()
    return HealthResponse(
        status="ok",
        version="1.0.0",
        databases_registered=len(db_manager.list_databases()),
    )


# ── Static Files (Web UI) ───────────────────────────────────────

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_ui():
    """Serve the web UI."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "NL2SQL API is running. Web UI not found — check /docs for API documentation."}


# ── Run with Uvicorn ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
