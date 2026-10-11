import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from anki_addons_mcp.domain.errors import InvalidQuery

FLAT_COLUMNS: list[tuple[str, str, str]] = [
    ("id", "id", "BIGINT, AnkiWeb addon id"),
    ("title", "anki_web.title", "VARCHAR"),
    ("url", "anki_web.addon_page_url", "VARCHAR, AnkiWeb page"),
    ("contact_author_url", "anki_web.contact_author_url", "VARCHAR"),
    ("rating", "anki_web.rating", "BIGINT, AnkiWeb rating"),
    ("likes", "anki_web.likes", "BIGINT"),
    ("dislikes", "anki_web.dislikes", "BIGINT"),
    ("update_date", "anki_web.update_date", "VARCHAR, YYYY-MM-DD of the last AnkiWeb upload"),
    ("anki_version", "anki_web.anki_version",
     "VARCHAR, newest supported Anki version as AnkiWeb lists it: '25.02~' (tested), '<=2.1.66' (hard), '' (unknown)"),
    ("anki_point_version", "anki_web.anki_point_version",
     "BIGINT, anki_version as Anki's point version: 2.1.x -> x, YY.MM[.PP] -> YYMMPP (sortable)"),
    ("anki_version_kind", "anki_web.anki_version_kind",
     ("VARCHAR, meaning of the upper version: 'hard' (Anki disables the addon on newer versions), "
      "'tested' (tested up to it, newer still run it), 'open' (no upper limit), 'unknown'")),
    ("branches", "anki_web.branches",
     ("STRUCT(min_version, max_version, updated, min_point_version, max_point_version, max_version_kind)[], "
      "AnkiWeb branches; raw max_version '+' = open, 'B+' = tested, 'B' = hard, empty = unknown")),
    ("links", "anki_web.links", "VARCHAR[], links found on the AnkiWeb page"),
    ("ai_declaration_markers", "anki_web.ai_declaration_markers", "VARCHAR[], AI-usage words in the description"),
    ("description_language", "anki_web.description_language", "VARCHAR, ISO code"),
    ("description_language_confidence", "anki_web.description_language_confidence", "DOUBLE"),
    ("description", "anki_web.description", "VARCHAR, AnkiWeb description as plain text"),
    ("has_github", "github IS NOT NULL", "BOOLEAN"),
    ("github_user", "github.user", "VARCHAR"),
    ("github_repo", "github.repo", "VARCHAR"),
    ("github_languages", "github.languages", "VARCHAR[]"),
    ("github_stars", "github.stars", "BIGINT"),
    ("github_last_commit", "github.last_commit", "VARCHAR, ISO timestamp"),
    ("github_links", "github.links", "STRUCT(url, user, repo)[]"),
    ("github_action_count", "github.action_count", "BIGINT, GitHub Actions workflows"),
    ("github_tests_count", "github.tests_count", "BIGINT, test files"),
    ("github_license", "github.license", "VARCHAR, SPDX id"),
    ("github_forks", "github.forks", "BIGINT"),
    ("github_open_issues", "github.open_issues", "BIGINT"),
    ("github_size_kb", "github.size_kb", "BIGINT"),
    ("github_topics", "github.topics", "VARCHAR[]"),
    ("github_repo_description", "github.repo_description", "VARCHAR"),
    ("github_homepage", "github.homepage", "VARCHAR"),
    ("github_archived", "github.archived", "BOOLEAN"),
    ("github_pushed_at", "github.pushed_at", "VARCHAR, ISO timestamp"),
    ("github_created_at", "github.created_at", "VARCHAR, ISO timestamp"),
    ("github_primary_language", "github.primary_language", "VARCHAR"),
    ("github_language_bytes", "github.language_bytes", "STRUCT(name, bytes)[]"),
    ("github_manifest", "CAST(to_json(github.manifest) AS VARCHAR)",
     ("VARCHAR, JSON of the addon manifest.json; "
      "min/max_point_version as written (negative max = hard), min/max_version and max_version_kind parsed")),
    ("github_dependencies", "CAST(github.dependencies AS VARCHAR[])", "VARCHAR[], Python dependencies"),
    ("github_readme", "CAST(github.readme AS VARCHAR)", "VARCHAR, README text"),
    ("github_ai_tooling_markers", "github.ai_tooling_markers", "VARCHAR[], AI coding tool traces in the repo"),
    ("has_forum", "forum IS NOT NULL AND forum.anki_forum_url IS NOT NULL", "BOOLEAN"),
    ("forum_url", "forum.anki_forum_url", "VARCHAR"),
    ("forum_topic_slug", "forum.topic_slug", "VARCHAR"),
    ("forum_topic_id", "forum.topic_id", "BIGINT"),
    ("forum_last_posted_at", "CAST(forum.last_posted_at AS VARCHAR)", "VARCHAR, timestamp"),
    ("forum_posts_count", "CAST(forum.posts_count AS BIGINT)", "BIGINT"),
    ("ai_summary", "ai.summary", "VARCHAR, LLM-generated summary (may be inaccurate)"),
    ("ai_model", "ai.model", "VARCHAR, model that wrote ai_summary"),
    ("ai_tags", "ai.tags", "VARCHAR[], LLM-picked tags (may be inaccurate), names from the `tags` table"),
]
TOPICS_TEXT = "topics_text"
TAGS_TEXT = "tags_text"
HELPER_COLUMNS = [TOPICS_TEXT, TAGS_TEXT]
SEARCH_COLUMNS = ["title", "description", "ai_summary", TOPICS_TEXT, TAGS_TEXT, "github_repo_description"]
SQL_VIEW = "addons"
TAGS_VIEW = "tags"
TAG_COLUMNS: list[tuple[str, str]] = [
    ("name", "VARCHAR, tag name as used in addons.ai_tags"),
    ("group", "VARCHAR, 'function' (what the addon does) or 'status' (paid, obsolete, beta, ...)"),
    ("description", "VARCHAR, meaning of the tag"),
]
_DENIED_FUNCTIONS = frozenset({"getenv", "current_setting"})


def flat_select(parquet_path: str) -> str:
    columns = ",\n  ".join(f"{expr} AS {name}" for name, expr, _ in FLAT_COLUMNS)
    escaped = parquet_path.replace("'", "''")
    return (f"SELECT\n  {columns},\n  array_to_string(github.topics, ' ') AS {TOPICS_TEXT},\n"
            f"  array_to_string(ai.tags, ' ') AS {TAGS_TEXT}\n"
            f"FROM read_parquet('{escaped}')")


def tags_select(parquet_path: str) -> str:
    escaped = parquet_path.replace("'", "''")
    return f"SELECT name, \"group\", description FROM read_parquet('{escaped}')"


def schema_description() -> str:
    lines = [f"- {name}: {desc}" for name, _, desc in FLAT_COLUMNS]
    tag_lines = [f"- {name}: {desc}" for name, desc in TAG_COLUMNS]
    return (f"Table `{SQL_VIEW}` (one row per addon of the requested snapshot):\n" + "\n".join(lines)
            + f"\n\nTable `{TAGS_VIEW}` (the tag vocabulary of the snapshot, quote \"group\"):\n"
            + "\n".join(tag_lines))


def _walk(node: Any, ctes: set[str], tables: list[tuple[str, str, str]]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, ctes, tables)
        return
    if not isinstance(node, dict):
        return
    kind = node.get("type")
    if kind == "TABLE_FUNCTION":
        raise InvalidQuery("Table functions are not allowed in query_sql")
    if kind == "BASE_TABLE":
        tables.append((node.get("catalog_name", ""), node.get("schema_name", ""), node.get("table_name", "")))
    if node.get("class") == "FUNCTION" and str(node.get("function_name", "")).lower() in _DENIED_FUNCTIONS:
        raise InvalidQuery(f"Function {node['function_name']} is not allowed in query_sql")
    cte_map = node.get("cte_map")
    if isinstance(cte_map, dict):
        for entry in cte_map.get("map", []):
            ctes.add(str(entry.get("key", "")).lower())
    for value in node.values():
        _walk(value, ctes, tables)


def validate_readonly_select(con: duckdb.DuckDBPyConnection, sql: str, allowed_tables: set[str]) -> None:
    try:
        statements = con.extract_statements(sql)
    except duckdb.Error as e:
        raise InvalidQuery(f"SQL parse error: {e}") from e
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise InvalidQuery("Exactly one SELECT statement is allowed")
    row = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()
    ast = json.loads(row[0]) if row else {"error": True, "error_message": "cannot parse"}
    if ast.get("error"):
        raise InvalidQuery(f"SQL rejected: {ast.get('error_message')}")
    ctes: set[str] = set()
    tables: list[tuple[str, str, str]] = []
    _walk(ast["statements"], ctes, tables)
    allowed = {t.lower() for t in allowed_tables} | ctes
    for catalog, schema, table in tables:
        if catalog or schema or table.lower() not in allowed:
            qualified = ".".join(p for p in (catalog, schema, table) if p)
            raise InvalidQuery(f"Unknown table '{qualified}'. Only {sorted(allowed_tables)} can be queried")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return str(value)
