from abc import ABC, abstractmethod
from datetime import date
from typing import Protocol, runtime_checkable

from anki_addons_mcp.domain.models import (
    AddonCard,
    AddonDetails,
    AddonHistoryPoint,
    Aggregation,
    GroupField,
    Page,
    SnapshotInfo,
    SqlResult,
    TextKind,
)
from anki_addons_mcp.domain.query import AddonQuery


class AddonRepository(ABC):
    @abstractmethod
    def list_snapshots(self) -> list[SnapshotInfo]: ...

    @abstractmethod
    def get_addon(self, addon_id: int, snapshot: date | None = None) -> AddonDetails | None: ...

    @abstractmethod
    def get_addons(self, addon_ids: list[int], snapshot: date | None = None) -> list[AddonDetails]: ...

    @abstractmethod
    def find(self, query: AddonQuery, snapshot: date | None = None) -> Page[AddonCard]: ...

    @abstractmethod
    def get_text(self, addon_id: int, kind: TextKind, snapshot: date | None = None) -> str | None: ...

    @abstractmethod
    def get_history(
        self, addon_id: int, from_: date | None = None, to: date | None = None
    ) -> list[AddonHistoryPoint]: ...

    @abstractmethod
    def get_aggregation(self, snapshot: date | None = None) -> Aggregation: ...

    @abstractmethod
    def group_counts(self, field: GroupField, snapshot: date | None = None) -> dict[str, int]: ...

    @abstractmethod
    def get_documentation(self) -> str: ...


@runtime_checkable
class SqlQueryable(Protocol):
    def sql_schema(self) -> str: ...

    def execute_readonly(
        self, sql: str, snapshot: date | None, max_rows: int, timeout_seconds: float
    ) -> SqlResult: ...


@runtime_checkable
class Refreshable(Protocol):
    def warm_up(self) -> None: ...

    def refresh(self) -> bool: ...
