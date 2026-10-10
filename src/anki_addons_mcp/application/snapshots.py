from datetime import date

from anki_addons_mcp.domain.errors import InvalidQuery, SnapshotNotFound
from anki_addons_mcp.domain.models import SnapshotInfo
from anki_addons_mcp.domain.ports import AddonRepository

LATEST = "latest"


def parse_snapshot(value: str | None) -> date | None:
    if value is None or value.strip().lower() in ("", LATEST):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as e:
        raise InvalidQuery(f"Snapshot must be 'latest' or a YYYY-MM-DD date, got '{value}'") from e


class SnapshotService:
    def __init__(self, repository: AddonRepository):
        self._repository = repository

    def list(self) -> list[SnapshotInfo]:
        return self._repository.list_snapshots()

    def get(self, snapshot: date | None) -> SnapshotInfo:
        snapshots = self.list()
        for info in snapshots:
            if (snapshot is None and info.latest) or info.date == snapshot:
                return info
        raise SnapshotNotFound(snapshot or LATEST)

    def resolve(self, snapshot: date | None) -> date:
        return self.get(snapshot).date

    def previous(self, snapshot: date) -> date | None:
        earlier = [info.date for info in self.list() if info.date < snapshot]
        return max(earlier) if earlier else None
