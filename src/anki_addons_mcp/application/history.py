from datetime import date

from pydantic import BaseModel

from anki_addons_mcp.application.catalog import check_limit
from anki_addons_mcp.application.snapshots import SnapshotService
from anki_addons_mcp.domain.errors import AddonNotFound, InvalidQuery
from anki_addons_mcp.domain.models import AddonCard, AddonHistoryPoint
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.domain.query import AddonQuery


class AddonChange(BaseModel):
    id: int
    title: str
    rating_from: int
    rating_to: int
    rating_delta: int
    stars_from: int | None
    stars_to: int | None
    stars_delta: int | None
    update_date_from: str | None
    update_date_to: str | None


class SnapshotDiff(BaseModel):
    from_snapshot: date
    to_snapshot: date
    addons_from: int
    addons_to: int
    added_count: int
    removed_count: int
    updated_count: int
    added: list[AddonCard]
    removed: list[AddonCard]
    updated: list[AddonChange]
    rating_movers: list[AddonChange]
    star_movers: list[AddonChange]


class AddonHistory(BaseModel):
    addon_id: int
    points: list[AddonHistoryPoint]


def _change(old: AddonCard, new: AddonCard) -> AddonChange:
    stars_delta = None
    if old.github_stars is not None and new.github_stars is not None:
        stars_delta = new.github_stars - old.github_stars
    return AddonChange(
        id=new.id, title=new.title, rating_from=old.rating, rating_to=new.rating,
        rating_delta=new.rating - old.rating, stars_from=old.github_stars, stars_to=new.github_stars,
        stars_delta=stars_delta, update_date_from=old.update_date, update_date_to=new.update_date,
    )


class HistoryService:
    def __init__(self, repository: AddonRepository, snapshots: SnapshotService):
        self._repository = repository
        self._snapshots = snapshots

    def history(self, addon_id: int, from_: date | None = None, to: date | None = None) -> AddonHistory:
        if from_ and to and from_ > to:
            raise InvalidQuery("'from' must not be after 'to'")
        points = self._repository.get_history(addon_id, from_, to)
        if not any(point.present for point in points):
            raise AddonNotFound(addon_id)
        return AddonHistory(addon_id=addon_id, points=points)

    def diff(self, from_: date | None = None, to: date | None = None, limit: int = 20) -> SnapshotDiff:
        check_limit(limit)
        to_date = self._snapshots.resolve(to)
        if from_ is None:
            from_ = self._snapshots.previous(to_date)
            if from_ is None:
                raise InvalidQuery(f"There is no snapshot before {to_date}")
        from_date = self._snapshots.resolve(from_)
        if from_date >= to_date:
            raise InvalidQuery("'from' snapshot must be earlier than 'to' snapshot")
        old = self._all_cards(from_date)
        new = self._all_cards(to_date)
        added = sorted((new[i] for i in new.keys() - old.keys()), key=lambda c: (-c.rating, c.id))
        removed = sorted((old[i] for i in old.keys() - new.keys()), key=lambda c: (-c.rating, c.id))
        changes = [_change(old[i], new[i]) for i in sorted(new.keys() & old.keys())]
        updated = sorted((c for c in changes if c.update_date_from != c.update_date_to),
                         key=lambda c: (c.update_date_to or "", c.id), reverse=True)
        rating_movers = sorted((c for c in changes if c.rating_delta),
                               key=lambda c: (-abs(c.rating_delta), c.id))
        star_movers = sorted((c for c in changes if c.stars_delta),
                             key=lambda c: (-abs(c.stars_delta or 0), c.id))
        return SnapshotDiff(
            from_snapshot=from_date, to_snapshot=to_date, addons_from=len(old), addons_to=len(new),
            added_count=len(added), removed_count=len(removed), updated_count=len(updated),
            added=added[:limit], removed=removed[:limit], updated=updated[:limit],
            rating_movers=rating_movers[:limit], star_movers=star_movers[:limit],
        )

    def _all_cards(self, snapshot: date) -> dict[int, AddonCard]:
        page = self._repository.find(AddonQuery(limit=None), snapshot)
        return {card.id: card for card in page.items}
