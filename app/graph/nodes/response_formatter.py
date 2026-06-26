"""
Response formatter node — assembles the final response.

Handles both success and error cases, producing a consistent
response structure for the API layer.
"""

import logging

logger = logging.getLogger(__name__)


def format_response(state: dict) -> dict:
    """
    Build the final response from the pipeline state.

    Handles success, validation failure, execution failure,
    blocked queries, and unclear queries.
    """
    intent = state.get("intent", "")
    error_message = state.get("error_message", "")
    generated_sql = state.get("generated_sql", "")
    execution_result = state.get("execution_result")
    execution_error = state.get("execution_error", "")
    validation_errors = state.get("validation_errors", [])
    correction_attempts = state.get("correction_attempts", 0)

    # ── Case 1: Blocked or unclear query ─────────────────────────
    if intent in ("blocked", "unclear") or (error_message and not generated_sql):
        return {
            "final_response": {
                "success": False,
                "error": error_message or "Unable to process this query.",
                "generated_sql": None,
                "results": None,
                "intent": intent,
                "correction_attempts": correction_attempts,
            }
        }

    # ── Case 2: Successful execution ─────────────────────────────
    if execution_result and not execution_error:
        natural_language_response = None
        try:
            from app.services import get_llm
            from langchain_core.prompts import PromptTemplate

            llm = get_llm()
            prompt = PromptTemplate.from_template(
                "You are a helpful data assistant. The user asked a question about their database, "
                "we generated a SQL query, and we executed it to get the results. "
                "Write a very brief, punchy natural language answer to the user's question "
                "based on the raw data below. "
                "CRITICAL INSTRUCTIONS:\n"
                "1. Keep it extremely concise (1-2 sentences maximum).\n"
                "2. Do not explain the SQL or the process.\n"
                "3. Use markdown bolding (**like this**) to highlight the most important numbers, entities, or key data points (e.g., 'There are **14** countries, including **India** and the **USA**').\n\n"
                "User Question: {question}\n"
                "Generated SQL: {sql}\n"
                "Execution Results: {results}\n\n"
                "Answer:"
            )
            chain = prompt | llm
            # Limit results to top 20 rows to avoid token explosion
            safe_results = {
                "columns": execution_result.get("columns", []),
                "rows": execution_result.get("rows", [])[:20],
                "row_count": execution_result.get("row_count", 0)
            }
            
            summary_msg = chain.invoke({
                "question": state.get("user_query", ""),
                "sql": generated_sql,
                "results": str(safe_results)
            })
            natural_language_response = summary_msg.content.strip()
        except Exception as e:
            logger.warning(f"Failed to generate natural language summary: {e}")

        return {
            "final_response": {
                "success": True,
                "error": None,
                "generated_sql": generated_sql,
                "natural_language_response": natural_language_response,
                "results": execution_result,
                "intent": intent,
                "correction_attempts": correction_attempts,
            }
        }

    # ── Case 3: Validation failed after max retries ──────────────
    if validation_errors:
        return {
            "final_response": {
                "success": False,
                "error": (
                    f"SQL validation failed after {correction_attempts} correction attempt(s). "
                    f"Errors: {'; '.join(validation_errors)}"
                ),
                "generated_sql": generated_sql,
                "results": None,
                "intent": intent,
                "correction_attempts": correction_attempts,
            }
        }

    # ── Case 4: Execution error after max retries ────────────────
    if execution_error:
        return {
            "final_response": {
                "success": False,
                "error": (
                    f"SQL execution failed after {correction_attempts} correction attempt(s). "
                    f"Error: {execution_error}"
                ),
                "generated_sql": generated_sql,
                "results": None,
                "intent": intent,
                "correction_attempts": correction_attempts,
            }
        }

    # ── Case 5: Generic failure ──────────────────────────────────
    return {
        "final_response": {
            "success": False,
            "error": error_message or "An unexpected error occurred in the pipeline.",
            "generated_sql": generated_sql,
            "results": None,
            "intent": intent,
            "correction_attempts": correction_attempts,
        }
    }
