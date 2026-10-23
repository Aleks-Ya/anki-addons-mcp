import math
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, computed_field, field_validator

AI_PROVENANCE = "LLM-generated summary and tags; may contain mistakes. Verify against the description or README."
APPROVAL_DESCRIPTION = ("Share of likes among AnkiWeb votes, as the 95% Wilson lower bound (0..1): "
                        "dislikes and few votes lower it. Ranking by 'rating' sorts by this value.")
AUTHOR_ID_DESCRIPTION = ("Derived AnkiWeb author: the smallest addon id among the addons the author shared. "
                         "An anonymous label, not an AnkiWeb id; null in snapshots collected before authors "
                         "were tracked.")
FORK_DESCRIPTION = ("Fork relations: detection is incomplete (a fork that neither uses a GitHub fork nor links the "
                    "original from its description is missed), and 'ai' evidence may be inaccurate.")
_Z = 1.96


def approval_score(likes: int, dislikes: int) -> float:
    """95% Wilson score lower bound of the like ratio; 0 without votes."""
    n = likes + dislikes
    if n <= 0:
        return 0.0
    p = likes / n
    return (p + _Z * _Z / (2 * n) - _Z * math.sqrt(p * (1 - p) / n + _Z * _Z / (4 * n * n))) / (1 + _Z * _Z / n)


class VersionKind(StrEnum):
    HARD = "hard"
    TESTED = "tested"
    OPEN = "open"
    UNKNOWN = "unknown"


Kind = Annotated[VersionKind, BeforeValidator(lambda value: value or VersionKind.UNKNOWN)]


class Branch(BaseModel):
    min_version: str | None = None
    max_version: str | None = None
    updated: str | None = None
    min_point_version: int | None = None
    max_point_version: int | None = None
    max_version_kind: Kind = VersionKind.UNKNOWN


class AnkiWebLink(BaseModel):
    url: str
    section: str | None = None
    count: int = 0
    texts: list[str] = Field(default_factory=list)


class AnkiWebInfo(BaseModel):
    title: str
    addon_page_url: str
    contact_author_url: str | None = None
    rating: int = 0
    update_date: str | None = None
    anki_version: str | None = None
    anki_point_version: int | None = None
    anki_version_kind: Kind = VersionKind.UNKNOWN
    branches: list[Branch] = Field(default_factory=list)
    links: list[AnkiWebLink] = Field(default_factory=list)
    likes: int = 0
    dislikes: int = 0
    ai_declaration_markers: list[str] = Field(default_factory=list)
    description_language: str | None = None
    description_language_confidence: float | None = None
    description_pre_wrap: bool = False
    other_items_count: int | None = Field(
        default=None, description="Other items the author shared on AnkiWeb, shared decks included")

    @field_validator("update_date", "anki_version", "contact_author_url", "description_language", mode="before")
    @classmethod
    def _empty_to_none(cls, value: Any) -> Any:
        return value or None


class ForkEvidence(StrEnum):
    GITHUB_FORK = "github_fork"
    AI = "ai"
    OVERRIDE = "override"


class ForkRelation(BaseModel):
    id: int = Field(description="AnkiWeb id of the addon this one was forked from")
    evidence: ForkEvidence = Field(
        description="'github_fork' (the repo is a GitHub fork of the parent's repo), 'ai' (an LLM read the "
                    "description; may be inaccurate) or 'override' (set by hand)")


class GithubLink(BaseModel):
    url: str
    user: str | None = None
    repo: str | None = None


class LanguageBytes(BaseModel):
    name: str
    bytes: int


class Manifest(BaseModel):
    package: str | None = None
    name: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    min_point_version: int | None = None
    max_point_version: int | None = None
    homepage: str | None = None
    mod: int | None = None
    min_version: str | None = None
    max_version: str | None = None
    max_version_kind: Kind = VersionKind.UNKNOWN


class GithubInfo(BaseModel):
    user: str | None = None
    repo: str | None = None
    repo_source: str | None = None
    languages: list[str] = Field(default_factory=list)
    stars: int = 0
    last_commit: str | None = None
    links: list[GithubLink] = Field(default_factory=list)
    action_count: int | None = None
    tests_count: int | None = None
    license: str | None = None
    forks: int | None = None
    open_issues: int | None = None
    size_kb: int | None = None
    topics: list[str] = Field(default_factory=list)
    repo_description: str | None = None
    homepage: str | None = None
    archived: bool | None = None
    pushed_at: str | None = None
    created_at: str | None = None
    primary_language: str | None = None
    language_bytes: list[LanguageBytes] = Field(default_factory=list)
    manifest: Manifest | None = None
    dependencies: list[str] = Field(default_factory=list)
    ai_tooling_markers: list[str] = Field(default_factory=list)
    fork_source: str | None = Field(
        default=None, description="Root repo (owner/repo) of the GitHub fork network when the repo is a fork")

    @computed_field
    def url(self) -> str | None:
        if self.user and self.repo:
            return f"https://github.com/{self.user}/{self.repo}"
        return None


class ForumInfo(BaseModel):
    anki_forum_url: str | None = None
    topic_slug: str | None = None
    topic_id: int | None = None
    last_posted_at: str | None = None
    posts_count: int | None = None


class AiInfo(BaseModel):
    summary: str | None = None
    model: str | None = None
    tags: list[str] = Field(default_factory=list)

    @computed_field
    def provenance(self) -> str:
        return AI_PROVENANCE


class AuthorInfo(BaseModel):
    id: int = Field(description=AUTHOR_ID_DESCRIPTION)
    addon_count: int = Field(description="Number of the author's addons in the snapshot")


class AddonDetails(BaseModel):
    id: int
    anki_web: AnkiWebInfo
    github: GithubInfo | None = None
    forum: ForumInfo | None = None
    ai: AiInfo | None = None
    author: AuthorInfo | None = None
    forked_from: ForkRelation | None = Field(
        default=None, description="The addon this one was forked from; an addon has at most one. " + FORK_DESCRIPTION)
    forks: list[int] = Field(default_factory=list, description="Addons forked from this one. " + FORK_DESCRIPTION)
    description: str | None = None
    description_html: str | None = None
    readme: str | None = None

    def without_texts(self) -> "AddonDetails":
        return self.model_copy(update={"description": None, "description_html": None, "readme": None})


class AddonCard(BaseModel):
    id: int
    title: str
    url: str
    rating: int
    likes: int
    dislikes: int
    update_date: str | None = None
    anki_version: str | None = None
    anki_point_version: int | None = None
    anki_version_kind: Kind = VersionKind.UNKNOWN
    ai_summary: str | None = Field(default=None, description=AI_PROVENANCE)
    github_user: str | None = None
    github_repo: str | None = None
    github_stars: int | None = None
    github_last_commit: str | None = None
    github_archived: bool | None = None
    license: str | None = None
    forum_posts_count: int | None = None
    ai_tags: list[str] = Field(default_factory=list, description=AI_PROVENANCE)
    author_id: int | None = Field(default=None, description=AUTHOR_ID_DESCRIPTION)
    forked_from: int | None = Field(default=None, description="Addon this one was forked from")
    forks: list[int] = Field(default_factory=list, description="Addons forked from this one")
    score: float | None = None

    @computed_field(description=APPROVAL_DESCRIPTION)
    def approval(self) -> float:
        return round(approval_score(self.likes, self.dislikes), 4)

    @classmethod
    def from_details(cls, details: AddonDetails, score: float | None = None) -> "AddonCard":
        github = details.github
        return cls(
            id=details.id,
            title=details.anki_web.title,
            url=details.anki_web.addon_page_url,
            rating=details.anki_web.rating,
            likes=details.anki_web.likes,
            dislikes=details.anki_web.dislikes,
            update_date=details.anki_web.update_date,
            anki_version=details.anki_web.anki_version,
            anki_point_version=details.anki_web.anki_point_version,
            anki_version_kind=details.anki_web.anki_version_kind,
            ai_summary=details.ai.summary if details.ai else None,
            github_user=github.user if github else None,
            github_repo=github.repo if github else None,
            github_stars=github.stars if github else None,
            github_last_commit=github.last_commit if github else None,
            github_archived=github.archived if github else None,
            license=github.license if github else None,
            forum_posts_count=details.forum.posts_count if details.forum else None,
            ai_tags=list(details.ai.tags) if details.ai else [],
            author_id=details.author.id if details.author else None,
            forked_from=details.forked_from.id if details.forked_from else None,
            forks=list(details.forks),
            score=score,
        )


class Tag(BaseModel):
    name: str
    group: str
    description: str | None = None


class AnkiRelease(BaseModel):
    version: str = Field(description="The version as Anki writes it, e.g. 25.09.2 or 2.1.66")
    point_version: int = Field(description="Anki's sortable integer encoding: 2.1.x -> x, YY.MM.PP -> YYMMPP")


class Page[T](BaseModel):
    items: list[T]
    total: int
    offset: int
    limit: int | None


class SnapshotInfo(BaseModel):
    date: date
    latest: bool
    report_generation_date: datetime | None = None
    script_version: str | None = None


class Aggregation(BaseModel):
    addon_number: int
    addon_with_github_number: int
    addon_with_anki_forum_page_number: int
    addon_with_unit_tests_number: int
    author_number: int


class AddonHistoryPoint(BaseModel):
    snapshot: date
    present: bool
    title: str | None = None
    rating: int | None = None
    likes: int | None = None
    dislikes: int | None = None
    github_stars: int | None = None
    update_date: str | None = None
    anki_version: str | None = None
    anki_version_kind: VersionKind | None = None


class TextKind(StrEnum):
    DESCRIPTION = "description"
    DESCRIPTION_HTML = "description_html"
    README = "readme"


class GroupField(StrEnum):
    LICENSE = "license"
    PRIMARY_LANGUAGE = "primary_language"
    DESCRIPTION_LANGUAGE = "description_language"
    ANKI_VERSION = "anki_version"
    ANKI_VERSION_KIND = "anki_version_kind"
    UPDATE_YEAR = "update_year"
    GITHUB_TOPIC = "github_topic"
    AI_DECLARATION_MARKER = "ai_declaration_marker"
    AI_TOOLING_MARKER = "ai_tooling_marker"
    AI_TAG = "ai_tag"


NONE_GROUP = "(none)"


class SqlResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
