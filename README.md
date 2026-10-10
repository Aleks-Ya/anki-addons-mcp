---
title: Anki Addons MCP
emoji: 🗂️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: MCP server for the Anki Addons dataset
---

# Anki Addons MCP

An [MCP](https://modelcontextprotocol.io) server that gives LLM clients read-only access to the
[Anki Addons dataset](https://huggingface.co/datasets/Ya-Alex/anki-addons): every addon in the AnkiWeb
catalog, enriched with GitHub, Anki Forum and AI-summary data, published as monthly snapshots.

It answers questions such as "which addon does X?", "will it work on Anki 25.02?", "is it maintained?",
and "what changed since last month?".

## Run locally (STDIO)

```bash
uvx anki-addons-mcp                       # once published to PyPI
uv run anki-addons-mcp                    # from a checkout
```

Register in Claude Code:

```bash
claude mcp add anki-addons -- uv --directory /path/to/anki-addons-mcp run anki-addons-mcp
```

The first start downloads the latest snapshot (~15 MB) into the HuggingFace cache. Older snapshots are
downloaded on demand by history tools.

## Run remotely (Streamable HTTP)

```bash
uv run anki-addons-mcp --transport http --host 0.0.0.0 --port 7860
curl http://localhost:7860/healthz
claude mcp add --transport http anki-addons http://localhost:7860/mcp
```

The HTTP transport runs stateless with JSON responses, so it survives restarts and needs no session
affinity. On a HuggingFace Docker Space (this README carries the Space header) the endpoint is
`https://<user>-anki-addons-mcp.hf.space/mcp`.

```bash
docker build -t anki-addons-mcp .
docker run -p 7860:7860 anki-addons-mcp
```

## Capabilities

**Tools** (all read-only, every data tool takes an optional `snapshot`, `YYYY-MM-DD` or `latest`):
`search_addons`, `filter_addons`, `get_addon`, `get_addon_readme`, `get_addon_description`,
`check_compatibility`, `assess_maintenance`, `find_similar_addons`, `list_addons_by_author`,
`get_addon_history`, `diff_snapshots`, `get_statistics`, `top_addons`, `list_snapshots`, and
`query_sql` (one sandboxed DuckDB `SELECT` over an `addons` table; only offered by SQL-capable backends).

**Resources**: `anki-addons://dataset/readme`, `anki-addons://dataset/schema`, `anki-addons://snapshots`,
`anki-addons://snapshots/{snapshot}/metadata`, `anki-addons://snapshots/{snapshot}/aggregation`,
`anki-addons://addons/{addon_id}` (and `/readme`, `/description`, `/history`),
`anki-addons://authors/{github_user}`.

**Prompts**: `find_addon_for_task`, `compare_addons`, `addon_health_report`, `upgrade_readiness`,
`monthly_ecosystem_digest`, `before_you_build`, `author_portfolio`.

AI summaries in the dataset are LLM-generated; the server labels them as such.

## Configuration

CLI flags override environment variables (prefix `ANKI_MCP_`, also read from `.env`).

| Variable | Default | Meaning |
|---|---|---|
| `ANKI_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `ANKI_MCP_HOST` / `ANKI_MCP_PORT` / `ANKI_MCP_PATH` | `127.0.0.1` / `8000` / `/mcp` | HTTP binding |
| `ANKI_MCP_ALLOWED_HOSTS` | `[]` | JSON list of Host headers to allow (enables DNS-rebinding protection) |
| `ANKI_MCP_BACKEND` | `hf_parquet` | `hf_parquet` (HuggingFace Hub) or `local_parquet` (a local copy) |
| `ANKI_MCP_HF_REPO_ID` / `ANKI_MCP_HF_REVISION` | `Ya-Alex/anki-addons` / `main` | Dataset to serve |
| `ANKI_MCP_DATA_DIR` | | Dataset directory for `local_parquet` (`latest/`, `history/<date>/`) |
| `ANKI_MCP_CACHE_DIR` | HF cache | Download cache |
| `ANKI_MCP_REFRESH_INTERVAL_SECONDS` | `3600` | Check for a new dataset revision; `0` disables |
| `ANKI_MCP_SQL_ENABLED` / `_SQL_MAX_ROWS` / `_SQL_TIMEOUT_SECONDS` | `true` / `200` / `10` | `query_sql` limits |
| `ANKI_MCP_MAINTENANCE_ACTIVE_DAYS` / `_STALE_DAYS` | `180` / `730` | Maintenance label thresholds |
| `ANKI_MCP_LOG_LEVEL` | `INFO` | Logs go to stderr |
| `HF_TOKEN` | | Optional HuggingFace token for higher download rate limits (a Space secret) |

## Architecture

Ports and adapters, so the storage can be replaced without touching the MCP layer:

```
interface/mcp   MCPServer tools, resources, prompts   (knows MCP, not storage)
application     catalog, compatibility, maintenance, history, similarity, stats services
domain          pydantic models, AddonQuery, AddonRepository port, optional SqlQueryable/Refreshable
adapters        hf_parquet (DuckDB over the published Parquet files), memory (tests)
bootstrap       settings -> repository -> services -> server -> transport
```

A new storage backend implements `AddonRepository` and passes `tests/contract`, which runs the same suite
against every adapter and checks that the adapters return identical records.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy
npx @modelcontextprotocol/inspector uv run anki-addons-mcp
```
