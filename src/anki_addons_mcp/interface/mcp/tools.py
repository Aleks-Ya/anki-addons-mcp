from datetime import date
from typing import Annotated, Any, Literal

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
    AnkiRelease,
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
Language = Annotated[str | None, Field(description="GitHub language, e.g. Python, JavaScript")]
DescriptionLanguage = Annotated[str | None, Field(description="ISO code of the description")]
AnkiVersionKind = Annotated[VersionKind | None, Field(
    description="Meaning of the addon's newest supported Anki version: hard (Anki disables it on newer "
                "versions), tested (tested up to it, newer still run it), open (no limit), unknown")]
AnkiVersionAtLeast = Annotated[str | None, Field(
    description="The addon's newest supported or tested Anki version is at least this, e.g. 25.09")]
HasAiDeclaration = Annotated[bool | None, Field(
    description="Description mentions AI use (e.g. 'vibe-coded', 'claude')")]
HasAiTooling = Annotated[bool | None, Field(
    description="Repository has AI coding tool traces (e.g. AGENTS.md, .cursor)")]
AuthorId = Annotated[int | None, Field(
    description="Derived AnkiWeb author id (author_id of an addon card); null in snapshots collected before "
                "authors were tracked")]
IsFork = Annotated[bool | None, Field(
    description="Addon was forked from another catalog addon (detection is incomplete; 'ai' evidence may be wrong)")]
HasForks = Annotated[bool | None, Field(description="Other catalog addons were forked from this addon")]
ForkOf = Annotated[int | None, Field(
    description="Only forks of this addon id, e.g. to find a maintained fork of an abandoned addon")]
DescriptionFormat = Literal["text", "html"]
_DESCRIPTION_KINDS = {"text": TextKind.DESCRIPTION, "html": TextKind.DESCRIPTION_HTML}


def _filters(arguments: dict[str, Any]) -> AddonFilters:
    """Filters from a tool's arguments: every parameter named like an AddonFilters field."""
    return AddonFilters(**{name: value for name, value in arguments.items() if name in AddonFilters.model_fields})


def register_tools(mcp: MCPServer, services: Services) -> None:
    catalog = services.catalog

    @mcp.tool(annotations=READ_ONLY, description=(
        "Full-text search over addon titles, AnkiWeb descriptions, AI summaries and tags, GitHub topics and "
        "repo descriptions. Returns compact addon cards ranked by relevance. Accepts every filter of "
        "filter_addons; filters are combined with the query with AND."))
    def search_addons(
        query: Annotated[str, Field(description="Search words, e.g. 'image occlusion'")],  # NOSONAR - flat MCP tool parameters
        min_rating: int | None = None, min_likes: int | None = None, min_stars: int | None = None,
        has_github: bool | None = None, has_tests: bool | None = None, has_forum: bool | None = None,
        language: Language = None, description_language: DescriptionLanguage = None,
        compatible_with_anki: AnkiVersion = None,
        anki_version_kind: AnkiVersionKind = None, anki_version_at_least: AnkiVersionAtLeast = None,
        updated_after: date | None = None, updated_before: date | None = None,
        archived: bool | None = None, author_id: AuthorId = None,
        is_fork: IsFork = None, has_forks: HasForks = None, fork_of: ForkOf = None,
        has_ai_declaration: HasAiDeclaration = None, has_ai_tooling: HasAiTooling = None,
        tags: Tags = None, exclude_tags: ExcludeTags = None,
        limit: Limit = 20, offset: Offset = 0, snapshot: Snapshot = "latest",
    ) -> Page[AddonCard]:
        with tool_errors():
            filters = _filters(locals())
            return catalog.search(query, limit, offset, filters, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Structured addon query. All filters are optional and combined with AND. "
        "Returns addon cards and the total number of matches. sort_by=rating (default) ranks by approval: "
        "the Wilson lower bound of likes vs. dislikes, so disliked addons rank lower. min_rating is a minimum "
        "number of AnkiWeb votes (likes + dislikes). sort_by=anki_version orders by the newest supported Anki version."))
    def filter_addons(
        min_rating: int | None = None, min_likes: int | None = None, min_stars: int | None = None,  # NOSONAR - flat MCP tool parameters
        has_github: bool | None = None, has_tests: bool | None = None, has_forum: bool | None = None,
        language: Language = None, description_language: DescriptionLanguage = None,
        compatible_with_anki: AnkiVersion = None,
        anki_version_kind: AnkiVersionKind = None, anki_version_at_least: AnkiVersionAtLeast = None,
        updated_after: date | None = None, updated_before: date | None = None,
        archived: bool | None = None, author_id: AuthorId = None,
        is_fork: IsFork = None, has_forks: HasForks = None, fork_of: ForkOf = None,
        has_ai_declaration: HasAiDeclaration = None, has_ai_tooling: HasAiTooling = None,
        tags: Tags = None, exclude_tags: ExcludeTags = None,
        sort_by: SortField = SortField.RATING, descending: bool = True,
        limit: Limit = 20, offset: Offset = 0, snapshot: Snapshot = "latest",
    ) -> Page[AddonCard]:
        with tool_errors():
            filters = _filters(locals())
            return catalog.filter(filters, sort_by, descending, limit, offset, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Full record of one addon: AnkiWeb info and version branches, GitHub repository data and manifest, "
        "Anki Forum topic, AI summary and tags, and fork relations (forked_from, forks). Long texts and link "
        "lists are omitted unless requested in 'include'."))
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

    @mcp.tool(annotations=READ_ONLY, description=(
        "AnkiWeb description of an addon as plain text (format=text) or as the author's HTML (format=html). "
        "The HTML is not sanitized; when anki_web.description_pre_wrap is true AnkiWeb renders it with "
        "preserved line breaks."))
    def get_addon_description(addon_id: AddonId, max_chars: MaxChars = 20000, format: DescriptionFormat = "text",
                              snapshot: Snapshot = "latest") -> AddonText:
        with tool_errors():
            return catalog.text(addon_id, _DESCRIPTION_KINDS[format], max_chars, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Check whether addons support an Anki version, based on the parsed AnkiWeb branches (min and max "
        "point versions and the max version kind), with a separate verdict from the GitHub manifest. "
        "Verdicts: supported (a branch covers the version), likely (tested on an older version, newer Anki "
        "still runs it), unsupported (below the minimum, or above a hard limit: Anki disables the addon), "
        "unknown (no upper version given or no version data). list_anki_versions gives the real Anki versions. "
        "See anki-addons://dataset/anki-versions."))
    def check_compatibility(addon_ids: Annotated[list[int], Field(min_length=1, max_length=100)],
                            anki_version: Annotated[str, Field(description="e.g. 25.02 or 2.1.66")],
                            snapshot: Snapshot = "latest") -> list[CompatibilityVerdict]:
        with tool_errors():
            return services.compatibility.check(addon_ids, anki_version, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Maintenance health of an addon: last update/commit, archived flag, open issues, tests, CI and forum "
        "activity, plus a coarse label (active, stale, abandoned, unknown) with reasons. For a stale or abandoned "
        "addon, the reasons name its forks; signals.forks holds their ids for assessing them in turn."))
    def assess_maintenance(addon_id: AddonId, snapshot: Snapshot = "latest") -> MaintenanceReport:
        with tool_errors():
            return services.maintenance.assess(addon_id, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "Addons similar to a given one: overlapping wording in title, summary and topics, shared GitHub "
        "topics, shared AI function tags, the same author, or a fork relation (forks of the addon and the addons "
        "it was forked from). Addons without AnkiWeb votes are listed after voted ones."))
    def find_similar_addons(addon_id: AddonId, limit: Limit = 10, snapshot: Snapshot = "latest") -> list[SimilarAddon]:
        with tool_errors():
            return services.similarity.similar(addon_id, limit, parse_snapshot(snapshot))

    @mcp.tool(annotations=READ_ONLY, description=(
        "All addons of one author. Give exactly one of: github_user (addons whose GitHub repository belongs to "
        "the user), author_id (the derived AnkiWeb author of addon cards), or addon_id (the AnkiWeb author of "
        "that addon). AnkiWeb authors are derived from AnkiWeb's 'shared by this author' lists and are missing "
        "in snapshots collected before authors were tracked; use github_user there."))
    def list_addons_by_author(
        github_user: Annotated[str | None, Field(description="GitHub user, e.g. 'glutanimate'")] = None,
        author_id: AuthorId = None,
        addon_id: Annotated[int | None, Field(description="Any addon of the author")] = None,
        snapshot: Snapshot = "latest",
    ) -> Page[AddonCard]:
        with tool_errors():
            return catalog.by_author(github_user, parse_snapshot(snapshot), author_id, addon_id)

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
        "Dataset statistics: addon counts (total, with GitHub, with forum topic, with tests), the number of "
        "AnkiWeb authors, and optional "
        "group-by counts, e.g. by license, primary language, AI tag (ai_tag) or Anki version kind "
        "(anki_version_kind)."))
    def get_statistics(group_by: list[GroupField] | None = None,
                       top_values: Annotated[int, Field(ge=1, le=200)] = 20,
                       snapshot: Snapshot = "latest") -> Statistics:
        with tool_errors():
            return services.stats.statistics(parse_snapshot(snapshot), group_by, top_values)

    @mcp.tool(annotations=READ_ONLY, description=(
        "Leaderboard of addons by rating, likes, stars, forum posts or recency, optionally within one AI tag. "
        "metric=rating ranks by approval (Wilson lower bound of likes vs. dislikes)."))
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

    @mcp.tool(annotations=READ_ONLY, description=(
        "Stable Anki releases from 2.1.0 on as known when the snapshot was collected, newest first (the first is "
        "the latest Anki), each with its point version. Use it to check a version a user mentions or to find the "
        "latest Anki. Empty for snapshots collected before the dataset published the list."))
    def list_anki_versions(snapshot: Snapshot = "latest") -> list[AnkiRelease]:
        with tool_errors():
            return services.repository.list_anki_versions(parse_snapshot(snapshot))

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
