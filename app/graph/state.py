"""
LangGraph state definition for the NL2SQL pipeline.

Uses TypedDict for a flat, explicit state schema. Each node reads
from and writes to specific keys — no mutations, only partial updates.
"""

from typing import TypedDict, Optional, Any


class NL2SQLState(TypedDict, total=False):
    """
    Complete state object flowing through the LangGraph pipeline.

    All fields are optional (total=False) so nodes can return
    partial state updates containing only the keys they modify.
    """

    # ── Input (set at invocation) ────────────────────────────────
    user_query: str          # Original natural language question
    database_id: str         # Target database identifier

    # ── Router Output ────────────────────────────────────────────
    intent: str              # simple_query | aggregation | join_query | blocked | unclear

    # ── RAG Retrieved Context ────────────────────────────────────
    relevant_tables: list    # List of relevant table metadata dicts
    schema_context: str      # Formatted schema text for the LLM prompt
    few_shot_examples: list  # List of {"question": ..., "sql": ...} dicts
    all_table_names: list    # All table names in the database (for validation)

    # ── SQL Generation ───────────────────────────────────────────
    generated_sql: str       # The generated SQL query
    db_dialect: str          # SQL dialect: sqlite, postgresql, mysql

    # ── Validation ───────────────────────────────────────────────
    is_valid: bool           # Whether the SQL passed all validation checks
    validation_errors: list  # List of validation error strings

    # ── Execution ────────────────────────────────────────────────
    execution_result: dict   # {"columns": [...], "rows": [...], "row_count": int}
    execution_error: str     # Error message if execution failed

    # ── Self-Correction Loop ─────────────────────────────────────
    correction_attempts: int # Number of correction attempts so far

    # ── Final Output ─────────────────────────────────────────────
    final_response: dict     # The complete response to return to the user
    error_message: str       # Error message for failed/blocked queries
