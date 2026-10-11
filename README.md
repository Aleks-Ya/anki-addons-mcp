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
catalog, enriched with GitHub, Anki Forum and AI-summary and AI-tag data, published as monthly snapshots.

It answers questions such as "which addon does X?", "will it work on Anki 25.02?", "is it maintained?",
and "what changed since last month?".

## Links
- [Anki Addons dataset](https://huggingface.co/datasets/Ya-Alex/anki-addons) on HuggingFace
- [anki-addons-dataset](https://github.com/Aleks-Ya/anki-addons-dataset), the pipeline that builds the dataset
- [Developer Guide](README-DEV.md): running from sources, debugging, tests, architecture, deployment

## Use it locally (STDIO)

Requires [uv](https://docs.astral.sh/uv/). `uvx` runs the [PyPI package](https://pypi.org/project/anki-addons-mcp/)
in an isolated, cached environment; to run a working copy instead, see
[Run from sources](README-DEV.md#run-from-sources).

Register the server in Claude Code:

```bash
claude mcp add anki-addons -- uvx anki-addons-mcp
```

Other MCP clients use the same command (`uvx anki-addons-mcp`) in their server configuration, e.g.:

```json
{
  "mcpServers": {
    "anki-addons": { "command": "uvx", "args": ["anki-addons-mcp"] }
  }
}
```

The first start downloads the latest snapshot (~15 MB) into the HuggingFace cache. Older snapshots are
downloaded on demand by history tools, so the first history question can take a minute.

## Use it remotely (Streamable HTTP)

Connect to the hosted instance on the [HuggingFace Space](https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp)
by URL:

```bash
claude mcp add --transport http anki-addons https://ya-alex-anki-addons-mcp.hf.space/mcp
```

The Space sleeps after inactivity, so the first request can take a while. To explore the server in a browser,
see [Debug with the MCP Inspector](README-DEV.md#debug-with-the-mcp-inspector).

To host your own instance, see [Run over HTTP](README-DEV.md#run-over-http) and
[Deploy to a HuggingFace Space](README-DEV.md#deploy-to-a-huggingface-space).

## Capabilities

**Tools** (all read-only, every data tool takes an optional `snapshot`, `YYYY-MM-DD` or `latest`):
`search_addons`, `filter_addons`, `get_addon`, `get_addon_readme`, `get_addon_description`,
`check_compatibility`, `assess_maintenance`, `find_similar_addons`, `list_addons_by_author`,
`get_addon_history`, `diff_snapshots`, `get_statistics`, `top_addons`, `list_snapshots`, `list_tags`, and
`query_sql` (one sandboxed DuckDB `SELECT` over the `addons` and `tags` tables; only offered by SQL-capable
backends). `search_addons` and `filter_addons` filter by AI tags with `tags` and `exclude_tags`.
Compatibility follows Anki's parsed versions (point versions and the `hard`/`tested`/`open`/`unknown` kind of the
upper version); `filter_addons` also filters by `anki_version_kind` and `anki_version_at_least` and sorts by
`anki_version`.

**Resources**: `anki-addons://dataset/readme`, `anki-addons://dataset/schema`,
`anki-addons://dataset/anki-versions`, `anki-addons://snapshots`,
`anki-addons://snapshots/{snapshot}/metadata`, `anki-addons://snapshots/{snapshot}/aggregation`,
`anki-addons://addons/{addon_id}` (and `/readme`, `/description`, `/history`),
`anki-addons://authors/{github_user}`, `anki-addons://tags`, `anki-addons://tags/{tag}`.

**Prompts**: `find_addon_for_task`, `compare_addons`, `addon_health_report`, `upgrade_readiness`,
`monthly_ecosystem_digest`, `before_you_build`, `author_portfolio`, `best_in_category`, `category_landscape`,
`anki_release_readiness`.

AI summaries and tags in the dataset are LLM-generated; the server labels them as such.

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
