# Reference

Tools, resources and prompts of the server. Every tool is read-only, and every data tool takes an optional
`snapshot` (`YYYY-MM-DD` from `list_snapshots`, default `latest`). Clients receive the full parameter
descriptions from the server itself; to browse them, see
[Debug with the MCP Inspector](development.md#debug-with-the-mcp-inspector). For gaps and caveats of the data,
see [Dataset notes](dataset-notes.md).

## Tools

### Find addons

| Tool | Use it to |
|---|---|
| `search_addons` | Full-text search over titles, descriptions, AI summaries and tags, GitHub topics; accepts every filter of `filter_addons` |
| `filter_addons` | Structured query with [filters](#filters), sorted by rating (approval), likes, stars, update date, last commit, forum posts or `anki_version` |
| `find_similar_addons` | Find addons similar to a given one: shared wording, topics, AI tags, author or fork relation |
| `list_addons_by_author` | List the addons of a GitHub user, or of an AnkiWeb author by `author_id` or by any of their addons (`addon_id`) |
| `top_addons` | Leaderboard by rating, likes, stars, forum posts or recency, optionally within one AI tag |

### Inspect one addon

| Tool | Use it to |
|---|---|
| `get_addon` | Get the full record: AnkiWeb, GitHub (with activity), forum topic, newest package, AI summary and tags, fork relations; long texts and the release list with `include` |
| `get_addon_readme` | Read the GitHub README as markdown |
| `get_addon_description` | Read the AnkiWeb description as plain text, or the author's HTML with `format=html` |
| `get_addon_reviews` | Read AnkiWeb reviews newest first, filtered by `vote`, `contains` text and `since` date, e.g. reports of breakage on a new Anki |
| `get_addon_packages` | See what the `.ankiaddon` packages ship, one per branch: sizes, file and Python line counts, languages, download URL; raw `manifest.json`, `config.json` and the file list with `include` |

### Assess

| Tool | Use it to |
|---|---|
| `check_compatibility` | Check whether up to 100 addons support an Anki version: `supported`, `likely`, `unsupported` or `unknown`, separately for AnkiWeb and the GitHub manifest |
| `assess_maintenance` | Get maintenance signals (commits, issues, response time, tests, CI, forum) and a label `active`, `stale`, `abandoned` or `unknown` |
| `compare_forks` | Compare the whole fork family of an addon side by side, without picking a winner |

### History and statistics

| Tool | Use it to |
|---|---|
| `get_addon_history` | Follow one addon's rating, likes, stars, update date and Anki version across snapshots |
| `diff_snapshots` | See added, removed and updated addons and the biggest rating and star changes between two snapshots |
| `get_statistics` | Count addons, optionally grouped by license, repo or package language, description language, AI tag, Anki version or its kind, update year, GitHub topic, AI markers |

### Lookups

| Tool | Use it to |
|---|---|
| `list_snapshots` | List the available monthly snapshots |
| `list_tags` | List the AI tag vocabulary with descriptions and addon counts |
| `list_anki_versions` | List the stable Anki releases of a snapshot, newest first, with release dates |

### SQL

| Tool | Use it to |
|---|---|
| `query_sql` | Run one sandboxed DuckDB `SELECT` over the tables `addons`, `tags`, `anki_versions`, `reviews` and `packages`, for questions the other tools cannot answer |

`query_sql` is offered only by SQL-capable backends and can be turned off with `--no-sql`; results are capped
(200 rows and 10 s by default, see [Configuration](configuration.md)). The tool description carries the table
schemas.

### Filters

`search_addons` and `filter_addons` share these filters, combined with AND:

| Filter | Matches addons |
|---|---|
| `min_rating`, `min_likes`, `min_stars` | with at least this many AnkiWeb votes, likes or GitHub stars |
| `has_github`, `has_tests`, `has_forum` | with a GitHub repo, tests or an Anki Forum topic |
| `language` | whose GitHub repo language or a language detected in the package matches, case-insensitive, e.g. `Python` |
| `description_language` | whose description is in this language (ISO code) |
| `compatible_with_anki` | that support this Anki version |
| `anki_version_kind`, `anki_version_at_least` | by the newest supported Anki version: its [kind](#anki-versions) or a minimum |
| `updated_after`, `updated_before`, `archived` | by AnkiWeb update date or GitHub archived flag |
| `author_id` | of one AnkiWeb author |
| `is_fork`, `has_forks`, `fork_of` | by [fork relations](#forks) |
| `has_ai_declaration`, `has_ai_tooling` | whose description mentions AI use, or whose repo has AI coding tool traces |
| `tags`, `exclude_tags` | with all / none of these AI tags (`list_tags`) |

Sorting by rating (and `metric=rating` in `top_addons`) ranks by approval: the Wilson lower bound of likes vs.
dislikes, so disliked addons rank lower.

### Anki versions

Compatibility follows the parsed AnkiWeb branches: each has a minimum and a maximum point version, and the
maximum has a kind:
- `hard`: Anki disables the addon on newer versions
- `tested`: tested up to this version, newer Anki still runs it
- `open`: no upper limit
- `unknown`: no version data

The resource `anki-addons://dataset/anki-versions` explains the encoding and how verdicts are derived.

### Forks

`get_addon` shows `forked_from` (the one addon it was forked from, or null) with its evidence (`github_fork`,
`ai` or `override`), `forks` (any number) and `github.fork_source`; addon cards carry the ids.
`find_similar_addons` and `assess_maintenance` point to forks, e.g. a maintained fork of an abandoned addon.
`compare_forks` returns the family of an addon (the original, its forks and forks of forks; the same family from
any member) with each version's place in it, compatibility, maintenance label, votes, stars and status flags.

## Resources

| URI | Content |
|---|---|
| `anki-addons://dataset/readme` | Dataset card: overview, tables, links to the field docs, license |
| `anki-addons://dataset/schema` | JSON Schema of the full addon record returned by `get_addon` |
| `anki-addons://dataset/anki-versions` | How Anki versions are encoded and how compatibility verdicts are derived |
| `anki-addons://snapshots` | Available snapshots with metadata |
| `anki-addons://snapshots/{snapshot}/metadata` | Metadata of one snapshot |
| `anki-addons://snapshots/{snapshot}/aggregation` | Addon counts of one snapshot |
| `anki-addons://addons/{addon_id}` | Full record of an addon |
| `anki-addons://addons/{addon_id}/readme` | GitHub README |
| `anki-addons://addons/{addon_id}/description` | AnkiWeb description as plain text |
| `anki-addons://addons/{addon_id}/description.html` | AnkiWeb description as the author's HTML (not sanitized) |
| `anki-addons://addons/{addon_id}/reviews` | The 50 newest AnkiWeb reviews |
| `anki-addons://addons/{addon_id}/packages` | Sizes, counts and download URLs of the `.ankiaddon` packages |
| `anki-addons://addons/{addon_id}/history` | Rating, likes and stars across snapshots |
| `anki-addons://authors/{github_user}` | Addons of a GitHub user |
| `anki-addons://tags` | AI tag vocabulary with descriptions and addon counts |
| `anki-addons://tags/{tag}` | Addons with an AI tag |
| `anki-addons://anki-versions` | Stable Anki releases from 2.1.0 on, newest first |

Resources without `{snapshot}` read the latest snapshot.

## Prompts

| Prompt | Arguments | Use it to |
|---|---|---|
| `find_addon_for_task` | `task`, `anki_version` | Get addon recommendations for a task, checked for compatibility and maintenance |
| `compare_addons` | `addon_ids` | Compare addons side by side |
| `addon_health_report` | `addon_id` | Get a health report of one addon |
| `upgrade_readiness` | `addon_ids`, `target_anki_version` | Find which installed addons keep working after an Anki upgrade |
| `monthly_ecosystem_digest` | `from_snapshot`, `to_snapshot` | Get a narrative digest of what changed between snapshots |
| `before_you_build` | `idea` | As an addon developer, see what already exists for an idea |
| `author_portfolio` | `github_user` | Summarize a GitHub author's addons |
| `best_in_category` | `tag`, `anki_version` | Find the best addons in one category (AI tag) |
| `category_landscape` | | Map the addon ecosystem by category (AI tags) |
| `anki_release_readiness` | `anki_version` | See how ready the addon ecosystem is for an Anki release |
