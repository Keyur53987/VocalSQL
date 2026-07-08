"""
Multi-database connection manager.

Handles registration, connection pooling, and query execution for
multiple databases (SQLite, PostgreSQL, MySQL, etc.) via SQLAlchemy.
"""

import json
import os
import threading
import logging
from typing import Dict, Optional, Any, List
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages connections to multiple databases."""

    def __init__(self, config_path: str = "./data/databases.json"):
        self.config_path = config_path
        self._engines: Dict[str, Engine] = {}
        self._lock = threading.Lock()
        self._configs: Dict[str, dict] = {}
        self._last_mtime = 0.0
        self._load_configs()

    # ── Configuration Persistence ─────────────────────────────────

    def _check_reload(self):
        """Check if the config file was modified by another worker and reload."""
        if os.path.exists(self.config_path):
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime > self._last_mtime:
                self._load_configs()

    def _load_configs(self):
        """Load database configurations from JSON file."""
        if os.path.exists(self.config_path):
            try:
                self._last_mtime = os.path.getmtime(self.config_path)
                with open(self.config_path, "r") as f:
                    self._configs = json.load(f)
                logger.info(f"Loaded {len(self._configs)} database config(s)")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load database configs: {e}")
                self._configs = {}
        else:
            self._configs = {}

    def _save_configs(self):
        """Persist database configurations to JSON file."""
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._configs, f, indent=2)

    # ── Database Registration ─────────────────────────────────────

    def register_database(
        self,
        db_id: str,
        connection_string: str,
        name: str = "",
        description: str = "",
    ) -> bool:
        """Register a new database connection."""
        self._configs[db_id] = {
            "connection_string": connection_string,
            "name": name or db_id,
            "description": description,
        }
        self._save_configs()

        # Clear any cached engine
        if db_id in self._engines:
            try:
                self._engines[db_id].dispose()
            except Exception:
                pass
            del self._engines[db_id]

        logger.info(f"Registered database '{db_id}'")
        return True

    def remove_database(self, db_id: str) -> bool:
        """Remove a registered database."""
        removed = False
        if db_id in self._configs:
            del self._configs[db_id]
            self._save_configs()
            removed = True
        if db_id in self._engines:
            try:
                self._engines[db_id].dispose()
            except Exception:
                pass
            del self._engines[db_id]
        return removed

    def list_databases(self) -> Dict[str, dict]:
        """List all registered databases (without connection strings)."""
        self._check_reload()
        return {
            db_id: {"name": cfg["name"], "description": cfg["description"]}
            for db_id, cfg in self._configs.items()
        }

    def has_database(self, db_id: str) -> bool:
        self._check_reload()
        return db_id in self._configs

    # ── Engine Management ─────────────────────────────────────────

    def get_engine(self, db_id: str) -> Engine:
        """Get or create a SQLAlchemy engine for the given database."""
        self._check_reload()
        if db_id not in self._engines:
            with self._lock:
                if db_id not in self._engines:
                    config = self._configs.get(db_id)
                    if not config:
                        raise ValueError(f"Database '{db_id}' is not registered")

                    conn_str = config["connection_string"]
                    engine_kwargs = {"pool_pre_ping": True}

                    # SQLite doesn't support connection pooling the same way
                    if conn_str.startswith("sqlite"):
                        engine_kwargs["connect_args"] = {"check_same_thread": False}
                    else:
                        engine_kwargs.update({
                            "pool_size": 5,
                            "max_overflow": 10,
                            "pool_recycle": 3600,
                        })

                    engine = create_engine(conn_str, **engine_kwargs)

                    # Enable WAL mode for SQLite (better concurrent reads)
                    if conn_str.startswith("sqlite"):
                        @event.listens_for(engine, "connect")
                        def _set_sqlite_pragma(dbapi_conn, _):
                            cursor = dbapi_conn.cursor()
                            cursor.execute("PRAGMA journal_mode=WAL")
                            cursor.execute("PRAGMA foreign_keys=ON")
                            cursor.close()

                    self._engines[db_id] = engine
                    logger.info(f"Created engine for database '{db_id}'")

        return self._engines[db_id]

    def get_dialect(self, db_id: str) -> str:
        """Get the SQL dialect name (sqlite, postgresql, mysql, etc.)."""
        engine = self.get_engine(db_id)
        return engine.dialect.name

    # ── Query Execution ───────────────────────────────────────────

    def execute_query(
        self,
        db_id: str,
        sql: str,
        timeout: int = 10,
        max_rows: int = 100,
    ) -> Dict[str, Any]:
        """
        Execute a read-only SQL query and return results.

        Returns:
            {"columns": [...], "rows": [...], "row_count": int, "truncated": bool}
        """
        engine = self.get_engine(db_id)

        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())

            rows = []
            truncated = False
            for i, row in enumerate(result):
                if i >= max_rows:
                    truncated = True
                    break
                # Convert row to dict with JSON-safe values
                row_dict = {}
                for col, val in zip(columns, row):
                    if val is None:
                        row_dict[col] = None
                    else:
                        row_dict[col] = str(val) if not isinstance(val, (int, float, bool)) else val
                rows.append(row_dict)

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": truncated,
            }

    # ── Health Check ──────────────────────────────────────────────

    def test_connection(self, db_id: str) -> bool:
        """Test if a database connection is working."""
        try:
            engine = self.get_engine(db_id)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(f"Connection test failed for '{db_id}': {e}")
            return False

    def dispose_all(self):
        """Dispose all connection pools (cleanup on shutdown)."""
        for db_id, engine in self._engines.items():
            try:
                engine.dispose()
            except Exception:
                pass
        self._engines.clear()
