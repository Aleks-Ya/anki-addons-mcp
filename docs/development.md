# Developer guide

Running, debugging and testing the server from sources. Deploying and releasing are in the
[Maintainer guide](maintaining.md).

## Set up
The project is managed by [uv](https://docs.astral.sh/uv/) and needs Python 3.13+.

```bash
uv sync
```

`uv sync` creates `.venv/` and installs the project in editable mode with the `dev` dependency group,
resolved from the committed `uv.lock`. Prefix commands with `uv run` to use that environment.

## Run from sources

```bash
uv run anki-addons-mcp                     # STDIO
uv run anki-addons-mcp --help              # all flags
```

Register the working copy in Claude Code:

```bash
claude mcp add anki-addons -- uv --directory /path/to/anki-addons-mcp run anki-addons-mcp
```

Settings are described in [Configuration](configuration.md). Useful for development:
- `--backend local_parquet --data-dir /path/to/dataset` serves a local copy of the dataset
  (`latest/` and `history/<date>/`, e.g. the bundle built by anki-addons-dataset), offline and without downloads.
- `--refresh-interval 0` turns off the hourly check for a new dataset revision.
- `--log-level DEBUG` also shows HTTP requests to the HuggingFace Hub. Logs always go to stderr, because
  stdout is the STDIO protocol channel.

## Run over HTTP

```bash
uv run anki-addons-mcp --transport http --port 8000
curl http://localhost:8000/healthz
claude mcp add --transport http anki-addons http://localhost:8000/mcp
```

The HTTP transport runs stateless with JSON responses, so it survives restarts and needs no session
affinity. Binding to `127.0.0.1` enables DNS-rebinding protection for localhost; on other hosts set
`ANKI_MCP_ALLOWED_HOSTS` to enable it.

## Run in Docker

```bash
docker build -t anki-addons-mcp .
docker run -p 7860:7860 anki-addons-mcp
curl http://localhost:7860/healthz
```

The image serves HTTP on port 7860 at `/mcp` and has the DuckDB `fts` extension preinstalled.

## Debug with the MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) needs Node.js (`npx`).

**STDIO.** The Inspector launches the server itself:

```bash
npx @modelcontextprotocol/inspector uv run anki-addons-mcp
npx @modelcontextprotocol/inspector uv --directory /path/to/anki-addons-mcp run anki-addons-mcp
```

Use the first command from the project directory and the second from anywhere else. The UI opens at
`http://localhost:6274` with the transport set to STDIO. Click **Connect**, then use the **Tools**,
**Resources** and **Prompts** tabs. Server logs (stderr) appear in the Inspector's server output pane.

**Streamable HTTP.** Start the server, then connect the Inspector to it:

```bash
uv run anki-addons-mcp --transport http --port 8000
npx @modelcontextprotocol/inspector
```

In the UI, set **Transport Type** to *Streamable HTTP* and **URL** to `http://localhost:8000/mcp`, then
click **Connect**. For the Docker image, use `http://localhost:7860/mcp`.

**Deployed Space.** Open the Inspector UI already connected to the Space:

```bash
npx @modelcontextprotocol/inspector --transport http --server-url https://ya-alex-anki-addons-mcp.hf.space/mcp
```

The UI opens at `http://localhost:6274` with **Transport Type** set to *Streamable HTTP* and **URL** set to
`https://ya-alex-anki-addons-mcp.hf.space/mcp`; click **Connect**. The CLI mode runs a single request and
prints the JSON:

```bash
npx @modelcontextprotocol/inspector --cli https://ya-alex-anki-addons-mcp.hf.space/mcp --transport http --method tools/list
npx @modelcontextprotocol/inspector --cli https://ya-alex-anki-addons-mcp.hf.space/mcp --transport http \
  --method tools/call --tool-name search_addons --tool-arg query="image occlusion" --tool-arg limit=3
```

The Space sleeps after inactivity, so the first request can be slow while it wakes up. Server logs are in the
**Logs** tab of the [Space page](https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp), not in the Inspector.

**Tips**
- **Timeouts:** the first start downloads the latest snapshot (~20 MB). The first `get_addon_history` or
  `diff_snapshots` call that needs older snapshots can take a minute or more. If a call times out, raise
  **Request Timeout** in the Inspector's **Configuration** panel (e.g. `300000` ms). Later runs read the
  files from the HF cache.
- **Offline or faster startup:** serve a local copy of the dataset (`latest/` and `history/<date>/`):
  `npx @modelcontextprotocol/inspector uv run anki-addons-mcp --backend local_parquet --data-dir /path/to/dataset`
- **Less noise:** add `--refresh-interval 0` to turn off the hourly check for a new dataset revision.

## Test and lint

```bash
uv run pytest
uv run ruff check src tests
uv run mypy
```

Tests build a small fixture dataset in the published layout (two snapshots, including the type drift of
older snapshots) and need no network access.

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
