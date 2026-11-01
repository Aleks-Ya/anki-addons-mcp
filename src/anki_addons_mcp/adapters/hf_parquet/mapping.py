import json
from typing import Any

from pydantic import BaseModel

from anki_addons_mcp.domain.models import (
    AddonCard,
    AddonDetails,
    AiInfo,
    AnkiWebInfo,
    AnkiWebLink,
    AuthorInfo,
    Branch,
    ForkRelation,
    ForumInfo,
    GithubContributor,
    GithubInfo,
    GithubLink,
    GithubRelease,
    LanguageBytes,
    Manifest,
    PackageSummary,
    VersionKind,
)

CARD_COLUMNS = [
    "id", "title", "url", "rating", "likes", "dislikes", "update_date", "anki_version", "anki_point_version",
    "anki_version_kind", "ai_summary",
    "github_user", "github_repo", "github_stars", "github_last_commit", "github_archived", "github_license",
    "forum_posts_count", "ai_tags", "author_id",
    "forked_from", "forks",
]


def _list(value: Any) -> list[Any]:
    return [v for v in value if v is not None] if isinstance(value, list) else []


def _structs(value: Any) -> list[dict[str, Any]]:
    return [v for v in _list(value) if isinstance(v, dict)]


def _validated[T: BaseModel](model: type[T], value: Any) -> list[T] | None:
    """None stays None: the dataset uses it for 'not known', unlike an empty list."""
    return None if value is None else [model.model_validate(v) for v in _structs(value)]


def _manifest(value: Any) -> Manifest | None:
    if not value:
        return None
    raw = json.loads(value) if isinstance(value, str) else value
    if not isinstance(raw, dict):
        return None
    raw["conflicts"] = _list(raw.get("conflicts"))
    return Manifest.model_validate(raw)


def row_to_card(row: dict[str, Any], score: float | None = None) -> AddonCard:
    return AddonCard(
        id=row["id"], title=row["title"] or "", url=row["url"] or "", rating=row["rating"] or 0,
        likes=row["likes"] or 0, dislikes=row["dislikes"] or 0, update_date=row["update_date"] or None,
        anki_version=row["anki_version"] or None, anki_point_version=row["anki_point_version"],
        anki_version_kind=row["anki_version_kind"] or VersionKind.UNKNOWN, ai_summary=row["ai_summary"],
        github_user=row["github_user"], github_repo=row["github_repo"], github_stars=row["github_stars"],
        github_last_commit=row["github_last_commit"], github_archived=row["github_archived"],
        license=row["github_license"], forum_posts_count=row["forum_posts_count"], ai_tags=_list(row["ai_tags"]),
        author_id=row["author_id"], forked_from=row["forked_from"]["id"] if row["forked_from"] else None,
        forks=_list(row["forks"]), score=score,
    )


def _author(row: dict[str, Any]) -> AuthorInfo | None:
    if row["author_id"] is None:
        return None
    return AuthorInfo(id=row["author_id"], addon_count=row["author_addon_count"] or 0)


def row_to_details(row: dict[str, Any]) -> AddonDetails:
    anki_web = AnkiWebInfo(
        title=row["title"] or "",
        addon_page_url=row["url"] or "",
        contact_author_url=row["contact_author_url"],
        rating=row["rating"] or 0,
        update_date=row["update_date"] or None,
        anki_version=row["anki_version"] or None,
        anki_point_version=row["anki_point_version"],
        anki_version_kind=row["anki_version_kind"] or VersionKind.UNKNOWN,
        branches=[Branch.model_validate(b) for b in _structs(row["branches"])],
        links=[AnkiWebLink.model_validate(link) for link in _structs(row["links"]) if link.get("url")],
        likes=row["likes"] or 0,
        dislikes=row["dislikes"] or 0,
        ai_declaration_markers=_list(row["ai_declaration_markers"]),
        description_language=row["description_language"],
        description_language_confidence=row["description_language_confidence"],
        description_pre_wrap=bool(row["description_pre_wrap"]),
        other_items_count=row["other_items_count"],
        package_size_kb=row["package_size_kb"],
    )
    github = None
    if row["has_github"]:
        github = GithubInfo(
            user=row["github_user"],
            repo=row["github_repo"],
            repo_source=row["github_repo_source"],
            languages=_list(row["github_languages"]),
            stars=row["github_stars"] or 0,
            last_commit=row["github_last_commit"],
            links=[GithubLink.model_validate(link) for link in _structs(row["github_links"]) if link.get("url")],
            action_count=row["github_action_count"],
            tests_count=row["github_tests_count"],
            license=row["github_license"],
            forks=row["github_forks"],
            open_issues=row["github_open_issues"],
            size_kb=row["github_size_kb"],
            topics=_list(row["github_topics"]),
            repo_description=row["github_repo_description"],
            homepage=row["github_homepage"],
            archived=row["github_archived"],
            pushed_at=row["github_pushed_at"],
            created_at=row["github_created_at"],
            primary_language=row["github_primary_language"],
            language_bytes=[LanguageBytes.model_validate(lb) for lb in _structs(row["github_language_bytes"])],
            manifest=_manifest(row["github_manifest"]),
            dependencies=_list(row["github_dependencies"]),
            ai_tooling_markers=_list(row["github_ai_tooling_markers"]),
            fork_source=row["github_fork_source"],
            releases=_validated(GithubRelease, row["github_releases"]),
            release_count=row["github_release_count"],
            latest_release_tag=row["github_latest_release_tag"],
            latest_release_at=row["github_latest_release_at"],
            release_downloads=row["github_release_downloads"],
            contributors=_validated(GithubContributor, row["github_contributors"]),
            contributor_count=row["github_contributor_count"],
            weekly_commits=row["github_weekly_commits"],
            commits_last_year=row["github_commits_last_year"],
            open_issue_count=row["github_open_issue_count"],
            closed_issue_count=row["github_closed_issue_count"],
            open_pr_count=row["github_open_pr_count"],
            closed_pr_count=row["github_closed_pr_count"],
            merged_pr_count=row["github_merged_pr_count"],
            has_issues_enabled=row["github_has_issues_enabled"],
            last_issue_closed_at=row["github_last_issue_closed_at"],
            median_first_response_hours=row["github_median_first_response_hours"],
            first_response_sample=row["github_first_response_sample"],
            outside_pr_merge_share=row["github_outside_pr_merge_share"],
            outside_prs_decided=row["github_outside_prs_decided"],
            outside_prs_merged=row["github_outside_prs_merged"],
        )
    forum = None
    if row["has_forum"] or row["forum_topic_id"] is not None:
        forum = ForumInfo(
            anki_forum_url=row["forum_url"],
            topic_slug=row["forum_topic_slug"],
            topic_id=row["forum_topic_id"],
            last_posted_at=row["forum_last_posted_at"],
            posts_count=row["forum_posts_count"],
            topic_source=row["forum_topic_source"],
        )
    tags = _list(row["ai_tags"])
    has_ai = row["ai_summary"] or row["ai_model"] or tags
    ai = AiInfo(summary=row["ai_summary"], model=row["ai_model"], tags=tags) if has_ai else None
    forked_from = ForkRelation.model_validate(row["forked_from"]) if row["forked_from"] else None
    package = PackageSummary.model_validate(row["package"]) if row["package"] else None
    return AddonDetails(id=row["id"], anki_web=anki_web, github=github, forum=forum, ai=ai, author=_author(row),
                        forked_from=forked_from, forks=_list(row["forks"]), package=package)
