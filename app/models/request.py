"""API request models."""

from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    """Natural language query request."""
    question: str = Field(..., min_length=3, max_length=1000, description="Natural language question")
    database_id: str = Field(..., min_length=1, description="Target database identifier")


class DatabaseRegisterRequest(BaseModel):
    """Register a new database connection."""
    db_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    connection_string: str = Field(..., min_length=5, description="SQLAlchemy connection string")
    name: str = Field("", max_length=100, description="Human-readable name")
    description: str = Field("", max_length=500, description="Database description")


class FeedbackRequest(BaseModel):
    """Submit a correction for few-shot learning."""
    question: str = Field(..., min_length=3)
    correct_sql: str = Field(..., min_length=5)
    database_id: str = Field(..., min_length=1)
