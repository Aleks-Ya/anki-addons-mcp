from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from anki_addons_mcp.application.tags import TagService
from anki_addons_mcp.domain.errors import AddonNotFound, InvalidQuery
from anki_addons_mcp.domain.models import AddonCard, AddonDetails, Page, TextKind
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.domain.query import AddonFilters, AddonQuery, SortField

MAX_LIMIT = 100


class TopMetric(StrEnum):
    RATING = "rating"
    LIKES = "likes"
    STARS = "stars"
    FORUM_POSTS = "forum_posts"
    RECENTLY_UPDATED = "recently_updated"


_TOP_SORT = {
    TopMetric.RATING: SortField.RATING,
    TopMetric.LIKES: SortField.LIKES,
    TopMetric.STARS: SortField.STARS,
    TopMetric.FORUM_POSTS: SortField.FORUM_POSTS,
    TopMetric.RECENTLY_UPDATED: SortField.UPDATE_DATE,
}


class AddonText(BaseModel):
    addon_id: int
    kind: TextKind
    text: str | None
    total_chars: int
    truncated: bool


def _without_links(details: AddonDetails) -> AddonDetails:
    anki_web = details.anki_web.model_copy(update={"links": []})
    github = details.github.model_copy(update={"links": []}) if details.github else None
    return details.model_copy(update={"anki_web": anki_web, "github": github})


def check_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_LIMIT:
        raise InvalidQuery(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


class CatalogService:
    def __init__(self, repository: AddonRepository, tags: TagService):
        self._repository = repository
        self._tags = tags

    def search(
        self, text: str, limit: int = 20, offset: int = 0, filters: AddonFilters | None = None,
        snapshot: date | None = None,
    ) -> Page[AddonCard]:
        if not text.strip():
            raise InvalidQuery("query must not be empty")
        filters = filters or AddonFilters()
        self._tags.validate_filters(filters, snapshot)
        query = AddonQuery(text=text, filters=filters, sort=SortField.RELEVANCE,
                           offset=offset, limit=check_limit(limit))
        return self._repository.find(query, snapshot)

    def filter(
        self, filters: AddonFilters, sort: SortField = SortField.RATING, descending: bool = True,
        limit: int = 20, offset: int = 0, snapshot: date | None = None,
    ) -> Page[AddonCard]:
        self._tags.validate_filters(filters, snapshot)
        query = AddonQuery(filters=filters, sort=sort, descending=descending, offset=offset,
                           limit=check_limit(limit))
        return self._repository.find(query, snapshot)

    def top(self, metric: TopMetric, limit: int = 10, snapshot: date | None = None,
            tag: str | None = None) -> Page[AddonCard]:
        filters = AddonFilters(has_github=True) if metric == TopMetric.STARS else AddonFilters()
        if metric == TopMetric.FORUM_POSTS:
            filters = AddonFilters(has_forum=True)
        if tag:
            filters.tags = [tag]
        return self.filter(filters, _TOP_SORT[metric], True, limit, 0, snapshot)

    def by_author(self, github_user: str | None = None, snapshot: date | None = None, author_id: int | None = None,
                  addon_id: int | None = None) -> Page[AddonCard]:
        given = [v for v in (github_user, author_id, addon_id) if v is not None]
        if len(given) != 1:
            raise InvalidQuery("Give exactly one of github_user, author_id or addon_id")
        if addon_id is not None:
            author_id = self._author_of(addon_id, snapshot)
        filters = AddonFilters(github_user=github_user, author_id=author_id)
        return self._repository.find(AddonQuery(filters=filters, sort=SortField.RATING, limit=None), snapshot)

    def _author_of(self, addon_id: int, snapshot: date | None) -> int:
        details = self._repository.get_addon(addon_id, snapshot)
        if details is None:
            raise AddonNotFound(addon_id, snapshot)
        if details.author is None:
            raise InvalidQuery(f"Addon {addon_id} has no AnkiWeb author data in this snapshot "
                               "(snapshots collected before authors were tracked have none); try github_user")
        return details.author.id

    def by_tag(self, tag: str, snapshot: date | None = None) -> Page[AddonCard]:
        filters = AddonFilters(tags=[tag])
        self._tags.validate_filters(filters, snapshot)
        return self._repository.find(AddonQuery(filters=filters, sort=SortField.RATING, limit=None), snapshot)

    def get(
        self, addon_id: int, snapshot: date | None = None, include_description: bool = False,
        include_readme: bool = False, max_chars: int | None = None, include_links: bool = True,
    ) -> AddonDetails:
        details = self._repository.get_addon(addon_id, snapshot)
        if details is None:
            raise AddonNotFound(addon_id, snapshot)
        if not include_links:
            details = _without_links(details)
        update: dict[str, str | None] = {}
        if include_description:
            update["description"] = self.text(addon_id, TextKind.DESCRIPTION, max_chars, snapshot).text
        if include_readme:
            update["readme"] = self.text(addon_id, TextKind.README, max_chars, snapshot).text
        return details.model_copy(update=update) if update else details

    def get_many(self, addon_ids: list[int], snapshot: date | None = None) -> list[AddonDetails]:
        found = {details.id: details for details in self._repository.get_addons(addon_ids, snapshot)}
        missing = [addon_id for addon_id in addon_ids if addon_id not in found]
        if missing:
            raise AddonNotFound(missing[0], snapshot)
        return [found[addon_id] for addon_id in addon_ids]

    def text(
        self, addon_id: int, kind: TextKind, max_chars: int | None = None, snapshot: date | None = None
    ) -> AddonText:
        if self._repository.get_addon(addon_id, snapshot) is None:
            raise AddonNotFound(addon_id, snapshot)
        text = self._repository.get_text(addon_id, kind, snapshot)
        total = len(text) if text else 0
        truncated = bool(text and max_chars is not None and total > max_chars)
        if text and truncated and max_chars is not None:
            text = text[:max_chars]
        return AddonText(addon_id=addon_id, kind=kind, text=text, total_chars=total, truncated=truncated)
