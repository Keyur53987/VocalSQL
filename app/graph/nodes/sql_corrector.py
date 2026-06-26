"""
SQL corrector node — self-healing loop using LLM feedback.

When validation fails, this node sends the invalid SQL along with
the specific error messages back to the LLM to fix. Increments
the correction_attempts counter (capped at MAX_CORRECTION_RETRIES).
"""

import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.services import get_llm
from app.graph.nodes.sql_generator import _clean_sql_response

logger = logging.getLogger(__name__)


CORRECTION_PROMPT = """You are an expert SQL debugger. Fix the SQL query below based on the error messages.

## RULES:
1. Return ONLY the corrected SQL query. No explanations, no markdown.
2. Use ONLY the tables and columns from the provided schema.
3. The query MUST be a SELECT statement (read-only).
4. Fix the specific errors mentioned — do not rewrite the entire query unnecessarily.
5. Use the correct SQL dialect: {dialect}

## DATABASE SCHEMA:
{schema}

## ORIGINAL USER QUESTION:
{question}

## FAILED SQL:
{failed_sql}

## ERROR MESSAGES:
{errors}

## CORRECTED SQL:"""


def correct_sql(state: dict) -> dict:
    """
    Attempt to fix invalid SQL using LLM with error feedback.

    Returns partial state with updated 'generated_sql' and
    incremented 'correction_attempts'.
    """
    failed_sql = state.get("generated_sql", "")
    validation_errors = state.get("validation_errors", [])
    execution_error = state.get("execution_error", "")
    schema_context = state.get("schema_context", "")
    user_query = state.get("user_query", "")
    dialect = state.get("db_dialect", "sqlite")
    attempts = state.get("correction_attempts", 0)

    # Combine all errors
    all_errors = list(validation_errors)
    if execution_error:
        all_errors.append(f"Execution error: {execution_error}")
    errors_text = "\n".join(f"- {e}" for e in all_errors)

    prompt = CORRECTION_PROMPT.format(
        dialect=dialect,
        schema=schema_context,
        question=user_query,
        failed_sql=failed_sql,
        errors=errors_text,
    )

    llm = get_llm()
    try:
        response = llm.invoke([
            SystemMessage(content="You are a SQL error correction expert. Return only the corrected SQL."),
            HumanMessage(content=prompt),
        ])

        corrected_sql = _clean_sql_response(response.content.strip())

        logger.info(
            f"Correction attempt {attempts + 1}: '{corrected_sql[:80]}...'"
        )

        return {
            "generated_sql": corrected_sql,
            "correction_attempts": attempts + 1,
            "validation_errors": [],  # Clear old errors for re-validation
            "execution_error": "",
        }

    except Exception as e:
        logger.error(f"SQL correction LLM call failed: {e}")
        return {
            "correction_attempts": attempts + 1,
            "error_message": f"SQL correction failed: {str(e)}",
        }
