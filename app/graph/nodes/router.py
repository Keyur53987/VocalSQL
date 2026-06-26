"""
Router node — classifies user intent using fast keyword matching.

Zero LLM cost. Blocks data-modification requests immediately.
Classifies into: simple_query, aggregation, join_query, blocked, unclear.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Keywords that indicate data modification (BLOCKED)
BLOCKED_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "grant", "revoke", "modify", "remove", "destroy",
    "purge", "wipe", "erase",
}

BLOCKED_PHRASES = [
    r"\badd\s+(a\s+)?new\s+(row|record|entry|data)\b",
    r"\bchange\s+the\s+(value|data|record)\b",
    r"\bremove\s+(all|the|this)\b",
    r"\bdelete\s+(all|the|this|from)\b",
    r"\bdrop\s+(the\s+)?(table|database|column)\b",
    r"\bmodify\s+(the\s+)?(table|column|schema)\b",
]

# Aggregation indicators
AGGREGATION_KEYWORDS = {
    "how many", "count", "total", "sum", "average", "avg",
    "minimum", "min", "maximum", "max", "percentage", "percent",
    "ratio", "proportion", "mean", "median", "group by",
    "highest", "lowest", "most", "least", "top", "bottom",
    "rank", "ranking", "distribution",
}

# Join / multi-table indicators
JOIN_KEYWORDS = {
    "join", "combine", "across", "relationship", "related",
    "along with", "together with", "corresponding", "linked",
    "associated", "for each", "per",
}

COMPILED_BLOCKED = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PHRASES]


def route_query(state: dict) -> dict:
    """
    Classify user query intent. Zero LLM cost — pure keyword matching.

    Returns partial state update with 'intent' and optionally 'error_message'.
    """
    query = state.get("user_query", "").strip()
    query_lower = query.lower()
    words = set(query_lower.split())

    # ── 1. Check for blocked (data modification) intent ──
    if words & BLOCKED_KEYWORDS:
        logger.warning(f"Blocked query (keyword match): '{query[:80]}'")
        return {
            "intent": "blocked",
            "error_message": (
                "⛔ Data modification queries are not allowed. "
                "This system only supports read-only SELECT queries for safety."
            ),
        }

    for pattern in COMPILED_BLOCKED:
        if pattern.search(query_lower):
            logger.warning(f"Blocked query (phrase match): '{query[:80]}'")
            return {
                "intent": "blocked",
                "error_message": (
                    "⛔ This request appears to modify data. "
                    "Only read-only queries are supported."
                ),
            }

    # ── 2. Check for unclear / too short ──
    if len(query.split()) < 3:
        return {
            "intent": "unclear",
            "error_message": (
                "❓ Your question is too short. Please provide more detail "
                "about what data you're looking for."
            ),
        }

    # ── 3. Classify query type ──
    if any(kw in query_lower for kw in AGGREGATION_KEYWORDS):
        intent = "aggregation"
    elif any(kw in query_lower for kw in JOIN_KEYWORDS):
        intent = "join_query"
    else:
        intent = "simple_query"

    logger.info(f"Routed query as '{intent}': '{query[:60]}'")
    return {"intent": intent}
