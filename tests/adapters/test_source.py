from pathlib import Path

from anki_addons_mcp.adapters.hf_parquet.repository import DuckDbAddonRepository
from anki_addons_mcp.adapters.hf_parquet.source import HfDatasetSource, LocalDatasetSource
from tests.fixtures.dataset import KANJI


def test_hf_package_url_is_pinned_to_the_revision() -> None:
    source = HfDatasetSource.__new__(HfDatasetSource)
    source._repo_id, source._sha = "owner/dataset", "abc123"
    url = source.package_url(1001, "0-2021-03-01-aaaaaaaaaaaa.ankiaddon")
    assert url is not None
    assert url.endswith("/datasets/owner/dataset/resolve/abc123/packages/1001/0-2021-03-01-aaaaaaaaaaaa.ankiaddon")


def test_local_dataset_has_no_package_url(dataset_dir: Path, duckdb_repository: DuckDbAddonRepository) -> None:
    assert LocalDatasetSource(dataset_dir).package_url(1001, "file.ankiaddon") is None
    assert {p.download_url for p in duckdb_repository.list_packages(KANJI)} == {None}
