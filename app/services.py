"""
Service registry — lazy-initialized singletons for all shared services.

Nodes import from here to access database, RAG, and LLM services.
Using lazy initialization so services are only created when first accessed
and the API key can be loaded from .env at runtime.
"""

import logging
from functools import lru_cache
from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache()
def get_db_manager():
    """Get the global DatabaseManager instance."""
    from app.db.connection import DatabaseManager
    return DatabaseManager(config_path="./data/databases.json")


@lru_cache()
def get_introspector():
    """Get the global SchemaIntrospector instance."""
    from app.db.introspector import SchemaIntrospector
    return SchemaIntrospector(get_db_manager())


@lru_cache()
def get_schema_indexer():
    """Get the global SchemaIndexer instance."""
    from app.rag.schema_indexer import SchemaIndexer
    return SchemaIndexer(settings.CHROMA_PERSIST_DIR)


@lru_cache()
def get_fewshot_store():
    """Get the global FewShotStore instance."""
    from app.rag.fewshot_store import FewShotStore
    return FewShotStore(settings.CHROMA_PERSIST_DIR)


@lru_cache()
def get_llm():
    """Get the global LLM instance (Groq)."""
    from langchain_groq import ChatGroq

    if not settings.GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. Get a free key at "
            "https://console.groq.com/keys and add it to your .env file."
        )

    llm = ChatGroq(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        groq_api_key=settings.GROQ_API_KEY,
    )
    logger.info(f"Initialized LLM: {settings.LLM_MODEL}")
    return llm
