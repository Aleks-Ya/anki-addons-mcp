from datetime import date

from pydantic import BaseModel

from anki_addons_mcp.application.snapshots import SnapshotService
from anki_addons_mcp.domain.models import Aggregation, GroupField
from anki_addons_mcp.domain.ports import AddonRepository


class GroupCounts(BaseModel):
    field: GroupField
    distinct_values: int
    counts: dict[str, int]


class Statistics(BaseModel):
    snapshot: date
    aggregation: Aggregation
    groups: list[GroupCounts]


class StatsService:
    def __init__(self, repository: AddonRepository, snapshots: SnapshotService):
        self._repository = repository
        self._snapshots = snapshots

    def aggregation(self, snapshot: date | None = None) -> Aggregation:
        return self._repository.get_aggregation(snapshot)

    def statistics(self, snapshot: date | None = None, group_by: list[GroupField] | None = None,
                   top_values: int = 20) -> Statistics:
        resolved = self._snapshots.resolve(snapshot)
        groups = []
        for field in group_by or []:
            counts = self._repository.group_counts(field, resolved)
            ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            groups.append(GroupCounts(field=field, distinct_values=len(counts), counts=dict(ordered[:top_values])))
        return Statistics(snapshot=resolved, aggregation=self._repository.get_aggregation(resolved), groups=groups)
