"""
Confidence analyzer node — dual-path confidence & ambiguity analysis.

Combines LLM self-assessment (via structured output) with deterministic
signals from the pipeline (schema coverage, few-shot similarity, complexity)
to produce a fused, evidence-based confidence score.

If confidence falls below the configured threshold, triggers a
clarification request instead of proceeding to execution.
"""

import re
import logging
import sqlglot
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, SystemMessage
from app.services import get_llm
from app.config import settings
from app.models.confidence import (
    AmbiguousTerm,
    ConfidenceSignals,
    SQLConfidenceReport,
    LLMAnalysisOutput,
    RiskLevel,
)

logger = logging.getLogger(__name__)


ANALYSIS_PROMPT = """You are a SQL analysis expert. You have just generated the following SQL query for a user's natural language question. Analyze the quality and confidence of this translation.

## USER QUESTION:
{question}

## DATABASE SCHEMA:
{schema}

## GENERATED SQL:
{sql}

Provide a thorough analysis of:
1. Your confidence (0-100) that this SQL correctly answers the question
2. Which tables are used
3. Any ambiguous or vague terms in the user's question (e.g., "recent", "top", "best")
4. What assumptions you had to make
5. If the question is ambiguous, what clarifying questions would help

Be honest about ambiguity. If the question contains vague terms, your confidence should reflect that uncertainty."""


# ── Deterministic Signal Extractors ──────────────────────────────


def _compute_schema_coverage(sql: str, schema_context: str) -> float:
    """
    Compute what fraction of the schema columns appear in the SQL.

    Higher coverage = the SQL is touching more of the relevant schema,
    which generally means the LLM understood the schema well.
    But we also penalize if it's too low (missed relevant columns).
    """
    if not sql or not schema_context:
        return 0.0

    # Extract column names from schema context
    schema_columns = set()
    for line in schema_context.split("\n"):
        line = line.strip()
        if line and not line.startswith(("Table:", "Description:", "Row Count:", "Columns:", "Foreign Keys:", "---", "None")):
            # Lines like: "  column_name TYPE [PRIMARY KEY]"
            parts = line.split()
            if parts:
                col_name = parts[0].lower()
                if col_name and len(col_name) > 1:
                    schema_columns.add(col_name)

    if not schema_columns:
        return 0.5  # Neutral if we can't parse

    # Check how many schema columns appear in the SQL
    sql_lower = sql.lower()
    matched = sum(1 for col in schema_columns if col in sql_lower)

    # We don't expect ALL columns to be used — normalize with a generous curve
    # Using ~30% as the "good" threshold
    coverage = min(matched / max(len(schema_columns) * 0.3, 1), 1.0)
    return round(coverage, 3)


def _compute_fewshot_similarity(few_shot_examples: list) -> float:
    """
    Score based on whether similar few-shot examples were found.

    If ChromaDB returned close matches, it means similar queries
    have been answered before — higher confidence.
    """
    if not few_shot_examples:
        return 0.3  # No examples = slight penalty but not catastrophic

    # The number of examples found is a signal
    count_score = min(len(few_shot_examples) / 3.0, 1.0)
    return round(count_score * 0.8 + 0.2, 3)  # Floor at 0.2


def _compute_query_complexity(sql: str) -> float:
    """
    Compute normalized complexity. More complex queries get a
    slight confidence penalty (more room for error).

    Returns 0-1 where 1 = very complex = MORE penalty.
    """
    if not sql:
        return 0.5

    sql_upper = sql.upper()

    signals = {
        "joins": len(re.findall(r'\bJOIN\b', sql_upper)),
        "subqueries": sql_upper.count("(SELECT"),
        "aggregations": len(re.findall(r'\b(COUNT|SUM|AVG|MIN|MAX)\s*\(', sql_upper)),
        "group_by": 1 if "GROUP BY" in sql_upper else 0,
        "having": 1 if "HAVING" in sql_upper else 0,
        "case_when": sql_upper.count("CASE WHEN"),
        "unions": sql_upper.count("UNION"),
    }

    # Weighted complexity score
    complexity = (
        signals["joins"] * 0.15 +
        signals["subqueries"] * 0.25 +
        signals["aggregations"] * 0.1 +
        signals["group_by"] * 0.1 +
        signals["having"] * 0.15 +
        signals["case_when"] * 0.2 +
        signals["unions"] * 0.2
    )

    # Normalize to 0-1 (cap at 1.0)
    return round(min(complexity, 1.0), 3)


def _extract_tables_from_sql(sql: str) -> List[str]:
    """Extract table names from SQL using sqlglot parsing."""
    try:
        parsed = sqlglot.parse_one(sql)
        tables = set()
        for table_node in parsed.find_all(sqlglot.exp.Table):
            if table_node.name:
                tables.add(table_node.name)
        return sorted(tables)
    except Exception:
        return []


# ── Signal Fusion ────────────────────────────────────────────────


def _fuse_confidence(signals: ConfidenceSignals) -> int:
    """
    Fuse multiple signals into a single confidence score.

    Weights:
      - LLM self-score:       40% (primary but needs validation)
      - Schema coverage:      25% (hard evidence)
      - Few-shot similarity:  20% (experience-based)
      - Complexity penalty:   15% (inverse — higher complexity = lower confidence)
    """
    fused = (
        signals.llm_self_score * 0.40 +
        signals.schema_coverage * 0.25 +
        signals.fewshot_similarity * 0.20 +
        (1.0 - signals.query_complexity) * 0.15  # Invert complexity
    )

    # Scale to 0-100 and clamp
    score = int(round(fused * 100))
    return max(0, min(100, score))


def _classify_risk(score: int) -> RiskLevel:
    """Classify risk level from confidence score."""
    if score >= 85:
        return RiskLevel.LOW
    elif score >= 70:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.HIGH


# ── Main Node ────────────────────────────────────────────────────


def analyze_confidence(state: dict) -> dict:
    """
    Analyze confidence and ambiguity of the generated SQL.

    This node runs after SQL generation. It performs:
    1. LLM self-assessment via structured output
    2. Deterministic signal collection
    3. Signal fusion into a single confidence score
    4. Risk classification and clarification gating

    Returns partial state with 'confidence_report' and
    optionally 'needs_clarification' + 'clarification_questions'.
    """
    generated_sql = state.get("generated_sql", "")
    user_query = state.get("user_query", "")
    schema_context = state.get("schema_context", "")
    few_shot_examples = state.get("few_shot_examples", [])

    # Skip analysis if no SQL was generated or feature is disabled
    if not generated_sql or not getattr(settings, 'ENABLE_CONFIDENCE_ANALYSIS', True):
        return {}

    # ── Step 1: LLM Self-Assessment ──────────────────────────────
    llm_analysis = _get_llm_analysis(user_query, schema_context, generated_sql)

    # ── Step 2: Deterministic Signals ────────────────────────────
    schema_coverage = _compute_schema_coverage(generated_sql, schema_context)
    fewshot_sim = _compute_fewshot_similarity(few_shot_examples)
    complexity = _compute_query_complexity(generated_sql)
    llm_self = llm_analysis.confidence_self_score / 100.0 if llm_analysis else 0.5

    signals = ConfidenceSignals(
        schema_coverage=schema_coverage,
        fewshot_similarity=fewshot_sim,
        query_complexity=complexity,
        llm_self_score=llm_self,
    )

    # ── Step 3: Fusion ───────────────────────────────────────────
    fused_score = _fuse_confidence(signals)
    risk = _classify_risk(fused_score)

    # ── Step 4: Build Report ─────────────────────────────────────
    tables = (
        llm_analysis.tables_used if llm_analysis
        else _extract_tables_from_sql(generated_sql)
    )

    ambiguous_terms = (
        llm_analysis.ambiguous_terms if llm_analysis else []
    )

    assumptions = (
        llm_analysis.assumptions if llm_analysis else []
    )

    clarification_questions = (
        llm_analysis.clarification_questions if llm_analysis else []
    )

    explanation = (
        llm_analysis.brief_explanation if llm_analysis
        else "Analysis unavailable."
    )

    report = SQLConfidenceReport(
        confidence_score=fused_score,
        risk_level=risk,
        tables_identified=tables,
        ambiguous_terms=ambiguous_terms,
        assumptions_made=assumptions,
        signals=signals,
        explanation=explanation,
        clarification_questions=clarification_questions,
    )

    report_dict = report.model_dump()

    # ── Step 5: Clarification Gate ───────────────────────────────
    threshold = getattr(settings, 'CONFIDENCE_THRESHOLD', 70)
    needs_clarification = fused_score < threshold and len(clarification_questions) > 0

    logger.info(
        f"Confidence analysis: score={fused_score}%, risk={risk.value}, "
        f"ambiguous_terms={len(ambiguous_terms)}, "
        f"needs_clarification={needs_clarification}"
    )

    result = {
        "confidence_report": report_dict,
        "needs_clarification": needs_clarification,
    }

    if needs_clarification:
        result["clarification_questions"] = clarification_questions

    return result


def _get_llm_analysis(
    question: str, schema: str, sql: str
) -> LLMAnalysisOutput | None:
    """
    Get structured self-assessment from the LLM.

    Uses with_structured_output for type-validated response.
    Falls back gracefully if structured output isn't supported.
    """
    llm = get_llm()

    prompt = ANALYSIS_PROMPT.format(
        question=question,
        schema=schema[:3000],  # Trim to avoid token explosion
        sql=sql,
    )

    try:
        # Try structured output first (supported by Groq with Llama models)
        structured_llm = llm.with_structured_output(LLMAnalysisOutput)
        result = structured_llm.invoke([
            SystemMessage(content="You are a SQL analysis expert. Provide honest, detailed analysis."),
            HumanMessage(content=prompt),
        ])
        logger.info("LLM structured analysis completed successfully")
        return result

    except Exception as e:
        logger.warning(f"Structured output failed, using fallback: {e}")
        return _fallback_analysis(llm, prompt)


def _fallback_analysis(llm, prompt: str) -> LLMAnalysisOutput | None:
    """
    Fallback: parse free-text LLM response into the analysis model.

    Used when with_structured_output isn't available.
    """
    try:
        response = llm.invoke([
            SystemMessage(
                content=(
                    "You are a SQL analysis expert. Respond in this exact JSON format:\n"
                    '{"confidence_self_score": <0-100>, "tables_used": ["table1"], '
                    '"ambiguous_terms": [{"term": "word", "interpretation": "how interpreted", "alternatives": ["alt1"]}], '
                    '"assumptions": ["assumption1"], "clarification_questions": ["question1"], '
                    '"brief_explanation": "one sentence"}'
                )
            ),
            HumanMessage(content=prompt),
        ])

        import json
        text = response.content.strip()

        # Try to extract JSON from the response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            data = json.loads(json_match.group())
            return LLMAnalysisOutput(**data)

    except Exception as e:
        logger.warning(f"Fallback analysis also failed: {e}")

    return None
