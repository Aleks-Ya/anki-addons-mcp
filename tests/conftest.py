from pathlib import Path

import pytest

from anki_addons_mcp.adapters.hf_parquet.repository import DuckDbAddonRepository
from anki_addons_mcp.adapters.hf_parquet.source import LocalDatasetSource
from anki_addons_mcp.adapters.memory.repository import InMemoryAddonRepository
from anki_addons_mcp.domain.ports import AddonRepository
from tests.fixtures.dataset import domain_infos, domain_snapshots, domain_tags, write_dataset


@pytest.fixture(scope="session")
def dataset_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_dataset(tmp_path_factory.mktemp("dataset"))


@pytest.fixture(scope="session")
def memory_repository() -> InMemoryAddonRepository:
    return InMemoryAddonRepository(domain_snapshots(), domain_infos(), "# Test dataset card\n", domain_tags())


@pytest.fixture(scope="session")
def duckdb_repository(dataset_dir: Path) -> DuckDbAddonRepository:
    return DuckDbAddonRepository(lambda: LocalDatasetSource(dataset_dir))


@pytest.fixture(params=["memory", "duckdb"])
def repository(request: pytest.FixtureRequest) -> AddonRepository:
    return request.getfixturevalue(f"{request.param}_repository")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
