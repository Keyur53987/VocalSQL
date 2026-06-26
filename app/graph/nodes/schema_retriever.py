"""
Schema retriever node — RAG-powered relevant table retrieval.

Queries ChromaDB to find the most relevant tables for a given
natural language question. This is the core anti-hallucination
mechanism: the LLM only sees tables retrieved here.
"""

import logging
from app.services import get_schema_indexer, get_db_manager
from app.config import settings

logger = logging.getLogger(__name__)


def retrieve_schema(state: dict) -> dict:
    """
    Retrieve relevant table schemas using semantic search.

    Returns partial state with 'relevant_tables', 'schema_context',
    'all_table_names', and 'db_dialect'.
    """
    query = state.get("user_query", "")
    db_id = state.get("database_id", "")

    indexer = get_schema_indexer()
    db_manager = get_db_manager()

    # Get SQL dialect for this database
    try:
        dialect = db_manager.get_dialect(db_id)
    except Exception:
        dialect = "sqlite"

    # Search for relevant tables
    results = indexer.search_relevant_tables(
        db_id=db_id,
        query=query,
        top_k=settings.SCHEMA_TOP_K,
    )

    if not results:
        logger.warning(f"No relevant tables found for query: '{query[:60]}'")
        return {
            "relevant_tables": [],
            "schema_context": "No schema information available.",
            "all_table_names": [],
            "db_dialect": dialect,
            "error_message": "No tables found in the database index. Please ensure the database schema has been indexed.",
        }

    # Build formatted schema context for the LLM prompt
    schema_parts = []
    for r in results:
        schema_parts.append(r["document"])

    schema_context = "\n\n---\n\n".join(schema_parts)

    # Get ALL table names for validation (not just retrieved ones)
    all_table_names = indexer.get_all_table_names(db_id)

    logger.info(
        f"Retrieved {len(results)} relevant tables for '{query[:40]}': "
        f"{[r['table_name'] for r in results]}"
    )

    return {
        "relevant_tables": results,
        "schema_context": schema_context,
        "all_table_names": all_table_names,
        "db_dialect": dialect,
    }
