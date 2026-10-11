from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator

AI_PROVENANCE = "LLM-generated summary; may contain mistakes. Verify against the description or README."


class Branch(BaseModel):
    min_version: str | None = None
    max_version: str | None = None
    updated: str | None = None


class AnkiWebInfo(BaseModel):
    title: str
    addon_page_url: str
    contact_author_url: str | None = None
    rating: int = 0
    update_date: str | None = None
    anki_version: str | None = None
    branches: list[Branch] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    likes: int = 0
    dislikes: int = 0
    ai_declaration_markers: list[str] = Field(default_factory=list)
    description_language: str | None = None
    description_language_confidence: float | None = None

    @field_validator("update_date", "anki_version", "contact_author_url", "description_language", mode="before")
    @classmethod
    def _empty_to_none(cls, value: Any) -> Any:
        return value or None


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


class GithubInfo(BaseModel):
    user: str | None = None
    repo: str | None = None
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

    @computed_field
    def provenance(self) -> str:
        return AI_PROVENANCE


class AddonDetails(BaseModel):
    id: int
    anki_web: AnkiWebInfo
    github: GithubInfo | None = None
    forum: ForumInfo | None = None
    ai: AiInfo | None = None
    description: str | None = None
    readme: str | None = None

    def without_texts(self) -> "AddonDetails":
        return self.model_copy(update={"description": None, "readme": None})


class AddonCard(BaseModel):
    id: int
    title: str
    url: str
    rating: int
    likes: int
    dislikes: int
    update_date: str | None = None
    anki_version: str | None = None
    ai_summary: str | None = Field(default=None, description=AI_PROVENANCE)
    github_user: str | None = None
    github_repo: str | None = None
    github_stars: int | None = None
    github_last_commit: str | None = None
    github_archived: bool | None = None
    license: str | None = None
    forum_posts_count: int | None = None
    score: float | None = None

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
            ai_summary=details.ai.summary if details.ai else None,
            github_user=github.user if github else None,
            github_repo=github.repo if github else None,
            github_stars=github.stars if github else None,
            github_last_commit=github.last_commit if github else None,
            github_archived=github.archived if github else None,
            license=github.license if github else None,
            forum_posts_count=details.forum.posts_count if details.forum else None,
            score=score,
        )


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


class TextKind(StrEnum):
    DESCRIPTION = "description"
    README = "readme"


class GroupField(StrEnum):
    LICENSE = "license"
    PRIMARY_LANGUAGE = "primary_language"
    DESCRIPTION_LANGUAGE = "description_language"
    ANKI_VERSION = "anki_version"
    UPDATE_YEAR = "update_year"
    GITHUB_TOPIC = "github_topic"
    AI_DECLARATION_MARKER = "ai_declaration_marker"
    AI_TOOLING_MARKER = "ai_tooling_marker"


NONE_GROUP = "(none)"


class SqlResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
