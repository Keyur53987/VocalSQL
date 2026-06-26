"""
Database schema introspector.

Extracts table metadata (columns, types, PKs, FKs, sample values)
from any SQLAlchemy-supported database for RAG indexing.
"""

import logging
from typing import Dict, List, Any
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


class SchemaIntrospector:
    """Extracts schema metadata from databases for RAG indexing."""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def introspect(self, db_id: str) -> List[Dict[str, Any]]:
        """
        Introspect a database and return full metadata for all tables.

        Returns:
            List of table metadata dicts with columns, FKs, samples, etc.
        """
        engine = self.db_manager.get_engine(db_id)
        inspector = inspect(engine)
        tables_metadata = []

        table_names = inspector.get_table_names()
        logger.info(f"Introspecting {len(table_names)} tables in '{db_id}'")

        for table_name in table_names:
            try:
                table_meta = self._introspect_table(engine, inspector, table_name)
                tables_metadata.append(table_meta)
            except Exception as e:
                logger.warning(f"Failed to introspect table '{table_name}': {e}")
                continue

        return tables_metadata

    def _introspect_table(
        self, engine, inspector, table_name: str
    ) -> Dict[str, Any]:
        """Introspect a single table."""
        # ── Columns ──
        columns = []
        for col in inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "primary_key": False,  # updated below
            })

        # ── Primary Keys ──
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_columns = pk_constraint.get("constrained_columns", []) if pk_constraint else []
        for col in columns:
            if col["name"] in pk_columns:
                col["primary_key"] = True

        # ── Foreign Keys ──
        foreign_keys = []
        for fk in inspector.get_foreign_keys(table_name):
            for i, col_name in enumerate(fk.get("constrained_columns", [])):
                ref_cols = fk.get("referred_columns", [])
                foreign_keys.append({
                    "column": col_name,
                    "references_table": fk.get("referred_table", ""),
                    "references_column": ref_cols[i] if i < len(ref_cols) else "",
                })

        # ── Indexes ──
        indexes = []
        try:
            for idx in inspector.get_indexes(table_name):
                indexes.append({
                    "name": idx.get("name", ""),
                    "columns": idx.get("column_names", []),
                    "unique": idx.get("unique", False),
                })
        except Exception:
            pass

        # ── Sample Values ──
        sample_values = self._get_sample_values(
            engine, table_name, [c["name"] for c in columns]
        )

        # ── Row Count ──
        row_count = self._get_row_count(engine, table_name)

        return {
            "table_name": table_name,
            "columns": columns,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
            "sample_values": sample_values,
            "row_count": row_count,
        }

    def _get_sample_values(
        self, engine, table_name: str, column_names: List[str], limit: int = 3
    ) -> Dict[str, List[str]]:
        """Get a few distinct sample values per column for context."""
        samples = {}
        dialect = engine.dialect.name

        try:
            with engine.connect() as conn:
                for col_name in column_names:
                    try:
                        # Use dialect-appropriate quoting
                        if dialect == "mysql":
                            quoted_col = f"`{col_name}`"
                            quoted_table = f"`{table_name}`"
                        else:
                            # SQLite and PostgreSQL use double quotes
                            quoted_col = f'"{col_name}"'
                            quoted_table = f'"{table_name}"'

                        sql = (
                            f"SELECT DISTINCT {quoted_col} FROM {quoted_table} "
                            f"WHERE {quoted_col} IS NOT NULL LIMIT {limit}"
                        )
                        result = conn.execute(text(sql))
                        samples[col_name] = [str(row[0]) for row in result.fetchall()]
                    except Exception:
                        samples[col_name] = []
        except Exception as e:
            logger.warning(f"Failed to get sample values for '{table_name}': {e}")

        return samples

    def _get_row_count(self, engine, table_name: str) -> int:
        """Get approximate row count for a table."""
        dialect = engine.dialect.name
        try:
            with engine.connect() as conn:
                if dialect == "mysql":
                    quoted = f"`{table_name}`"
                else:
                    quoted = f'"{table_name}"'
                result = conn.execute(text(f"SELECT COUNT(*) FROM {quoted}"))
                return result.scalar() or 0
        except Exception:
            return 0

    def get_all_table_names(self, db_id: str) -> List[str]:
        """Get just the table names for a database (fast, no introspection)."""
        engine = self.db_manager.get_engine(db_id)
        inspector = inspect(engine)
        return inspector.get_table_names()
