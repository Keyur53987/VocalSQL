"""
SQL validator node — deterministic, zero-LLM-cost validation.

Three validation layers:
1. Syntax check (sqlglot parser)
2. Safety check (block data modifications)
3. Schema compliance (verify tables/columns exist)
"""

import logging
import sqlglot
from app.utils.security import is_safe_sql, get_safety_violations

logger = logging.getLogger(__name__)


def validate_sql(state: dict) -> dict:
    """
    Validate generated SQL through 3 deterministic layers.

    Returns partial state with 'is_valid' and 'validation_errors'.
    """
    sql = state.get("generated_sql", "").strip()
    all_table_names = state.get("all_table_names", [])

    errors = []

    # ── Layer 0: Empty check ─────────────────────────────────────
    if not sql:
        return {
            "is_valid": False,
            "validation_errors": ["No SQL query was generated."],
        }

    # ── Layer 1: Syntax Validation (sqlglot) ─────────────────────
    try:
        parsed = sqlglot.parse(sql)
        if not parsed or not parsed[0]:
            errors.append("SQL parsing returned empty result.")
    except sqlglot.errors.ParseError as e:
        errors.append(f"SQL syntax error: {str(e)[:200]}")
    except Exception as e:
        # sqlglot may raise other errors for very malformed SQL
        errors.append(f"SQL parsing failed: {str(e)[:200]}")

    # ── Layer 2: Safety Validation ───────────────────────────────
    safety_violations = get_safety_violations(sql)
    if safety_violations:
        errors.extend(safety_violations)

    # ── Layer 3: Schema Compliance ───────────────────────────────
    if all_table_names and not errors:
        # Extract table names referenced in the SQL
        try:
            parsed_ast = sqlglot.parse_one(sql)
            referenced_tables = set()
            for table_node in parsed_ast.find_all(sqlglot.exp.Table):
                table_name = table_node.name
                if table_name:
                    referenced_tables.add(table_name.lower())

            known_tables = {t.lower() for t in all_table_names}
            unknown_tables = referenced_tables - known_tables

            if unknown_tables:
                errors.append(
                    f"Unknown table(s) referenced: {', '.join(sorted(unknown_tables))}. "
                    f"Available tables: {', '.join(sorted(known_tables))}"
                )
        except Exception as e:
            # Don't fail validation if table extraction fails
            logger.warning(f"Could not extract table names for compliance check: {e}")

    is_valid = len(errors) == 0

    if is_valid:
        logger.info(f"SQL validation passed: {sql[:80]}...")
    else:
        logger.warning(f"SQL validation failed with {len(errors)} error(s): {errors}")

    return {
        "is_valid": is_valid,
        "validation_errors": errors,
    }
