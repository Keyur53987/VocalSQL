"""API response models."""

from pydantic import BaseModel, Field
from typing import Optional, Any


class QueryResponse(BaseModel):
    """Response from the NL2SQL pipeline."""
    success: bool
    question: str
    generated_sql: Optional[str] = None
    natural_language_response: Optional[str] = None
    results: Optional[dict] = None  # {columns: [...], rows: [...], row_count: int}
    error: Optional[str] = None
    intent: Optional[str] = None
    correction_attempts: int = 0
    execution_time_ms: Optional[float] = None
    # Confidence & Ambiguity Analysis
    confidence_report: Optional[dict] = None
    needs_clarification: bool = False
    clarification_questions: Optional[list] = None


class DatabaseInfo(BaseModel):
    """Database connection info (safe to expose)."""
    db_id: str
    name: str
    description: str
    is_connected: bool = False
    table_count: int = 0


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "1.0.0"
    databases_registered: int = 0
