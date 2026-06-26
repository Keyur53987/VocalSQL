"""
SQL security utilities.

Deterministic, zero-LLM-cost safety checks to prevent
data modification, injection, and dangerous operations.
"""

import re
from typing import List, Tuple


# Patterns that indicate data modification (case-insensitive)
DANGEROUS_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
    "MERGE", "REPLACE", "RENAME", "ATTACH", "DETACH",
}

# Regex patterns for more sophisticated detection
DANGEROUS_PATTERNS = [
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bDELETE\s+FROM\b",
    r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)\b",
    r"\bALTER\s+(TABLE|DATABASE)\b",
    r"\bTRUNCATE\s+TABLE\b",
    r"\bCREATE\s+(TABLE|DATABASE|INDEX|VIEW)\b",
    r"\bGRANT\s+",
    r"\bREVOKE\s+",
    r"\bEXEC(UTE)?\s*\(",
    r";\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)",  # stacked queries
    r"--",  # SQL comments (potential injection)
    r"/\*.*?\*/",  # Block comments (potential injection)
    r"\bUNION\s+ALL\s+SELECT\b.*\bFROM\s+information_schema\b",  # info leak
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in DANGEROUS_PATTERNS]


def is_safe_sql(sql: str) -> bool:
    """
    Check if a SQL query is safe to execute (read-only).

    Returns True if the SQL appears to be a safe read-only query.
    """
    if not sql or not sql.strip():
        return False

    # Normalize whitespace
    normalized = " ".join(sql.split()).upper()

    # Must start with SELECT, WITH, or EXPLAIN
    valid_starts = ("SELECT", "WITH", "EXPLAIN")
    if not any(normalized.startswith(kw) for kw in valid_starts):
        return False

    # Check for dangerous keywords as standalone tokens
    tokens = set(re.findall(r'\b\w+\b', normalized))
    if tokens & DANGEROUS_KEYWORDS:
        return False

    # Check dangerous patterns (more precise than keyword matching)
    for pattern in COMPILED_PATTERNS:
        if pattern.search(sql):
            return False

    return True


def get_safety_violations(sql: str) -> List[str]:
    """
    Return a list of specific safety violations found in the SQL.
    """
    violations = []

    if not sql or not sql.strip():
        violations.append("Empty SQL query")
        return violations

    normalized = " ".join(sql.split()).upper()

    # Check start
    valid_starts = ("SELECT", "WITH", "EXPLAIN")
    if not any(normalized.startswith(kw) for kw in valid_starts):
        violations.append(f"Query must start with SELECT, WITH, or EXPLAIN. Found: '{normalized[:20]}...'")

    # Check dangerous keywords
    tokens = set(re.findall(r'\b\w+\b', normalized))
    found_dangerous = tokens & DANGEROUS_KEYWORDS
    if found_dangerous:
        violations.append(f"Dangerous keywords detected: {', '.join(found_dangerous)}")

    # Check patterns
    for i, pattern in enumerate(COMPILED_PATTERNS):
        if pattern.search(sql):
            violations.append(f"Dangerous pattern detected: {DANGEROUS_PATTERNS[i]}")

    return violations


def sanitize_identifier(name: str) -> str:
    """Sanitize a SQL identifier (table/column name) to prevent injection."""
    # Allow only alphanumeric and underscores
    return re.sub(r'[^a-zA-Z0-9_]', '', name)
