"""
SQL executor node — safely executes validated SQL against the database.

Uses read-only connection with row limits and timeout protection.
"""

import logging
from app.services import get_db_manager
from app.config import settings

logger = logging.getLogger(__name__)


def execute_sql(state: dict) -> dict:
    """
    Execute validated SQL against the target database.

    Returns partial state with 'execution_result' or 'execution_error'.
    """
    sql = state.get("generated_sql", "")
    db_id = state.get("database_id", "")

    if not sql:
        return {"execution_error": "No SQL to execute."}

    db_manager = get_db_manager()

    try:
        result = db_manager.execute_query(
            db_id=db_id,
            sql=sql,
            timeout=settings.QUERY_TIMEOUT_SECONDS,
            max_rows=settings.MAX_RESULT_ROWS,
        )

        logger.info(
            f"Query executed successfully: {result['row_count']} rows returned"
        )

        return {
            "execution_result": result,
            "execution_error": "",
        }

    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Query execution failed: {error_msg[:200]}")

        # Provide a clean error message (strip SQLAlchemy internals)
        clean_error = _clean_execution_error(error_msg)

        return {
            "execution_error": clean_error,
            "execution_result": None,
        }


def _clean_execution_error(raw_error: str) -> str:
    """Clean up database error messages for the LLM corrector."""
    # Remove SQLAlchemy wrapper text
    error = raw_error

    # Extract the core database error
    if "OperationalError" in error:
        # e.g., "(sqlite3.OperationalError) no such table: xyz"
        start = error.find(") ") + 2
        if start > 2:
            error = error[start:]

    # Truncate very long errors
    if len(error) > 500:
        error = error[:500] + "..."

    return error
