from dataclasses import dataclass

from anki_addons_mcp.application.catalog import CatalogService
from anki_addons_mcp.application.compatibility import CompatibilityService
from anki_addons_mcp.application.history import HistoryService
from anki_addons_mcp.application.maintenance import MaintenanceService, MaintenanceThresholds
from anki_addons_mcp.application.similarity import SimilarityService
from anki_addons_mcp.application.snapshots import SnapshotService
from anki_addons_mcp.application.stats import StatsService
from anki_addons_mcp.domain.ports import AddonRepository, SqlQueryable


@dataclass(frozen=True)
class SqlLimits:
    max_rows: int = 200
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class Services:
    repository: AddonRepository
    snapshots: SnapshotService
    catalog: CatalogService
    compatibility: CompatibilityService
    maintenance: MaintenanceService
    history: HistoryService
    similarity: SimilarityService
    stats: StatsService
    sql: SqlQueryable | None
    sql_limits: SqlLimits


def build_services(repository: AddonRepository, thresholds: MaintenanceThresholds | None = None,
                   sql_enabled: bool = True, sql_limits: SqlLimits | None = None) -> Services:
    snapshots = SnapshotService(repository)
    catalog = CatalogService(repository)
    sql = repository if sql_enabled and isinstance(repository, SqlQueryable) else None
    return Services(
        repository=repository,
        snapshots=snapshots,
        catalog=catalog,
        compatibility=CompatibilityService(catalog),
        maintenance=MaintenanceService(catalog, snapshots, thresholds or MaintenanceThresholds()),
        history=HistoryService(repository, snapshots),
        similarity=SimilarityService(repository, catalog),
        stats=StatsService(repository, snapshots),
        sql=sql,
        sql_limits=sql_limits or SqlLimits(),
    )
