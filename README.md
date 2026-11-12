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

## Use it locally (STDIO)

Requires [uv](https://docs.astral.sh/uv/). `uvx` runs the [PyPI package](https://pypi.org/project/anki-addons-mcp/)
in an isolated, cached environment; to run a working copy instead, see
[Run from sources](docs/development.md#run-from-sources).

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

The first start downloads the latest snapshot of the pinned dataset version (~20 MB) into the HuggingFace
cache. Older snapshots are downloaded on demand by history tools, so the first history question can take a minute.

## Use it remotely (Streamable HTTP)

Connect to the hosted instance on the [HuggingFace Space](https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp)
by URL:

```bash
claude mcp add --transport http anki-addons https://ya-alex-anki-addons-mcp.hf.space/mcp
```

The Space sleeps after inactivity, so the first request can take a while. To host your own instance, see
[Configuration](docs/configuration.md#serve-over-http) and
[Deploy to a HuggingFace Space](docs/maintaining.md#deploy-to-a-huggingface-space).

## What it can do

- **Find addons**: full-text search and structured filters (rating, GitHub, language, Anki version, AI tags,
  forks, copies, ...), similar addons, addons of an author, leaderboards.
- **Inspect an addon**: the full record, GitHub README, AnkiWeb description, user reviews, and what its
  `.ankiaddon` packages really ship.
- **Check compatibility** of addons with an Anki version, and list the real Anki releases.
- **Assess maintenance**: activity signals and an active / stale / abandoned label.
- **Compare forks**: the original, its forks and forks of forks side by side, e.g. to find a maintained fork
  of an abandoned addon.
- **Track changes** of one addon or the whole catalog across monthly snapshots, and get statistics.
- **Run SQL**: one sandboxed DuckDB `SELECT` for questions the other tools cannot answer.
- **Prompts** for common workflows, e.g. `find_addon_for_task`, `upgrade_readiness`, `before_you_build`.

AI summaries and tags in the dataset are LLM-generated; the server labels them as such.

## Documentation

- [Reference](docs/reference.md): all tools, filters, resources and prompts
- [Dataset notes](docs/dataset-notes.md): AI-generated fields, gaps, data missing in older snapshots
- [Configuration](docs/configuration.md): environment variables, CLI flags, serving a local dataset copy
- [Developer guide](docs/development.md): running from sources, debugging, tests, architecture
- [Maintainer guide](docs/maintaining.md): deploying the Space, releasing, PyPI, CI

## Links

- [Anki Addons dataset](https://huggingface.co/datasets/Ya-Alex/anki-addons) on HuggingFace
- [anki-addons-dataset](https://github.com/Aleks-Ya/anki-addons-dataset), the pipeline that builds the dataset
- [PyPI package](https://pypi.org/project/anki-addons-mcp/)
- [HuggingFace Space](https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp)
