import re
from collections import Counter
from datetime import date
from typing import Any

from anki_addons_mcp.domain.compatibility import is_compatible
from anki_addons_mcp.domain.errors import SnapshotNotFound
from anki_addons_mcp.domain.models import (
    NONE_GROUP,
    AddonCard,
    AddonDetails,
    AddonHistoryPoint,
    Aggregation,
    GroupField,
    Page,
    SnapshotInfo,
    Tag,
    TextKind,
)
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.domain.query import AddonFilters, AddonQuery, SortField

_WORD = re.compile(r"\w+")


def _lower(value: str | None) -> str | None:
    return value.lower() if value else None


def _matches(d: AddonDetails, f: AddonFilters) -> bool:
    gh = d.github
    aw = d.anki_web
    checks: list[bool] = []
    if f.addon_ids is not None:
        checks.append(d.id in f.addon_ids)
    if f.min_rating is not None:
        checks.append(aw.rating >= f.min_rating)
    if f.min_likes is not None:
        checks.append(aw.likes >= f.min_likes)
    if f.min_stars is not None:
        checks.append(gh is not None and gh.stars >= f.min_stars)
    if f.has_github is not None:
        checks.append((gh is not None) == f.has_github)
    if f.has_tests is not None:
        checks.append(bool(gh and gh.tests_count) == f.has_tests)
    if f.has_forum is not None:
        checks.append(bool(d.forum and d.forum.anki_forum_url) == f.has_forum)
    if f.license is not None:
        checks.append(gh is not None and _lower(gh.license) == f.license.lower())
    if f.language is not None:
        language = f.language.lower()
        checks.append(gh is not None and (language in [x.lower() for x in gh.languages]
                                          or _lower(gh.primary_language) == language))
    if f.description_language is not None:
        checks.append(_lower(aw.description_language) == f.description_language.lower())
    if f.github_user is not None:
        checks.append(gh is not None and _lower(gh.user) == f.github_user.lower())
    if f.topic is not None:
        checks.append(gh is not None and f.topic.lower() in [x.lower() for x in gh.topics])
    if f.updated_after is not None:
        checks.append(bool(aw.update_date) and (aw.update_date or "") >= f.updated_after.isoformat())
    if f.updated_before is not None:
        checks.append(bool(aw.update_date) and (aw.update_date or "") <= f.updated_before.isoformat())
    if f.archived is not None:
        checks.append(bool(gh and gh.archived) == f.archived)
    if f.has_ai_declaration is not None:
        checks.append(bool(aw.ai_declaration_markers) == f.has_ai_declaration)
    if f.has_ai_tooling is not None:
        checks.append(bool(gh and gh.ai_tooling_markers) == f.has_ai_tooling)
    if f.compatible_with_anki is not None:
        checks.append(is_compatible(aw.branches, f.compatible_with_anki))
    if f.tags or f.exclude_tags:
        tags = {t.lower() for t in d.ai.tags} if d.ai else set()
        if f.tags:
            checks.append({t.lower() for t in f.tags} <= tags)
        if f.exclude_tags:
            checks.append(not ({t.lower() for t in f.exclude_tags} & tags))
    return all(checks)


def _score(d: AddonDetails, terms: list[str]) -> float:
    title = Counter(_WORD.findall(d.anki_web.title.lower()))
    body = Counter(_WORD.findall(" ".join(filter(None, [
        d.description,
        d.ai.summary if d.ai else None,
        " ".join(d.ai.tags) if d.ai else None,
        " ".join(d.github.topics) if d.github else None,
        d.github.repo_description if d.github else None,
    ])).lower()))
    return float(sum(2 * title[t] + body[t] for t in terms))


def _sort_value(d: AddonDetails, field: SortField, score: float | None) -> Any:
    gh = d.github
    match field:
        case SortField.RELEVANCE:
            return score
        case SortField.RATING:
            return d.anki_web.rating
        case SortField.LIKES:
            return d.anki_web.likes
        case SortField.STARS:
            return gh.stars if gh else None
        case SortField.UPDATE_DATE:
            return d.anki_web.update_date or None
        case SortField.LAST_COMMIT:
            return gh.last_commit if gh else None
        case SortField.FORUM_POSTS:
            return d.forum.posts_count if d.forum else None


def _group_values(d: AddonDetails, field: GroupField) -> list[str | None]:
    gh = d.github
    aw = d.anki_web
    match field:
        case GroupField.LICENSE:
            return [gh.license if gh else None]
        case GroupField.PRIMARY_LANGUAGE:
            return [gh.primary_language if gh else None]
        case GroupField.DESCRIPTION_LANGUAGE:
            return [aw.description_language]
        case GroupField.ANKI_VERSION:
            return [aw.anki_version]
        case GroupField.UPDATE_YEAR:
            return [aw.update_date[:4] if aw.update_date else None]
        case GroupField.GITHUB_TOPIC:
            return list(gh.topics) if gh and gh.topics else [None]
        case GroupField.AI_DECLARATION_MARKER:
            return list(aw.ai_declaration_markers) or [None]
        case GroupField.AI_TOOLING_MARKER:
            return list(gh.ai_tooling_markers) if gh and gh.ai_tooling_markers else [None]
        case GroupField.AI_TAG:
            return list(d.ai.tags) if d.ai and d.ai.tags else [None]


class InMemoryAddonRepository(AddonRepository):
    def __init__(self, snapshots: dict[date, list[AddonDetails]], infos: dict[date, SnapshotInfo] | None = None,
                 documentation: str = "In-memory Anki addons dataset.", tags: dict[date, list[Tag]] | None = None):
        if not snapshots:
            raise ValueError("At least one snapshot is required")
        self._snapshots = {d: {a.id: a for a in addons} for d, addons in snapshots.items()}
        self._latest = max(snapshots)
        self._infos = infos or {}
        self._documentation = documentation
        self._tags = tags or {}

    def _data(self, snapshot: date | None) -> dict[int, AddonDetails]:
        key = snapshot or self._latest
        if key not in self._snapshots:
            raise SnapshotNotFound(key)
        return self._snapshots[key]

    def list_snapshots(self) -> list[SnapshotInfo]:
        result = []
        for d in sorted(self._snapshots):
            info = self._infos.get(d) or SnapshotInfo(date=d, latest=False)
            result.append(info.model_copy(update={"date": d, "latest": d == self._latest}))
        return result

    def get_addon(self, addon_id: int, snapshot: date | None = None) -> AddonDetails | None:
        details = self._data(snapshot).get(addon_id)
        return details.without_texts() if details else None

    def get_addons(self, addon_ids: list[int], snapshot: date | None = None) -> list[AddonDetails]:
        data = self._data(snapshot)
        return [data[i].without_texts() for i in dict.fromkeys(addon_ids) if i in data]

    def find(self, query: AddonQuery, snapshot: date | None = None) -> Page[AddonCard]:
        terms = [t for t in _WORD.findall((query.text or "").lower())]
        rows: list[tuple[AddonDetails, float | None]] = []
        for details in self._data(snapshot).values():
            if not _matches(details, query.filters):
                continue
            score = _score(details, terms) if query.has_text() else None
            if score is not None and score <= 0:
                continue
            rows.append((details, score))
        field = query.effective_sort()
        rows.sort(key=lambda r: r[0].id)
        present = [r for r in rows if _sort_value(r[0], field, r[1]) is not None]
        missing = [r for r in rows if _sort_value(r[0], field, r[1]) is None]
        present.sort(key=lambda r: _sort_value(r[0], field, r[1]), reverse=query.descending)
        ordered = present + missing
        end = None if query.limit is None else query.offset + query.limit
        items = [AddonCard.from_details(d, s) for d, s in ordered[query.offset:end]]
        return Page[AddonCard](items=items, total=len(ordered), offset=query.offset, limit=query.limit)

    def get_text(self, addon_id: int, kind: TextKind, snapshot: date | None = None) -> str | None:
        details = self._data(snapshot).get(addon_id)
        if details is None:
            return None
        return (details.description if kind == TextKind.DESCRIPTION else details.readme) or None

    def get_history(self, addon_id: int, from_: date | None = None, to: date | None = None) -> list[AddonHistoryPoint]:
        points = []
        for d in sorted(self._snapshots):
            if (from_ and d < from_) or (to and d > to):
                continue
            details = self._snapshots[d].get(addon_id)
            if details is None:
                points.append(AddonHistoryPoint(snapshot=d, present=False))
                continue
            aw = details.anki_web
            points.append(AddonHistoryPoint(
                snapshot=d, present=True, title=aw.title, rating=aw.rating, likes=aw.likes, dislikes=aw.dislikes,
                github_stars=details.github.stars if details.github else None, update_date=aw.update_date,
                anki_version=aw.anki_version,
            ))
        return points

    def get_aggregation(self, snapshot: date | None = None) -> Aggregation:
        addons = list(self._data(snapshot).values())
        return Aggregation(
            addon_number=len(addons),
            addon_with_github_number=sum(1 for a in addons if a.github is not None),
            addon_with_anki_forum_page_number=sum(1 for a in addons if a.forum and a.forum.anki_forum_url),
            addon_with_unit_tests_number=sum(1 for a in addons if a.github and a.github.tests_count),
        )

    def group_counts(self, field: GroupField, snapshot: date | None = None) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for details in self._data(snapshot).values():
            for value in _group_values(details, field):
                counter[value or NONE_GROUP] += 1
        return dict(counter)

    def list_tags(self, snapshot: date | None = None) -> list[Tag]:
        key = snapshot or self._latest
        self._data(key)
        return sorted(self._tags.get(key, []), key=lambda t: (t.group, t.name))

    def get_documentation(self) -> str:
        return self._documentation
