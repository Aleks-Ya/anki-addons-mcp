import logging
import threading
from collections.abc import Callable

from mcp.server.mcpserver import MCPServer

from anki_addons_mcp.adapters.hf_parquet.repository import DuckDbAddonRepository
from anki_addons_mcp.adapters.hf_parquet.source import DatasetSource, HfDatasetSource, LocalDatasetSource
from anki_addons_mcp.application.maintenance import MaintenanceThresholds
from anki_addons_mcp.application.services import Services, SqlLimits, build_services
from anki_addons_mcp.config import Settings
from anki_addons_mcp.domain.ports import AddonRepository, Refreshable
from anki_addons_mcp.interface.mcp.server import build_server

log = logging.getLogger(__name__)


def _source_factory(settings: Settings) -> Callable[[], DatasetSource]:
    if settings.backend == "local_parquet":
        if settings.data_dir is None:
            raise ValueError("ANKI_MCP_DATA_DIR (--data-dir) is required for the local_parquet backend")
        data_dir = settings.data_dir
        return lambda: LocalDatasetSource(data_dir)
    return lambda: HfDatasetSource(settings.hf_repo_id, settings.hf_revision, settings.cache_dir, settings.hf_token)


def create_repository(settings: Settings) -> AddonRepository:
    match settings.backend:
        case "hf_parquet" | "local_parquet":
            return DuckDbAddonRepository(_source_factory(settings))
    raise ValueError(f"Unknown backend: {settings.backend}")


def create_services(settings: Settings, repository: AddonRepository | None = None) -> Services:
    return build_services(
        repository or create_repository(settings),
        thresholds=MaintenanceThresholds(active_days=settings.maintenance_active_days,
                                         stale_days=settings.maintenance_stale_days),
        sql_enabled=settings.sql_enabled,
        sql_limits=SqlLimits(max_rows=settings.sql_max_rows, timeout_seconds=settings.sql_timeout_seconds),
    )


def start_background_tasks(repository: AddonRepository, settings: Settings) -> None:
    if not isinstance(repository, Refreshable):
        return
    stop = threading.Event()

    def run() -> None:
        if settings.warm_up:
            try:
                repository.warm_up()
                log.info("Dataset loaded")
            except Exception:
                log.exception("Warm-up failed; data will be loaded on first request")
        interval = settings.refresh_interval_seconds
        while interval > 0 and not stop.wait(interval):
            try:
                repository.refresh()
            except Exception:
                log.exception("Dataset refresh failed")

    threading.Thread(target=run, name="dataset-refresh", daemon=True).start()


def create_app(settings: Settings) -> tuple[MCPServer, Services]:
    services = create_services(settings)
    start_background_tasks(services.repository, settings)
    return build_server(services, settings.log_level), services
