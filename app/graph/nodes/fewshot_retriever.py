"""
Few-shot retriever node — retrieves similar NL→SQL examples.

Finds the most semantically similar past queries and their
correct SQL translations to provide as in-context examples.
"""

import logging
from app.services import get_fewshot_store
from app.config import settings

logger = logging.getLogger(__name__)


def retrieve_fewshots(state: dict) -> dict:
    """
    Retrieve similar few-shot examples from the vector store.

    Returns partial state with 'few_shot_examples'.
    """
    query = state.get("user_query", "")
    db_id = state.get("database_id", "")

    store = get_fewshot_store()
    examples = store.search_similar(
        db_id=db_id,
        query=query,
        top_k=settings.FEWSHOT_TOP_K,
    )

    logger.info(f"Retrieved {len(examples)} few-shot examples for '{query[:40]}'")

    return {"few_shot_examples": examples}
