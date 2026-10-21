import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from anki_addons_mcp.domain.errors import SnapshotNotFound
from anki_addons_mcp.domain.models import SnapshotInfo

log = logging.getLogger(__name__)

LATEST_DIR = "latest"
HISTORY_DIR = "history"
DATA_FILE = "parquet/data.parquet"
TAGS_FILE = "parquet/tags.parquet"
ANKI_VERSIONS_FILE = "parquet/anki_versions.parquet"
METADATA_FILE = "metadata.json"
README_FILE = "README.md"


class DatasetSource(Protocol):
    @property
    def revision(self) -> str: ...

    def head_revision(self) -> str: ...

    def latest_date(self) -> date: ...

    def snapshot_dates(self) -> list[date]: ...

    def snapshot_info(self, snapshot: date) -> SnapshotInfo: ...

    def data_file(self, snapshot: date) -> Path: ...

    def tags_file(self, snapshot: date) -> Path: ...

    def anki_versions_file(self, snapshot: date) -> Path | None:
        """None for a snapshot collected before the dataset published the table."""
        ...

    def readme(self) -> str | None: ...


def _info(raw: dict[str, Any], snapshot: date, latest: bool) -> SnapshotInfo:
    generated = raw.get("report_generation_date")
    return SnapshotInfo(
        date=snapshot,
        latest=latest,
        report_generation_date=datetime.fromisoformat(generated) if generated else None,
        script_version=raw.get("script_version"),
    )


def _parse_dir_date(name: str) -> date | None:
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


class _BaseSource:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: date | None = None
        self._infos: dict[date, SnapshotInfo] = {}

    def _read_json(self, relative: str) -> dict[str, Any]:
        raise NotImplementedError

    def _history_names(self) -> list[str]:
        raise NotImplementedError

    def latest_date(self) -> date:
        with self._lock:
            if self._latest is None:
                raw = self._read_json(f"{LATEST_DIR}/{METADATA_FILE}")
                self._latest = date.fromisoformat(raw["data_collection_date"])
            return self._latest

    def snapshot_dates(self) -> list[date]:
        dates = {d for d in (_parse_dir_date(n) for n in self._history_names()) if d}
        dates.add(self.latest_date())
        return sorted(dates)

    def snapshot_info(self, snapshot: date) -> SnapshotInfo:
        latest = self.latest_date()
        if snapshot not in self.snapshot_dates():
            raise SnapshotNotFound(snapshot)
        cached = self._infos.get(snapshot)
        if cached is not None:
            return cached
        folder = LATEST_DIR if snapshot == latest else f"{HISTORY_DIR}/{snapshot.isoformat()}"
        try:
            raw = self._read_json(f"{folder}/{METADATA_FILE}")
        except Exception:
            log.warning("Cannot read metadata for snapshot %s", snapshot, exc_info=True)
            raw = {}
        info = _info(raw, snapshot, snapshot == latest)
        self._infos[snapshot] = info
        return info

    def _snapshot_relative(self, snapshot: date, file: str) -> str:
        if snapshot == self.latest_date():
            return f"{LATEST_DIR}/{file}"
        if snapshot not in self.snapshot_dates():
            raise SnapshotNotFound(snapshot)
        return f"{HISTORY_DIR}/{snapshot.isoformat()}/{file}"


class LocalDatasetSource(_BaseSource):
    def __init__(self, root: Path):
        super().__init__()
        self._root = root
        if not (root / LATEST_DIR / METADATA_FILE).is_file():
            raise FileNotFoundError(f"Not a dataset directory (missing {LATEST_DIR}/{METADATA_FILE}): {root}")

    @property
    def revision(self) -> str:
        return self.head_revision()

    def head_revision(self) -> str:
        return str((self._root / LATEST_DIR / METADATA_FILE).stat().st_mtime_ns)

    def _read_json(self, relative: str) -> dict[str, Any]:
        result: dict[str, Any] = json.loads((self._root / relative).read_text())
        return result

    def _history_names(self) -> list[str]:
        history = self._root / HISTORY_DIR
        return [p.name for p in history.iterdir() if p.is_dir()] if history.is_dir() else []

    def data_file(self, snapshot: date) -> Path:
        return self._root / self._snapshot_relative(snapshot, DATA_FILE)

    def tags_file(self, snapshot: date) -> Path:
        return self._root / self._snapshot_relative(snapshot, TAGS_FILE)

    def anki_versions_file(self, snapshot: date) -> Path | None:
        path = self._root / self._snapshot_relative(snapshot, ANKI_VERSIONS_FILE)
        return path if path.is_file() else None

    def readme(self) -> str | None:
        path = self._root / README_FILE
        return path.read_text() if path.is_file() else None


class HfDatasetSource(_BaseSource):
    def __init__(self, repo_id: str, revision: str = "main", cache_dir: Path | None = None,
                 token: str | None = None):
        from huggingface_hub import HfApi

        super().__init__()
        self._repo_id = repo_id
        self._requested_revision = revision
        self._cache_dir = cache_dir
        self._token = token
        self._api = HfApi(token=token)
        self._sha = self.head_revision()
        self._history: list[str] | None = None
        log.info("Using dataset %s at revision %s", repo_id, self._sha)

    @property
    def revision(self) -> str:
        return self._sha

    def head_revision(self) -> str:
        info = self._api.dataset_info(self._repo_id, revision=self._requested_revision)
        return info.sha or self._requested_revision

    def _download(self, relative: str) -> Path:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(self._repo_id, relative, repo_type="dataset", revision=self._sha,
                               cache_dir=self._cache_dir, token=self._token)
        return Path(path)

    def _read_json(self, relative: str) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self._download(relative).read_text())
        return result

    def _history_names(self) -> list[str]:
        from huggingface_hub import RepoFolder

        with self._lock:
            if self._history is None:
                entries = self._api.list_repo_tree(self._repo_id, path_in_repo=HISTORY_DIR, repo_type="dataset",
                                                   revision=self._sha)
                self._history = [e.path.rsplit("/", 1)[-1] for e in entries if isinstance(e, RepoFolder)]
            return self._history

    def data_file(self, snapshot: date) -> Path:
        relative = self._snapshot_relative(snapshot, DATA_FILE)
        log.info("Fetching %s", relative)
        return self._download(relative)

    def tags_file(self, snapshot: date) -> Path:
        return self._download(self._snapshot_relative(snapshot, TAGS_FILE))

    def anki_versions_file(self, snapshot: date) -> Path | None:
        from huggingface_hub.errors import EntryNotFoundError

        relative = self._snapshot_relative(snapshot, ANKI_VERSIONS_FILE)
        try:
            return self._download(relative)
        except EntryNotFoundError:
            log.info("Snapshot %s has no %s", snapshot, ANKI_VERSIONS_FILE)
            return None

    def readme(self) -> str | None:
        try:
            return self._download(README_FILE).read_text()
        except Exception:
            log.warning("Cannot fetch dataset card", exc_info=True)
            return None
