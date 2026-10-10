from datetime import date


class DomainError(Exception):
    pass


class AddonNotFound(DomainError):
    def __init__(self, addon_id: int, snapshot: date | None = None):
        where = f"snapshot {snapshot.isoformat()}" if snapshot else "the latest snapshot"
        super().__init__(f"Addon {addon_id} not found in {where}")
        self.addon_id = addon_id


class SnapshotNotFound(DomainError):
    def __init__(self, snapshot: object):
        super().__init__(f"Snapshot {snapshot} not found. Call list_snapshots to see available dates.")


class InvalidQuery(DomainError):
    pass


class DataSourceUnavailable(DomainError):
    pass
