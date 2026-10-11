from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class SortField(StrEnum):
    RELEVANCE = "relevance"
    RATING = "rating"
    LIKES = "likes"
    STARS = "stars"
    UPDATE_DATE = "update_date"
    LAST_COMMIT = "last_commit"
    FORUM_POSTS = "forum_posts"


class AddonFilters(BaseModel):
    addon_ids: list[int] | None = None
    min_rating: int | None = None
    min_likes: int | None = None
    min_stars: int | None = None
    has_github: bool | None = None
    has_tests: bool | None = None
    has_forum: bool | None = None
    license: str | None = None
    language: str | None = None
    description_language: str | None = None
    github_user: str | None = None
    topic: str | None = None
    updated_after: date | None = None
    updated_before: date | None = None
    archived: bool | None = None
    has_ai_declaration: bool | None = None
    has_ai_tooling: bool | None = None
    compatible_with_anki: str | None = None
    tags: list[str] | None = None
    exclude_tags: list[str] | None = None


class AddonQuery(BaseModel):
    text: str | None = None
    filters: AddonFilters = Field(default_factory=AddonFilters)
    sort: SortField = SortField.RELEVANCE
    descending: bool = True
    offset: int = Field(default=0, ge=0)
    limit: int | None = Field(default=20, ge=1)

    def effective_sort(self) -> SortField:
        if self.sort == SortField.RELEVANCE and not self.has_text():
            return SortField.RATING
        return self.sort

    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())
