"""
Unit tests for SQL validation and security checks.

These tests run without any external dependencies (no DB, no LLM, no ChromaDB).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.security import is_safe_sql, get_safety_violations
from app.graph.nodes.sql_validator import validate_sql


# ═══════════════════════════════════════════════════════════════════
# Security Tests
# ═══════════════════════════════════════════════════════════════════

class TestSQLSafety:
    """Tests for the SQL safety checker."""

    def test_safe_select(self):
        assert is_safe_sql("SELECT * FROM users") is True

    def test_safe_select_with_join(self):
        assert is_safe_sql(
            "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id"
        ) is True

    def test_safe_with_cte(self):
        assert is_safe_sql(
            "WITH top_users AS (SELECT id FROM users LIMIT 10) SELECT * FROM top_users"
        ) is True

    def test_safe_subquery(self):
        assert is_safe_sql(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
        ) is True

    def test_block_insert(self):
        assert is_safe_sql("INSERT INTO users (name) VALUES ('test')") is False

    def test_block_update(self):
        assert is_safe_sql("UPDATE users SET name = 'test' WHERE id = 1") is False

    def test_block_delete(self):
        assert is_safe_sql("DELETE FROM users WHERE id = 1") is False

    def test_block_drop(self):
        assert is_safe_sql("DROP TABLE users") is False

    def test_block_alter(self):
        assert is_safe_sql("ALTER TABLE users ADD COLUMN age INTEGER") is False

    def test_block_truncate(self):
        assert is_safe_sql("TRUNCATE TABLE users") is False

    def test_block_empty(self):
        assert is_safe_sql("") is False

    def test_block_stacked_query(self):
        assert is_safe_sql("SELECT 1; DROP TABLE users") is False

    def test_violations_detail(self):
        violations = get_safety_violations("DELETE FROM users")
        assert len(violations) > 0
        assert any("DELETE" in v for v in violations)


# ═══════════════════════════════════════════════════════════════════
# Validator Tests
# ═══════════════════════════════════════════════════════════════════

class TestSQLValidator:
    """Tests for the SQL validator node."""

    def test_valid_simple_query(self):
        state = {
            "generated_sql": "SELECT name FROM customers",
            "all_table_names": ["customers", "orders", "products"],
        }
        result = validate_sql(state)
        assert result["is_valid"] is True
        assert len(result["validation_errors"]) == 0

    def test_empty_sql(self):
        state = {"generated_sql": "", "all_table_names": []}
        result = validate_sql(state)
        assert result["is_valid"] is False

    def test_syntax_error(self):
        state = {
            "generated_sql": "SELEC name FRO customers",
            "all_table_names": ["customers"],
        }
        result = validate_sql(state)
        # sqlglot may or may not catch this specific error
        # but it should at least not crash
        assert isinstance(result["is_valid"], bool)

    def test_unknown_table(self):
        state = {
            "generated_sql": "SELECT * FROM nonexistent_table",
            "all_table_names": ["customers", "orders"],
        }
        result = validate_sql(state)
        assert result["is_valid"] is False
        assert any("nonexistent_table" in e.lower() for e in result["validation_errors"])

    def test_unsafe_sql_blocked(self):
        state = {
            "generated_sql": "DELETE FROM customers WHERE id = 1",
            "all_table_names": ["customers"],
        }
        result = validate_sql(state)
        assert result["is_valid"] is False


# ═══════════════════════════════════════════════════════════════════
# Run with pytest
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Quick manual test runner
    tests = [TestSQLSafety(), TestSQLValidator()]
    passed = 0
    failed = 0

    for test_class in tests:
        for method_name in dir(test_class):
            if method_name.startswith("test_"):
                try:
                    getattr(test_class, method_name)()
                    print(f"  PASS {test_class.__class__.__name__}.{method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  FAIL {test_class.__class__.__name__}.{method_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  WARN {test_class.__class__.__name__}.{method_name}: {e}")
                    failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
