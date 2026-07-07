"""
Pydantic models for SQL Confidence & Ambiguity Analysis.

These models support structured output from the LLM, allowing
the confidence analyzer to receive type-validated analysis data
alongside the generated SQL.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class RiskLevel(str, Enum):
    """Risk classification for a generated SQL query."""
    LOW = "low"        # Confidence >= 85%
    MEDIUM = "medium"  # Confidence 70-84%
    HIGH = "high"      # Confidence < 70%


class AmbiguousTerm(BaseModel):
    """A single ambiguous term identified in the user's query."""
    term: str = Field(..., description="The ambiguous word or phrase from the user's query")
    interpretation: str = Field(..., description="How the system interpreted this term")
    alternatives: list[str] = Field(
        default_factory=list,
        description="Other reasonable interpretations that were not chosen"
    )


class ConfidenceSignals(BaseModel):
    """Deterministic signals collected from the pipeline for confidence fusion."""
    schema_coverage: float = Field(
        0.0, ge=0.0, le=1.0,
        description="Fraction of retrieved table columns referenced in the SQL"
    )
    fewshot_similarity: float = Field(
        0.0, ge=0.0, le=1.0,
        description="Best similarity score from few-shot example retrieval"
    )
    query_complexity: float = Field(
        0.0, ge=0.0, le=1.0,
        description="Normalized complexity score (JOINs, subqueries, aggregations)"
    )
    llm_self_score: float = Field(
        0.0, ge=0.0, le=1.0,
        description="The LLM's own confidence self-assessment (0-1)"
    )


class SQLConfidenceReport(BaseModel):
    """Complete confidence and ambiguity analysis for a generated SQL query."""
    confidence_score: int = Field(
        ..., ge=0, le=100,
        description="Fused confidence score (0-100)"
    )
    risk_level: RiskLevel = Field(
        ..., description="Risk classification based on confidence score"
    )
    tables_identified: list[str] = Field(
        default_factory=list,
        description="Tables used in the generated SQL"
    )
    ambiguous_terms: list[AmbiguousTerm] = Field(
        default_factory=list,
        description="Ambiguous terms found in the user's query"
    )
    assumptions_made: list[str] = Field(
        default_factory=list,
        description="Key assumptions the system made during SQL generation"
    )
    signals: ConfidenceSignals = Field(
        default_factory=ConfidenceSignals,
        description="Raw deterministic signals used for confidence fusion"
    )
    explanation: str = Field(
        "", description="Brief human-readable explanation of the confidence assessment"
    )
    clarification_questions: list[str] = Field(
        default_factory=list,
        description="Suggested questions to ask the user if confidence is low"
    )


class LLMAnalysisOutput(BaseModel):
    """
    Schema for the LLM's structured self-assessment output.

    Used with `with_structured_output()` to get type-validated
    analysis from the LLM in a single call.
    """
    confidence_self_score: int = Field(
        ..., ge=0, le=100,
        description="Your confidence (0-100) that this SQL correctly answers the user's question"
    )
    tables_used: list[str] = Field(
        ..., description="List of table names referenced in the SQL"
    )
    ambiguous_terms: list[AmbiguousTerm] = Field(
        default_factory=list,
        description="Ambiguous or vague terms in the user's question"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Key assumptions you made to generate this SQL"
    )
    clarification_questions: list[str] = Field(
        default_factory=list,
        description="Questions to ask the user if the query is ambiguous"
    )
    brief_explanation: str = Field(
        "", description="One-sentence explanation of your interpretation"
    )
