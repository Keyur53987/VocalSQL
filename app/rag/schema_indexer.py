"""
Schema indexer for RAG-based table retrieval.

Embeds database schema metadata into ChromaDB so the pipeline can
retrieve only the relevant tables for a given natural language query,
instead of stuffing the entire schema into the LLM prompt.
"""

import json
import logging
from typing import Dict, List, Any, Optional
import chromadb

logger = logging.getLogger(__name__)


class SchemaIndexer:
    """Indexes database schema into ChromaDB for semantic retrieval."""

    def __init__(self, persist_dir: str):
        self.client = chromadb.PersistentClient(path=persist_dir)
        # Cache of full table metadata per database (for validator use)
        self._full_metadata: Dict[str, List[Dict]] = {}

    def _collection_name(self, db_id: str) -> str:
        """Generate a safe collection name for a database."""
        # ChromaDB collection names must be 3-63 chars, alphanumeric + underscores
        safe_name = "schema_" + "".join(c if c.isalnum() or c == "_" else "_" for c in db_id)
        return safe_name[:63]

    def index_schema(
        self,
        db_id: str,
        tables_metadata: List[Dict[str, Any]],
        descriptions: Optional[Dict[str, dict]] = None,
    ):
        """
        Embed and index all table metadata for a database.

        Args:
            db_id: Database identifier
            tables_metadata: List of table metadata from SchemaIntrospector
            descriptions: Optional natural-language descriptions keyed by table name
        """
        collection_name = self._collection_name(db_id)

        # Drop and recreate collection for clean re-index
        try:
            self.client.delete_collection(collection_name)
        except Exception:
            pass

        collection = self.client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        documents = []
        metadatas = []
        ids = []

        for table in tables_metadata:
            table_name = table["table_name"]

            # Build a rich text document for embedding
            doc = self._build_table_document(table, descriptions)

            documents.append(doc)
            metadatas.append({
                "table_name": table_name,
                "db_id": db_id,
                "column_count": len(table.get("columns", [])),
                "row_count": table.get("row_count", 0),
            })
            ids.append(f"{db_id}__{table_name}")

        if documents:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(
                f"Indexed {len(documents)} tables for database '{db_id}' "
                f"into collection '{collection_name}'"
            )

        # Cache full metadata for validation
        self._full_metadata[db_id] = tables_metadata

    def _build_table_document(
        self, table: Dict, descriptions: Optional[Dict] = None
    ) -> str:
        """Build a rich text document from table metadata for embedding."""
        table_name = table["table_name"]

        # Table description
        desc = ""
        if descriptions and table_name in descriptions:
            desc = descriptions[table_name].get("description", "")
            col_descs = descriptions[table_name].get("columns", {})
        else:
            col_descs = {}

        # Column details
        col_parts = []
        for col in table.get("columns", []):
            col_name = col["name"]
            col_type = col["type"]
            pk = " [PRIMARY KEY]" if col.get("primary_key") else ""
            col_desc = f" - {col_descs[col_name]}" if col_name in col_descs else ""

            # Add sample values for context
            samples = table.get("sample_values", {}).get(col_name, [])
            sample_str = f" (e.g., {', '.join(samples[:3])})" if samples else ""

            col_parts.append(f"  {col_name} {col_type}{pk}{col_desc}{sample_str}")

        columns_text = "\n".join(col_parts)

        # Foreign keys
        fk_parts = []
        for fk in table.get("foreign_keys", []):
            fk_parts.append(
                f"  {fk['column']} → {fk['references_table']}.{fk['references_column']}"
            )
        fk_text = "\n".join(fk_parts) if fk_parts else "  None"

        doc = (
            f"Table: {table_name}\n"
            f"Description: {desc or 'No description available'}\n"
            f"Row Count: {table.get('row_count', 'unknown')}\n"
            f"Columns:\n{columns_text}\n"
            f"Foreign Keys:\n{fk_text}"
        )

        return doc

    def search_relevant_tables(
        self, db_id: str, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for tables relevant to a natural language query.

        Returns:
            List of dicts with 'document', 'table_name', 'metadata', 'score'
        """
        collection_name = self._collection_name(db_id)

        try:
            collection = self.client.get_collection(collection_name)
        except Exception:
            logger.warning(f"No schema index found for database '{db_id}'")
            return []

        count = collection.count()
        if count == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, count),
        )

        tables = []
        if results["documents"] and results["documents"][0]:
            distances = results.get("distances", [[]])[0]
            for i, (doc, meta) in enumerate(
                zip(results["documents"][0], results["metadatas"][0])
            ):
                tables.append({
                    "document": doc,
                    "table_name": meta["table_name"],
                    "metadata": meta,
                    "score": 1 - distances[i] if i < len(distances) else 0,
                })

        return tables

    def get_full_metadata(self, db_id: str) -> List[Dict]:
        """Get cached full table metadata for a database."""
        return self._full_metadata.get(db_id, [])

    def get_all_table_names(self, db_id: str) -> List[str]:
        """Get all indexed table names for a database."""
        metadata = self._full_metadata.get(db_id, [])
        return [t["table_name"] for t in metadata]

    def is_indexed(self, db_id: str) -> bool:
        """Check if a database has been indexed."""
        collection_name = self._collection_name(db_id)
        try:
            collection = self.client.get_collection(collection_name)
            return collection.count() > 0
        except Exception:
            return False
