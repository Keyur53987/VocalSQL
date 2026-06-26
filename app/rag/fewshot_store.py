"""
Few-shot example store for RAG retrieval.

Stores curated (question, SQL) pairs in ChromaDB and retrieves
the most semantically similar examples at query time to provide
in-context learning examples to the LLM.
"""

import json
import os
import logging
from typing import List, Dict, Optional
import chromadb

logger = logging.getLogger(__name__)


class FewShotStore:
    """Manages few-shot NL→SQL examples in ChromaDB."""

    def __init__(self, persist_dir: str):
        self.client = chromadb.PersistentClient(path=persist_dir)

    def _collection_name(self, db_id: str) -> str:
        safe_name = "fewshot_" + "".join(
            c if c.isalnum() or c == "_" else "_" for c in db_id
        )
        return safe_name[:63]

    def load_examples(self, db_id: str, examples: List[Dict[str, str]]):
        """
        Load a batch of few-shot examples into ChromaDB.

        Args:
            db_id: Database identifier
            examples: List of {"question": ..., "sql": ...} dicts
        """
        collection_name = self._collection_name(db_id)
        # Recreate collection
        try:
            self.client.delete_collection(collection_name)
        except Exception:
            pass

        collection = self.client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        if not examples:
            return

        documents = []
        metadatas = []
        ids = []

        for i, example in enumerate(examples):
            question = example.get("question", "")
            sql = example.get("sql", "")
            if not question or not sql:
                continue

            # Embed the question (the user query will be matched against this)
            documents.append(question)
            metadatas.append({
                "sql": sql,
                "question": question,
                "db_id": db_id,
            })
            ids.append(f"{db_id}__fewshot_{i}")

        if documents:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(
                f"Loaded {len(documents)} few-shot examples for database '{db_id}'"
            )

    def load_from_file(self, db_id: str, filepath: str):
        """Load few-shot examples from a JSON file."""
        if not os.path.exists(filepath):
            logger.warning(f"Few-shot file not found: {filepath}")
            return

        with open(filepath, "r") as f:
            examples = json.load(f)

        self.load_examples(db_id, examples)

    def add_example(self, db_id: str, question: str, sql: str):
        """Add a single new few-shot example (for feedback/learning loop)."""
        collection_name = self._collection_name(db_id)

        try:
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            collection = self.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        idx = collection.count()
        collection.add(
            documents=[question],
            metadatas=[{"sql": sql, "question": question, "db_id": db_id}],
            ids=[f"{db_id}__fewshot_{idx}"],
        )
        logger.info(f"Added new few-shot example for '{db_id}'")

    def search_similar(
        self, db_id: str, query: str, top_k: int = 3
    ) -> List[Dict[str, str]]:
        """
        Retrieve the most similar few-shot examples for a query.

        Returns:
            List of {"question": ..., "sql": ...} dicts, ordered by similarity
        """
        collection_name = self._collection_name(db_id)

        try:
            collection = self.client.get_collection(collection_name)
        except Exception:
            return []

        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, count),
        )

        examples = []
        if results["metadatas"] and results["metadatas"][0]:
            for meta in results["metadatas"][0]:
                examples.append({
                    "question": meta.get("question", ""),
                    "sql": meta.get("sql", ""),
                })

        return examples

    def get_example_count(self, db_id: str) -> int:
        """Get the number of few-shot examples for a database."""
        collection_name = self._collection_name(db_id)
        try:
            collection = self.client.get_collection(collection_name)
            return collection.count()
        except Exception:
            return 0
