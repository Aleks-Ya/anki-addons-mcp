import json
from typing import Any

from anki_addons_mcp.domain.models import (
    AddonCard,
    AddonDetails,
    AiInfo,
    AnkiWebInfo,
    AnkiWebLink,
    Branch,
    ForumInfo,
    GithubInfo,
    GithubLink,
    LanguageBytes,
    Manifest,
    VersionKind,
)

CARD_COLUMNS = [
    "id", "title", "url", "rating", "likes", "dislikes", "update_date", "anki_version", "anki_point_version",
    "anki_version_kind", "ai_summary",
    "github_user", "github_repo", "github_stars", "github_last_commit", "github_archived", "github_license",
    "forum_posts_count", "ai_tags",
]


def _list(value: Any) -> list[Any]:
    return [v for v in value if v is not None] if isinstance(value, list) else []


def _structs(value: Any) -> list[dict[str, Any]]:
    return [v for v in _list(value) if isinstance(v, dict)]


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
        score=score,
    )


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
        )
    forum = None
    if row["has_forum"] or row["forum_topic_id"] is not None:
        forum = ForumInfo(
            anki_forum_url=row["forum_url"],
            topic_slug=row["forum_topic_slug"],
            topic_id=row["forum_topic_id"],
            last_posted_at=row["forum_last_posted_at"],
            posts_count=row["forum_posts_count"],
        )
    tags = _list(row["ai_tags"])
    has_ai = row["ai_summary"] or row["ai_model"] or tags
    ai = AiInfo(summary=row["ai_summary"], model=row["ai_model"], tags=tags) if has_ai else None
    return AddonDetails(id=row["id"], anki_web=anki_web, github=github, forum=forum, ai=ai)
