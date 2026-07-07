"""
LangGraph workflow assembly — compiles the full NL2SQL pipeline.

Defines the state machine with conditional edges for:
- Blocked/unclear query short-circuit → response_formatter
- Self-correction loop: validator ↔ corrector (max 3 retries)
- Execution error recovery: executor → corrector → validator
"""

import logging
from langgraph.graph import StateGraph, START, END
from app.graph.state import NL2SQLState
from app.graph.nodes.router import route_query
from app.graph.nodes.schema_retriever import retrieve_schema
from app.graph.nodes.fewshot_retriever import retrieve_fewshots
from app.graph.nodes.sql_generator import generate_sql
from app.graph.nodes.confidence_analyzer import analyze_confidence
from app.graph.nodes.sql_validator import validate_sql
from app.graph.nodes.sql_corrector import correct_sql
from app.graph.nodes.sql_executor import execute_sql
from app.graph.nodes.response_formatter import format_response
from app.config import settings

logger = logging.getLogger(__name__)


def _should_continue_after_router(state: dict) -> str:
    """Decide where to go after routing."""
    intent = state.get("intent", "")
    if intent in ("blocked", "unclear"):
        return "format_response"
    if state.get("error_message") and not state.get("generated_sql"):
        return "format_response"
    return "retrieve_schema"


def _should_continue_after_validator(state: dict) -> str:
    """Decide where to go after SQL validation."""
    if state.get("is_valid"):
        return "execute_sql"
    # Check if we've exhausted correction attempts
    if state.get("correction_attempts", 0) >= settings.MAX_CORRECTION_RETRIES:
        return "format_response"
    return "correct_sql"


def _should_continue_after_executor(state: dict) -> str:
    """Decide where to go after SQL execution."""
    if not state.get("execution_error"):
        return "format_response"
    # Execution failed — try to correct if retries remain
    if state.get("correction_attempts", 0) >= settings.MAX_CORRECTION_RETRIES:
        return "format_response"
    return "correct_sql"


def _should_continue_after_confidence(state: dict) -> str:
    """Decide where to go after confidence analysis."""
    if state.get("needs_clarification"):
        return "format_response"
    return "validate_sql"


def build_graph() -> StateGraph:
    """
    Build and compile the NL2SQL LangGraph pipeline.

    Flow:
        START → router → [schema_retriever → fewshot_retriever → sql_generator]
                       ↘ (blocked/unclear) → response_formatter → END
        sql_generator → sql_validator
        sql_validator → (valid) → sql_executor → response_formatter → END
                      → (invalid, retries < 3) → sql_corrector → sql_validator ↩
                      → (invalid, retries ≥ 3) → response_formatter → END
        sql_executor → (error, retries < 3) → sql_corrector → sql_validator ↩
                     → (error, retries ≥ 3) → response_formatter → END
    """
    builder = StateGraph(NL2SQLState)

    # ── Register Nodes ───────────────────────────────────────────
    builder.add_node("router", route_query)
    builder.add_node("retrieve_schema", retrieve_schema)
    builder.add_node("retrieve_fewshots", retrieve_fewshots)
    builder.add_node("generate_sql", generate_sql)
    builder.add_node("confidence_analyzer", analyze_confidence)
    builder.add_node("validate_sql", validate_sql)
    builder.add_node("correct_sql", correct_sql)
    builder.add_node("execute_sql", execute_sql)
    builder.add_node("format_response", format_response)

    # ── Define Edges ─────────────────────────────────────────────

    # Entry point
    builder.add_edge(START, "router")

    # Router → continue or short-circuit
    builder.add_conditional_edges(
        "router",
        _should_continue_after_router,
        {
            "retrieve_schema": "retrieve_schema",
            "format_response": "format_response",
        },
    )

    # Linear pipeline: schema → fewshots → generate → validate
    builder.add_edge("retrieve_schema", "retrieve_fewshots")
    builder.add_edge("retrieve_fewshots", "generate_sql")
    builder.add_edge("generate_sql", "confidence_analyzer")

    # Confidence gate: proceed or ask for clarification
    builder.add_conditional_edges(
        "confidence_analyzer",
        _should_continue_after_confidence,
        {
            "validate_sql": "validate_sql",
            "format_response": "format_response",
        },
    )

    # Validator → execute OR correct OR give up
    builder.add_conditional_edges(
        "validate_sql",
        _should_continue_after_validator,
        {
            "execute_sql": "execute_sql",
            "correct_sql": "correct_sql",
            "format_response": "format_response",
        },
    )

    # Corrector always goes back to validator (the loop)
    builder.add_edge("correct_sql", "validate_sql")

    # Executor → format response OR correct
    builder.add_conditional_edges(
        "execute_sql",
        _should_continue_after_executor,
        {
            "format_response": "format_response",
            "correct_sql": "correct_sql",
        },
    )

    # Final node → END
    builder.add_edge("format_response", END)

    # ── Compile ──────────────────────────────────────────────────
    graph = builder.compile()
    logger.info("NL2SQL LangGraph pipeline compiled successfully")

    return graph


# Lazy-initialized compiled graph
_compiled_graph = None


def get_graph():
    """Get the compiled graph (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
