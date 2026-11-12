# Configuration

The server reads environment variables with the prefix `ANKI_MCP_`, also from a `.env` file in the working
directory. CLI flags override environment variables; `uvx anki-addons-mcp --help` lists them.

| Variable | CLI flag | Default | Meaning |
|---|---|---|---|
| `ANKI_MCP_TRANSPORT` | `--transport` | `stdio` | `stdio` or `http` |
| `ANKI_MCP_HOST` / `ANKI_MCP_PORT` / `ANKI_MCP_PATH` | `--host` / `--port` / `--path` | `127.0.0.1` / `8000` / `/mcp` | HTTP binding |
| `ANKI_MCP_ALLOWED_HOSTS` | | `[]` | JSON list of Host headers to allow (enables DNS-rebinding protection) |
| `ANKI_MCP_BACKEND` | `--backend` | `hf_parquet` | `hf_parquet` (HuggingFace Hub) or `local_parquet` (a local copy) |
| `ANKI_MCP_HF_REPO_ID` / `ANKI_MCP_HF_REVISION` | `--hf-revision` | `Ya-Alex/anki-addons` / `v1.0-2026-11-01` | Dataset to serve; the revision is any git ref: a version tag, the `v1` or `main` branch, a commit SHA (see [Update the dataset version](maintaining.md#update-the-dataset-version)) |
| `ANKI_MCP_DATA_DIR` | `--data-dir` | | Dataset directory for `local_parquet` (`latest/`, `history/<date>/`) |
| `ANKI_MCP_CACHE_DIR` | `--cache-dir` | HF cache | Download cache |
| `ANKI_MCP_REFRESH_INTERVAL_SECONDS` | `--refresh-interval` | `3600` | Check for a new dataset revision; finds one only when the revision is a branch, the default tag never changes; `0` disables |
| `ANKI_MCP_SQL_ENABLED` / `_SQL_MAX_ROWS` / `_SQL_TIMEOUT_SECONDS` | `--no-sql` | `true` / `200` / `10` | `query_sql` limits |
| `ANKI_MCP_MAINTENANCE_ACTIVE_DAYS` / `_STALE_DAYS` | | `180` / `730` | Maintenance label thresholds |
| `ANKI_MCP_LOG_LEVEL` | `--log-level` | `INFO` | Logs go to stderr |
| `HF_TOKEN` | | | Optional HuggingFace token for higher download rate limits (a Space secret) |

## Serve a local copy of the dataset

The `local_parquet` backend reads the dataset from disk, offline and without downloads. The directory has the
published layout: `latest/` and `history/<date>/`, e.g. the bundle built by
[anki-addons-dataset](https://github.com/Aleks-Ya/anki-addons-dataset).

```bash
uvx anki-addons-mcp --backend local_parquet --data-dir /path/to/dataset
```

## Serve over HTTP

```bash
uvx anki-addons-mcp --transport http --port 8000
```

The endpoint is `http://localhost:8000/mcp`. See [Run over HTTP](development.md#run-over-http) for details.
