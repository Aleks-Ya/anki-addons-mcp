from datetime import date
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from anki_addons_mcp.application.catalog import AddonText, TopMetric
from anki_addons_mcp.application.compatibility import CompatibilityVerdict
from anki_addons_mcp.application.history import AddonHistory, SnapshotDiff
from anki_addons_mcp.application.maintenance import MaintenanceReport
from anki_addons_mcp.application.services import Services
from anki_addons_mcp.application.similarity import SimilarAddon
from anki_addons_mcp.application.snapshots import parse_snapshot
from anki_addons_mcp.application.stats import Statistics
from anki_addons_mcp.application.tags import TagUsage
from anki_addons_mcp.domain.models import (
    AddonCard,
    AddonDetails,
    GroupField,
    Page,
    SnapshotInfo,
    SqlResult,
    TextKind,
    VersionKind,
)
from anki_addons_mcp.domain.query import AddonFilters, SortField
from anki_addons_mcp.interface.mcp.errors import tool_errors

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

Snapshot = Annotated[str, Field(description="Snapshot date YYYY-MM-DD from list_snapshots, or 'latest'")]
AddonId = Annotated[int, Field(description="AnkiWeb addon id, e.g. 1374772155")]
Limit = Annotated[int, Field(ge=1, le=100, description="Maximum number of results")]
Offset = Annotated[int, Field(ge=0, description="Number of results to skip, for paging")]
AnkiVersion = Annotated[str | None, Field(description="Anki version such as 25.02, 25.09.2, 2.1.66 or 26.05b1")]
MaxChars = Annotated[int, Field(ge=100, le=200_000, description="Truncate the text to this many characters")]
AddonInclude = Literal["description", "readme", "links"]
Tags = Annotated[list[str] | None, Field(
    description="AI tags the addon must all have, e.g. ['statistics'] or ['cloze', 'mobile-compatible']; "
                "see list_tags for the vocabulary")]
ExcludeTags = Annotated[list[str] | None, Field(
    description="AI tags the addon must not have, e.g. ['obsolete', 'no-description', 'paid']")]


def register_tools(mcp: MCPServer, services: Services) -> None:
    catalog = services.catalog

    @mcp.tool(annotations=READ_ONLY, description=(
        "Full-text search over addon titles, AnkiWeb descriptions, AI summaries and tags, GitHub topics and "
        "repo descriptions. Returns compact addon cards ranked by relevance."))
    def search_addons(query: Annotated[str, Field(description="Search words, e.g. 'image occlusion'")],
                      limit: Limit = 20, offset: Offset = 0,
                      compatible_with_anki: AnkiVersion = None,
                      tags: Tags = None, exclude_tags: ExcludeTags = None,
                      snapshot: Snapshot = "latest") -> Page[AddonCard]:
        with tool_errors():
            filters = AddonFilters(compatible_with_anki=compatible_with_anki, tags=tags, exclude_tags=exclude_tags)
            return catalog.search(query, limit, offset, filters, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Structured addon query. All filters are optional and combined with AND. "
        "Returns addon cards and the total number of matches. sort_by=anki_version orders by the newest "
        "supported Anki version."))
    def filter_addons(  # NOSONAR - each filter is a flat tool parameter in the MCP input schema
        min_rating: int | None = None, min_likes: int | None = None, min_stars: int | None = None,
        has_github: bool | None = None, has_tests: bool | None = None, has_forum: bool | None = None,
        license: Annotated[str | None, Field(description="SPDX id, e.g. MIT, GPL-3.0, AGPL-3.0")] = None,
        language: Annotated[str | None, Field(description="GitHub language, e.g. Python, JavaScript")] = None,
        description_language: Annotated[str | None, Field(description="ISO code of the description")] = None,
        topic: Annotated[str | None, Field(description="GitHub topic")] = None,
        compatible_with_anki: AnkiVersion = None,
        anki_version_kind: Annotated[VersionKind | None, Field(
            description="Meaning of the addon's newest supported Anki version: hard (Anki disables it on newer "
                        "versions), tested (tested up to it, newer still run it), open (no limit), unknown")] = None,
        anki_version_at_least: Annotated[str | None, Field(
            description="The addon's newest supported or tested Anki version is at least this, e.g. 25.09")] = None,
        updated_after: date | None = None, updated_before: date | None = None,
        archived: bool | None = None,
        has_ai_declaration: Annotated[bool | None, Field(
            description="Description mentions AI use (e.g. 'vibe-coded', 'claude')")] = None,
        has_ai_tooling: Annotated[bool | None, Field(
            description="Repository has AI coding tool traces (e.g. AGENTS.md, .cursor)")] = None,
        tags: Tags = None, exclude_tags: ExcludeTags = None,
        sort_by: SortField = SortField.RATING, descending: bool = True,
        limit: Limit = 20, offset: Offset = 0, snapshot: Snapshot = "latest",
    ) -> Page[AddonCard]:
        with tool_errors():
            filters = AddonFilters(
                min_rating=min_rating, min_likes=min_likes, min_stars=min_stars, has_github=has_github,
                has_tests=has_tests, has_forum=has_forum, license=license, language=language,
                description_language=description_language, topic=topic, compatible_with_anki=compatible_with_anki,
                anki_version_kind=anki_version_kind, anki_version_at_least=anki_version_at_least,
                updated_after=updated_after, updated_before=updated_before, archived=archived,
                has_ai_declaration=has_ai_declaration, has_ai_tooling=has_ai_tooling, tags=tags,
                exclude_tags=exclude_tags,
            )
            return catalog.filter(filters, sort_by, descending, limit, offset, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Full record of one addon: AnkiWeb info and version branches, GitHub repository data and manifest, "
        "Anki Forum topic and AI summary and tags. Long texts and link lists are omitted unless requested in 'include'."))
    def get_addon(addon_id: AddonId, include: list[AddonInclude] | None = None,
                  max_chars: MaxChars = 4000, snapshot: Snapshot = "latest") -> AddonDetails:
        parts = set(include or [])
        with tool_errors():
            return catalog.get(addon_id, parse_snapshot(snapshot), "description" in parts, "readme" in parts,
                               max_chars, "links" in parts)

    @mcp.tool(annotations=READ_ONLY, description="GitHub README of an addon as markdown text.")
    def get_addon_readme(addon_id: AddonId, max_chars: MaxChars = 20000, snapshot: Snapshot = "latest") -> AddonText:
        with tool_errors():
            return catalog.text(addon_id, TextKind.README, max_chars, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description="AnkiWeb description of an addon as plain text.")
    def get_addon_description(addon_id: AddonId, max_chars: MaxChars = 20000,
                              snapshot: Snapshot = "latest") -> AddonText:
        with tool_errors():
            return catalog.text(addon_id, TextKind.DESCRIPTION, max_chars, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Check whether addons support an Anki version, based on the parsed AnkiWeb branches (min and max "
        "point versions and the max version kind), with a separate verdict from the GitHub manifest. "
        "Verdicts: supported (a branch covers the version), likely (tested on an older version, newer Anki "
        "still runs it), unsupported (below the minimum, or above a hard limit: Anki disables the addon), "
        "unknown (no upper version given or no version data). See anki-addons://dataset/anki-versions."))
    def check_compatibility(addon_ids: Annotated[list[int], Field(min_length=1, max_length=100)],
                            anki_version: Annotated[str, Field(description="e.g. 25.02 or 2.1.66")],
                            snapshot: Snapshot = "latest") -> list[CompatibilityVerdict]:
        with tool_errors():
            return services.compatibility.check(addon_ids, anki_version, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Maintenance health of an addon: last update/commit, archived flag, open issues, tests, CI and forum "
        "activity, plus a coarse label (active, stale, abandoned, unknown) with reasons."))
    def assess_maintenance(addon_id: AddonId, snapshot: Snapshot = "latest") -> MaintenanceReport:
        with tool_errors():
            return services.maintenance.assess(addon_id, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Addons similar to a given one: overlapping wording in title, summary and topics, shared GitHub "
        "topics, shared AI function tags, or the same author."))
    def find_similar_addons(addon_id: AddonId, limit: Limit = 10, snapshot: Snapshot = "latest") -> list[SimilarAddon]:
        with tool_errors():
            return services.similarity.similar(addon_id, limit, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description="All addons whose GitHub repository belongs to a GitHub user.")
    def list_addons_by_author(github_user: str, snapshot: Snapshot = "latest") -> Page[AddonCard]:
        with tool_errors():
            return catalog.by_author(github_user, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "One addon across monthly snapshots: rating, likes, GitHub stars, update date and Anki version, "
        "and whether it was listed. Loading old snapshots for the first time can take a while."))
    def get_addon_history(addon_id: AddonId, from_date: date | None = None,
                          to_date: date | None = None) -> AddonHistory:
        with tool_errors():
            return services.history.history(addon_id, from_date, to_date)

    @mcp.tool(annotations=READ_ONLY, description=(
        "What changed between two snapshots: added and removed addons, updated addons, and the biggest "
        "rating and GitHub star changes. Defaults compare the latest snapshot with the one before it."))
    def diff_snapshots(from_snapshot: Annotated[str | None, Field(
                           description="Earlier snapshot date; default is the one before 'to_snapshot'")] = None,
                       to_snapshot: Snapshot = "latest", limit: Limit = 20) -> SnapshotDiff:
        with tool_errors():
            to = parse_snapshot(to_snapshot)
            from_ = parse_snapshot(from_snapshot) if from_snapshot else None
            return services.history.diff(from_, to, limit)

    @mcp.tool(annotations=READ_ONLY, description=(
        "Dataset statistics: addon counts (total, with GitHub, with forum topic, with tests) and optional "
        "group-by counts, e.g. by license, primary language, AI tag (ai_tag) or Anki version kind "
        "(anki_version_kind)."))
    def get_statistics(group_by: list[GroupField] | None = None,
                       top_values: Annotated[int, Field(ge=1, le=200)] = 20,
                       snapshot: Snapshot = "latest") -> Statistics:
        with tool_errors():
            return services.stats.statistics(parse_snapshot(snapshot), group_by, top_values)

    @mcp.tool(annotations=READ_ONLY, description=(
        "Leaderboard of addons by rating, likes, stars, forum posts or recency, optionally within one AI tag."))
    def top_addons(metric: TopMetric = TopMetric.RATING, limit: Limit = 10,
                   tag: Annotated[str | None, Field(description="Only addons with this AI tag, e.g. 'fsrs'")] = None,
                   snapshot: Snapshot = "latest") -> Page[AddonCard]:
        with tool_errors():
            return catalog.top(metric, limit, parse_snapshot(snapshot), tag)

    @mcp.tool(annotations=READ_ONLY, description=(
        "Vocabulary of AI tags that classify addons: 'function' tags say what an addon does (e.g. statistics, "
        "cloze, fsrs), 'status' tags flag its state (e.g. obsolete, paid, beta). Each tag has a description "
        "and the number of addons that carry it. Use the names in the tags/exclude_tags filters."))
    def list_tags(snapshot: Snapshot = "latest") -> list[TagUsage]:
        with tool_errors():
            return services.tags.vocabulary(parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description="Available dataset snapshots (monthly) with their metadata.")
    def list_snapshots() -> list[SnapshotInfo]:
        with tool_errors():
            return services.snapshots.list()

    sql = services.sql
    if sql is None:
        return
    limits = services.sql_limits

    @mcp.tool(annotations=READ_ONLY, description=(
        "Run one read-only DuckDB SELECT for questions the other tools cannot answer. "
        f"Results are capped at {limits.max_rows} rows and {limits.timeout_seconds:g}s.\n\n" + sql.sql_schema()))
    def query_sql(sql_query: Annotated[str, Field(description="A single SELECT over the `addons` table")],
                  snapshot: Snapshot = "latest") -> SqlResult:
        with tool_errors():
            return sql.execute_readonly(sql_query, parse_snapshot(snapshot), limits.max_rows, limits.timeout_seconds)
