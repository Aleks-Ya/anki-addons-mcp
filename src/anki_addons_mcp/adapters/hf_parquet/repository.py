import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

import duckdb

from anki_addons_mcp.adapters.hf_parquet.mapping import CARD_COLUMNS, row_to_card, row_to_details
from anki_addons_mcp.adapters.hf_parquet.source import DatasetSource
from anki_addons_mcp.adapters.hf_parquet.sql import (
    FLAT_COLUMNS,
    HELPER_COLUMNS,
    SEARCH_COLUMNS,
    SQL_VIEW,
    TAGS_VIEW,
    flat_select,
    json_safe,
    schema_description,
    tags_select,
    validate_readonly_select,
)
from anki_addons_mcp.domain.compatibility import require_point
from anki_addons_mcp.domain.errors import DataSourceUnavailable, InvalidQuery, SnapshotNotFound
from anki_addons_mcp.domain.models import (
    NONE_GROUP,
    AddonCard,
    AddonDetails,
    AddonHistoryPoint,
    Aggregation,
    GroupField,
    Page,
    SnapshotInfo,
    SqlResult,
    Tag,
    TextKind,
)
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.domain.query import AddonFilters, AddonQuery, SortField

log = logging.getLogger(__name__)

_PARALLEL_DOWNLOADS = 4

_DETAIL_COLUMNS = [name for name, _, _ in FLAT_COLUMNS if name not in ("description", "github_readme")]

# 95% Wilson lower bound of likes among votes; mirrors domain.models.approval_score.
_APPROVAL = ("(CASE WHEN coalesce(likes, 0) + coalesce(dislikes, 0) = 0 THEN 0.0 ELSE "
             "(coalesce(likes, 0) + 1.9208 - 1.96 * sqrt(coalesce(likes, 0) * coalesce(dislikes, 0) "
             "/ (coalesce(likes, 0) + coalesce(dislikes, 0)) + 0.9604)) "
             "/ (coalesce(likes, 0) + coalesce(dislikes, 0) + 3.8416) END)")

_SORT_EXPR = {
    SortField.RELEVANCE: "score",
    SortField.RATING: _APPROVAL,
    SortField.LIKES: "likes",
    SortField.STARS: "github_stars",
    SortField.UPDATE_DATE: "NULLIF(update_date, '')",
    SortField.LAST_COMMIT: "github_last_commit",
    SortField.FORUM_POSTS: "forum_posts_count",
    SortField.ANKI_VERSION: "anki_point_version",
}

_SCALAR_GROUPS = {
    GroupField.LICENSE: "github_license",
    GroupField.PRIMARY_LANGUAGE: "github_primary_language",
    GroupField.DESCRIPTION_LANGUAGE: "description_language",
    GroupField.ANKI_VERSION: "anki_version",
    GroupField.ANKI_VERSION_KIND: "anki_version_kind",
    GroupField.UPDATE_YEAR: "left(update_date, 4)",
}

_LIST_GROUPS = {
    GroupField.GITHUB_TOPIC: "github_topics",
    GroupField.AI_DECLARATION_MARKER: "ai_declaration_markers",
    GroupField.AI_TOOLING_MARKER: "github_ai_tooling_markers",
    GroupField.AI_TAG: "ai_tags",
}

_LOWER_TAGS = "list_transform(ai_tags, lambda x: lower(x))"

# A branch supports (or likely supports) point version $p; mirrors domain.compatibility.branch_support.
_COMPATIBLE_BRANCH = ("len(list_filter(branches, lambda b: b.min_point_version <= $p AND ("
                      "b.max_version_kind IN ('open', 'tested') "
                      "OR (b.max_version_kind = 'hard' AND $p <= b.max_point_version) "
                      "OR (b.max_version_kind = 'unknown' AND b.min_point_version = $p)))) > 0")


def _lower_all(values: list[str]) -> list[str]:
    return [v.lower() for v in values]


_Add = Callable[..., None]


def _anki_web_filters(f: AddonFilters, add: _Add) -> None:
    if f.addon_ids is not None:
        add("list_contains(?, id)", f.addon_ids)
    if f.min_rating is not None:
        add("rating >= ?", f.min_rating)
    if f.min_likes is not None:
        add("likes >= ?", f.min_likes)
    if f.has_forum is not None:
        add("has_forum = ?", f.has_forum)
    if f.description_language is not None:
        add("lower(description_language) = lower(?)", f.description_language)
    if f.updated_after is not None:
        add("NULLIF(update_date, '') >= ?", f.updated_after.isoformat())
    if f.updated_before is not None:
        add("NULLIF(update_date, '') <= ?", f.updated_before.isoformat())
    if f.has_ai_declaration is not None:
        add("(coalesce(len(ai_declaration_markers), 0) > 0) = ?", f.has_ai_declaration)


def _github_filters(f: AddonFilters, add: _Add) -> None:
    if f.min_stars is not None:
        add("has_github AND github_stars >= ?", f.min_stars)
    if f.has_github is not None:
        add("has_github = ?", f.has_github)
    if f.has_tests is not None:
        add("(coalesce(github_tests_count, 0) > 0) = ?", f.has_tests)
    if f.language is not None:
        add("(list_contains(list_transform(github_languages, lambda x: lower(x)), lower(?))"
            " OR lower(github_primary_language) = lower(?))", f.language, f.language)
    if f.github_user is not None:
        add("lower(github_user) = lower(?)", f.github_user)
    if f.archived is not None:
        add("coalesce(github_archived, false) = ?", f.archived)
    if f.has_ai_tooling is not None:
        add("(coalesce(len(github_ai_tooling_markers), 0) > 0) = ?", f.has_ai_tooling)


def _version_and_tag_filters(f: AddonFilters, add: _Add) -> None:
    if f.compatible_with_anki is not None:
        add(_COMPATIBLE_BRANCH.replace("$p", str(require_point(f.compatible_with_anki))))
    if f.anki_version_kind is not None:
        add("anki_version_kind = ?", f.anki_version_kind.value)
    if f.anki_version_at_least is not None:
        add("anki_point_version >= ?", require_point(f.anki_version_at_least))
    if f.tags:
        add(f"list_has_all({_LOWER_TAGS}, ?)", _lower_all(f.tags))
    if f.exclude_tags:
        add(f"NOT list_has_any(coalesce({_LOWER_TAGS}, []), ?)", _lower_all(f.exclude_tags))


def _filters_sql(f: AddonFilters) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    def add(clause: str, *values: Any) -> None:
        clauses.append(clause)
        params.extend(values)

    _anki_web_filters(f, add)
    _github_filters(f, add)
    _version_and_tag_filters(f, add)
    return [f"coalesce({c}, false)" for c in clauses], params


def _dicts(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    names = [d[0] for d in cursor.description or []]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


class _State:
    def __init__(self, source: DatasetSource):
        self.source = source
        self.con = duckdb.connect(":memory:")
        self.relations: dict[date, str] = {}
        self.tag_tables: dict[date, str] = {}
        self.fts: set[str] = set()
        self.lock = threading.RLock()
        self.fts_available = self._load_fts()

    def _load_fts(self) -> bool:
        try:
            self.con.execute("LOAD fts")
            return True
        except duckdb.Error:
            try:
                self.con.execute("INSTALL fts")
                self.con.execute("LOAD fts")
                return True
            except duckdb.Error as e:
                log.warning("DuckDB fts extension unavailable, falling back to substring search: %s", e)
                return False

    def relation(self, snapshot: date | None) -> str:
        resolved = snapshot or self.source.latest_date()
        with self.lock:
            if resolved in self.relations:
                return self.relations[resolved]
        if resolved not in self.source.snapshot_dates():
            raise SnapshotNotFound(resolved)
        path = str(self.source.data_file(resolved))
        with self.lock:
            if resolved in self.relations:
                return self.relations[resolved]
            name = f"snap_{resolved.strftime('%Y%m%d')}"
            if resolved == self.source.latest_date():
                self.con.execute(f"CREATE TABLE {name} AS {flat_select(path)}")
                self._index(name)
            else:
                self.con.execute(f"CREATE VIEW {name} AS {flat_select(path)}")
            self.relations[resolved] = name
            log.info("Loaded snapshot %s as %s", resolved, name)
            return name

    def tag_table(self, snapshot: date | None) -> str:
        resolved = snapshot or self.source.latest_date()
        with self.lock:
            if resolved in self.tag_tables:
                return self.tag_tables[resolved]
        if resolved not in self.source.snapshot_dates():
            raise SnapshotNotFound(resolved)
        path = str(self.source.tags_file(resolved))
        with self.lock:
            if resolved not in self.tag_tables:
                name = f"tags_{resolved.strftime('%Y%m%d')}"
                self.con.execute(f"CREATE TABLE {name} AS {tags_select(path)}")
                self.tag_tables[resolved] = name
            return self.tag_tables[resolved]

    def _index(self, table: str) -> None:
        if not self.fts_available:
            return
        columns = ", ".join(f"'{c}'" for c in SEARCH_COLUMNS)
        self.con.execute(f"PRAGMA create_fts_index('{table}', 'id', {columns}, "
                         "stemmer='porter', stopwords='english', overwrite=1)")
        self.fts.add(table)

    def cursor(self) -> duckdb.DuckDBPyConnection:
        return self.con.cursor()

    def close(self) -> None:
        self.con.close()


class DuckDbAddonRepository(AddonRepository):
    def __init__(self, source_factory: Callable[[], DatasetSource]):
        self._source_factory = source_factory
        self._state: _State | None = None
        self._state_lock = threading.Lock()

    def _current(self) -> _State:
        state = self._state
        if state is not None:
            return state
        with self._state_lock:
            if self._state is None:
                try:
                    self._state = _State(self._source_factory())
                except Exception as e:
                    raise DataSourceUnavailable(f"Cannot open the dataset: {e}") from e
            return self._state

    def warm_up(self) -> None:
        self._current().relation(None)
        self.list_snapshots()

    def refresh(self) -> bool:
        current = self._current()
        if current.source.head_revision() == current.source.revision:
            return False
        new_state = _State(self._source_factory())
        new_state.relation(None)
        with self._state_lock:
            self._state = new_state
        log.info("Dataset changed, switched to revision %s", new_state.source.revision)
        return True

    def list_snapshots(self) -> list[SnapshotInfo]:
        source = self._current().source
        with ThreadPoolExecutor(_PARALLEL_DOWNLOADS) as pool:
            return list(pool.map(source.snapshot_info, source.snapshot_dates()))

    def _select(self, sql: str, params: list[Any], snapshot: date | None) -> list[dict[str, Any]]:
        state = self._current()
        relation = state.relation(snapshot)
        cursor = state.cursor()
        try:
            cursor.execute(sql.replace("{rel}", relation).replace("{fts}", f"fts_main_{relation}"), params)
            return _dicts(cursor)
        finally:
            cursor.close()

    def get_addon(self, addon_id: int, snapshot: date | None = None) -> AddonDetails | None:
        found = self.get_addons([addon_id], snapshot)
        return found[0] if found else None

    def get_addons(self, addon_ids: list[int], snapshot: date | None = None) -> list[AddonDetails]:
        if not addon_ids:
            return []
        rows = self._select(f"SELECT {', '.join(_DETAIL_COLUMNS)} FROM {{rel}} WHERE list_contains(?, id)",
                            [list(addon_ids)], snapshot)
        by_id = {row["id"]: row_to_details(row) for row in rows}
        return [by_id[i] for i in dict.fromkeys(addon_ids) if i in by_id]

    def find(self, query: AddonQuery, snapshot: date | None = None) -> Page[AddonCard]:
        state = self._current()
        relation = state.relation(snapshot)
        clauses, params = _filters_sql(query.filters)
        score_expr = "NULL::DOUBLE"
        score_params: list[Any] = []
        if query.has_text():
            text = (query.text or "").strip()
            if relation in state.fts:
                score_expr = "{fts}.match_bm25(id, ?)"
                score_params = [text]
            else:
                terms = [t for t in text.lower().split() if t]
                haystack = "lower(concat_ws(' ', " + ", ".join(SEARCH_COLUMNS) + "))"
                score_expr = "NULLIF(" + " + ".join(f"CAST(contains({haystack}, ?) AS DOUBLE)" for _ in terms) + ", 0)"
                score_params = terms
            clauses.append("score IS NOT NULL")
        where = " AND ".join(clauses) or "true"
        order = (f"{_SORT_EXPR[query.effective_sort()]} {'DESC' if query.descending else 'ASC'} NULLS LAST, id")
        base = (f"WITH base AS (SELECT *, {score_expr} AS score FROM {{rel}}) "
                f"SELECT {', '.join(CARD_COLUMNS)}, score FROM base WHERE {where} ORDER BY {order}")
        all_params = score_params + params
        total_rows = self._select(f"SELECT count(*) AS n FROM ({base})", all_params, snapshot)
        total = int(total_rows[0]["n"])
        paging = f" LIMIT {int(query.limit)}" if query.limit is not None else ""
        paging += f" OFFSET {int(query.offset)}" if query.offset else ""
        rows = self._select(base + paging, all_params, snapshot)
        items = [row_to_card(r, r["score"]) for r in rows]
        return Page[AddonCard](items=items, total=total, offset=query.offset, limit=query.limit)

    def get_text(self, addon_id: int, kind: TextKind, snapshot: date | None = None) -> str | None:
        column = "description" if kind == TextKind.DESCRIPTION else "github_readme"
        rows = self._select(f"SELECT {column} AS text FROM {{rel}} WHERE id = ?", [addon_id], snapshot)
        return (rows[0]["text"] or None) if rows else None

    def get_history(self, addon_id: int, from_: date | None = None, to: date | None = None) -> list[AddonHistoryPoint]:
        state = self._current()
        dates = [d for d in state.source.snapshot_dates() if not ((from_ and d < from_) or (to and d > to))]
        with ThreadPoolExecutor(_PARALLEL_DOWNLOADS) as pool:
            list(pool.map(state.relation, dates))
        points = []
        for d in dates:
            rows = self._select("SELECT title, rating, likes, dislikes, github_stars, update_date, anki_version, "
                                "anki_version_kind FROM {rel} WHERE id = ?", [addon_id], d)
            if not rows:
                points.append(AddonHistoryPoint(snapshot=d, present=False))
                continue
            row = rows[0]
            points.append(AddonHistoryPoint(
                snapshot=d, present=True, title=row["title"], rating=row["rating"], likes=row["likes"],
                dislikes=row["dislikes"], github_stars=row["github_stars"], update_date=row["update_date"] or None,
                anki_version=row["anki_version"] or None, anki_version_kind=row["anki_version_kind"],
            ))
        return points

    def get_aggregation(self, snapshot: date | None = None) -> Aggregation:
        row = self._select(
            "SELECT count(*) AS addon_number, count_if(has_github) AS addon_with_github_number, "
            "count_if(has_forum) AS addon_with_anki_forum_page_number, "
            "count_if(coalesce(github_tests_count, 0) > 0) AS addon_with_unit_tests_number FROM {rel}",
            [], snapshot)[0]
        return Aggregation.model_validate(row)

    def group_counts(self, field: GroupField, snapshot: date | None = None) -> dict[str, int]:
        if field in _SCALAR_GROUPS:
            expr = _SCALAR_GROUPS[field]
            sql = (f"SELECT coalesce(NULLIF({expr}, ''), '{NONE_GROUP}') AS k, count(*) AS n "
                   "FROM {rel} GROUP BY k")
        else:
            column = _LIST_GROUPS[field]
            sql = (f"SELECT k, count(*) AS n FROM (SELECT unnest(CASE WHEN len({column}) > 0 THEN {column} "
                   f"ELSE ['{NONE_GROUP}'] END) AS k FROM {{rel}}) GROUP BY k")
        return {row["k"]: int(row["n"]) for row in self._select(sql, [], snapshot)}

    def list_tags(self, snapshot: date | None = None) -> list[Tag]:
        state = self._current()
        table = state.tag_table(snapshot)
        cursor = state.cursor()
        try:
            cursor.execute(f'SELECT name, "group", description FROM {table} ORDER BY "group", name')
            return [Tag.model_validate(row) for row in _dicts(cursor)]
        finally:
            cursor.close()

    def get_documentation(self) -> str:
        return self._current().source.readme() or "Anki addons dataset (no dataset card available)."

    def sql_schema(self) -> str:
        return schema_description()

    def execute_readonly(self, sql: str, snapshot: date | None, max_rows: int, timeout_seconds: float) -> SqlResult:
        state = self._current()
        relation = state.relation(snapshot)
        tag_table = state.tag_table(snapshot)
        cursor = state.cursor()
        timer = threading.Timer(timeout_seconds, cursor.interrupt)
        try:
            validate_readonly_select(cursor, sql, {SQL_VIEW, TAGS_VIEW})
            helpers = ", ".join(HELPER_COLUMNS)
            cursor.execute(f"CREATE OR REPLACE TEMP VIEW {SQL_VIEW} AS SELECT * EXCLUDE ({helpers}) FROM {relation}")
            cursor.execute(f"CREATE OR REPLACE TEMP VIEW {TAGS_VIEW} AS SELECT * FROM {tag_table}")
            timer.start()
            try:
                cursor.execute(sql)
                rows = cursor.fetchmany(max_rows + 1)
            except duckdb.InterruptException as e:
                raise InvalidQuery(f"Query exceeded the {timeout_seconds}s time limit") from e
            except duckdb.Error as e:
                raise InvalidQuery(f"SQL error: {e}") from e
            columns = [d[0] for d in cursor.description or []]
            truncated = len(rows) > max_rows
            rows = rows[:max_rows]
            return SqlResult(columns=columns, rows=[[json_safe(v) for v in row] for row in rows],
                             row_count=len(rows), truncated=truncated)
        finally:
            timer.cancel()
            cursor.close()
