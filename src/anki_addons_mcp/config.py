from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANKI_MCP_", env_file=".env", extra="ignore")

    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    allowed_hosts: list[str] = []

    backend: Literal["hf_parquet", "local_parquet"] = "hf_parquet"
    hf_repo_id: str = "Ya-Alex/anki-addons"
    hf_revision: str = "main"
    hf_token: str | None = None
    data_dir: Path | None = None
    cache_dir: Path | None = None
    refresh_interval_seconds: int = 3600
    warm_up: bool = True

    sql_enabled: bool = True
    sql_max_rows: int = 200
    sql_timeout_seconds: float = 10.0

    maintenance_active_days: int = 180
    maintenance_stale_days: int = 730

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
