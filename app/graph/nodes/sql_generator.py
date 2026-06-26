"""
SQL generator node — the core LLM call that converts NL to SQL.

Uses Google Gemini with a carefully crafted prompt that includes:
1. System instructions (output SQL only, use only provided schema)
2. Retrieved schema subset (from RAG)
3. Few-shot examples (from RAG)
4. User question
5. Target SQL dialect

Temperature is set to 0.0 for maximum determinism.
"""

import re
import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.services import get_llm

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an expert SQL query generator. Your job is to convert natural language questions into accurate, efficient SQL queries.

## CRITICAL RULES (MUST FOLLOW):
1. Generate ONLY a single SQL SELECT query. No explanations, no markdown, no comments.
2. Use ONLY the tables and columns listed in the DATABASE SCHEMA section below. Do NOT invent or guess table/column names.
3. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or any data-modifying statement.
4. Use the correct SQL dialect: {dialect}
5. Use table aliases for multi-table queries (e.g., SELECT c.name FROM customers c).
6. Use appropriate JOINs based on the foreign key relationships shown in the schema.
7. When filtering text, use LIKE with appropriate wildcards for flexible matching.
8. For date operations in SQLite, use strftime(). For PostgreSQL, use date_trunc() or EXTRACT(). For MySQL, use DATE_FORMAT().
9. Always include ORDER BY for ranking/top-N queries.
10. Use LIMIT to restrict results to a reasonable number (default 50 if not specified).

## OUTPUT FORMAT:
Return ONLY the raw SQL query. No markdown code blocks, no explanations, no prefixes like "SQL:" or "Query:".

Example of correct output:
SELECT name, price FROM products WHERE category = 'Electronics' ORDER BY price DESC LIMIT 10"""


def generate_sql(state: dict) -> dict:
    """
    Generate SQL from the user's natural language query using LLM.

    Uses the retrieved schema context and few-shot examples to
    produce accurate SQL with minimal hallucination.
    """
    user_query = state.get("user_query", "")
    schema_context = state.get("schema_context", "")
    few_shot_examples = state.get("few_shot_examples", [])
    dialect = state.get("db_dialect", "sqlite")

    if not schema_context or schema_context == "No schema information available.":
        return {
            "generated_sql": "",
            "error_message": "Cannot generate SQL: no schema context available.",
        }

    # Build the prompt
    system_msg = SYSTEM_PROMPT.format(dialect=dialect)

    # Add few-shot examples
    examples_text = ""
    if few_shot_examples:
        examples_parts = []
        for ex in few_shot_examples:
            examples_parts.append(
                f"Question: {ex['question']}\nSQL: {ex['sql']}"
            )
        examples_text = "\n\n".join(examples_parts)

    # Construct the human message
    human_parts = [
        f"## DATABASE SCHEMA:\n{schema_context}",
    ]
    if examples_text:
        human_parts.append(f"## EXAMPLE QUERIES:\n{examples_text}")
    human_parts.append(f"## USER QUESTION:\n{user_query}")
    human_parts.append("## YOUR SQL QUERY:")

    human_msg = "\n\n".join(human_parts)

    # Call LLM
    llm = get_llm()
    try:
        response = llm.invoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=human_msg),
        ])

        raw_sql = response.content.strip()

        # Clean up the response — remove markdown code blocks if present
        sql = _clean_sql_response(raw_sql)

        logger.info(f"Generated SQL: {sql[:120]}...")
        return {"generated_sql": sql}

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {
            "generated_sql": "",
            "error_message": f"SQL generation failed: {str(e)}",
        }


def _clean_sql_response(raw: str) -> str:
    """
    Clean LLM response to extract pure SQL.

    Handles cases where the LLM wraps output in markdown code blocks,
    adds explanations, or includes prefixes.
    """
    text = raw.strip()

    # Remove markdown code blocks
    code_block = re.search(r"```(?:sql)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if code_block:
        text = code_block.group(1).strip()

    # Remove common prefixes
    for prefix in ["SQL:", "Query:", "sql:", "query:", "Answer:", "Here is the SQL:"]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    # Remove trailing semicolons (we add our own if needed)
    text = text.rstrip(";").strip()

    # Ensure it's a single query (no stacked queries)
    if ";" in text:
        text = text.split(";")[0].strip()

    return text
