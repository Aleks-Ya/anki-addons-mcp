from datetime import date

import pytest

from anki_addons_mcp.adapters.hf_parquet.repository import DuckDbAddonRepository
from anki_addons_mcp.domain.errors import InvalidQuery
from anki_addons_mcp.domain.ports import SqlQueryable
from tests.fixtures.dataset import KANJI, LEGACY, OLD


def test_is_sql_queryable(duckdb_repository: DuckDbAddonRepository) -> None:
    assert isinstance(duckdb_repository, SqlQueryable)
    assert "github_stars" in duckdb_repository.sql_schema()


def test_select(duckdb_repository: DuckDbAddonRepository) -> None:
    result = duckdb_repository.execute_readonly(
        "WITH t AS (SELECT * FROM addons WHERE has_github) SELECT github_license, count(*) AS n FROM t "
        "GROUP BY 1 ORDER BY n DESC, 1 LIMIT 1", None, 10, 5)
    assert result.columns == ["github_license", "n"]
    assert result.rows == [["MIT", 4]]
    assert not result.truncated


def test_snapshot_and_complex_values(duckdb_repository: DuckDbAddonRepository) -> None:
    result = duckdb_repository.execute_readonly("SELECT count(*), max(branches) FROM addons", OLD, 10, 5)
    assert result.rows[0][0] == 8
    assert isinstance(result.rows[0][1], list)


def test_tags_table(duckdb_repository: DuckDbAddonRepository) -> None:
    assert "Table `tags`" in duckdb_repository.sql_schema()
    result = duckdb_repository.execute_readonly(
        'SELECT t."group", count(*) AS n FROM (SELECT unnest(ai_tags) AS tag FROM addons) a '
        'JOIN tags t ON t.name = a.tag GROUP BY 1 ORDER BY 1', None, 10, 5)
    assert result.rows == [["function", 11], ["status", 3]]
    helpers = duckdb_repository.execute_readonly("SELECT * FROM addons LIMIT 1", OLD, 10, 5)
    assert "tags_text" not in helpers.columns
    assert "ai_tags" in helpers.columns



def test_anki_versions_table(duckdb_repository: DuckDbAddonRepository) -> None:
    assert "Table `anki_versions`" in duckdb_repository.sql_schema()
    latest = duckdb_repository.execute_readonly(
        "SELECT version, point_version FROM anki_versions ORDER BY point_version DESC LIMIT 2", None, 10, 5)
    assert latest.rows == [["26.09.3", 260903], ["26.09", 260900]]
    joined = duckdb_repository.execute_readonly(
        "SELECT v.version, count(*) FROM addons a JOIN anki_versions v ON v.point_version = a.anki_point_version "
        "GROUP BY 1 ORDER BY 1", None, 10, 5)
    assert joined.rows
    old = duckdb_repository.execute_readonly("SELECT count(*) FROM anki_versions", OLD, 10, 5)
    assert old.rows == [[0]]


@pytest.mark.parametrize(("snapshot", "expected"), [(None, [6, 8, 1]), (OLD, [0, 8, 2])])
def test_dataset_2_4_columns(duckdb_repository: DuckDbAddonRepository, snapshot: date | None,
                             expected: list[int]) -> None:
    result = duckdb_repository.execute_readonly(
        "SELECT count(DISTINCT author_id), count(description_html), count_if(description_pre_wrap) FROM addons",
        snapshot, 10, 5)
    assert result.rows == [expected]


@pytest.mark.parametrize(("snapshot", "expected"), [(None, [2, 2, 1]), (OLD, [1, 1, 0])])
def test_dataset_2_5_columns(duckdb_repository: DuckDbAddonRepository, snapshot: date | None,
                             expected: list[int]) -> None:
    result = duckdb_repository.execute_readonly(
        "SELECT count(forked_from), count_if(len(forks) > 0), count(github_fork_source) FROM addons",
        snapshot, 10, 5)
    assert result.rows == [expected]


def test_fork_evidence_column(duckdb_repository: DuckDbAddonRepository) -> None:
    result = duckdb_repository.execute_readonly(
        "SELECT forked_from.id, forked_from.evidence FROM addons WHERE forked_from IS NOT NULL ORDER BY 1", None, 10, 5)
    assert result.rows == [[KANJI, "github_fork"], [LEGACY, "ai"]]


def test_row_cap(duckdb_repository: DuckDbAddonRepository) -> None:
    result = duckdb_repository.execute_readonly("SELECT id FROM addons", None, 3, 5)
    assert result.row_count == 3
    assert result.truncated


def test_timeout(duckdb_repository: DuckDbAddonRepository) -> None:
    with pytest.raises(InvalidQuery, match="time limit"):
        duckdb_repository.execute_readonly(
            "SELECT count(*) FROM addons a, addons b, addons c, addons d, addons e, addons f, addons g, addons h, "
            "addons i, addons j WHERE hash(a.id, b.id, c.id, d.id, e.id, f.id, g.id, h.id, i.id, j.id) = 0",
            None, 3, 0.2)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM '/etc/passwd'",
    "FROM 'data.parquet'",
    "SELECT * FROM snap_20261001",
    "SELECT * FROM main.addons",
    "SELECT * FROM duckdb_settings()",
    "SELECT getenv('HOME')",
    "SELECT 1; SELECT 2",
    "COPY (SELECT 1) TO '/tmp/x.csv'",
    "ATTACH '/tmp/x.db'",
    "INSTALL httpfs",
    "PRAGMA version",
    "SET threads = 1",
    "CREATE TABLE x AS SELECT 1",
    "DROP VIEW addons",
    "SELECT * FROM addons WHERE id IN (SELECT id FROM glob('*'))",
    "not sql at all",
])
def test_rejected(duckdb_repository: DuckDbAddonRepository, sql: str) -> None:
    with pytest.raises(InvalidQuery):
        duckdb_repository.execute_readonly(sql, None, 10, 5)
