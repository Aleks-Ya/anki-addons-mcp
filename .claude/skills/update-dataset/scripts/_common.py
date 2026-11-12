"""Shared helpers of the update-dataset scripts: dataset refs, metadata and the local paths."""
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "Ya-Alex/anki-addons"
GITHUB_REPO = "Aleks-Ya/anki-addons-dataset"
MCP_ROOT = Path(__file__).resolve().parents[4]
DATASET_REPO = MCP_ROOT.parent / "anki-addons-dataset"
LOCAL_BUNDLE = Path.home() / "anki-addons-dataset" / "bundle"

_TAG = re.compile(r"^v(\d+)\.(\d+)-(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")


@dataclass(frozen=True, order=True)
class VersionTag:
    """A frozen dataset tag vMAJOR.MINOR-<date>[-N]; a re-upload of the same snapshot adds -N."""
    major: int
    minor: int
    date: str
    upload: int
    name: str

    @property
    def dataset_version(self) -> str:
        return f"{self.major}.{self.minor}"


def parse_tag(name: str) -> VersionTag | None:
    match = _TAG.match(name)
    if not match:
        return None
    major, minor, day, upload = match.groups()
    return VersionTag(int(major), int(minor), day, int(upload or 1), name)


def version_tags(api: HfApi) -> list[VersionTag]:
    refs = api.list_repo_refs(REPO_ID, repo_type="dataset")
    return sorted(t for ref in refs.tags if (t := parse_tag(ref.name)) is not None)


def baseline_revision() -> str:
    """The revision the server is pinned to: the hf_revision default, not overridden by env or .env."""
    from anki_addons_mcp.config import Settings

    default = Settings.model_fields["hf_revision"].default
    assert isinstance(default, str)
    return default


def revision_sha(api: HfApi, revision: str) -> str:
    sha = api.dataset_info(REPO_ID, revision=revision).sha
    assert sha is not None
    return sha


def read_metadata(revision: str, folder: str = "latest") -> dict[str, Any]:
    path = hf_hub_download(REPO_ID, f"{folder}/metadata.json", repo_type="dataset", revision=revision)
    result: dict[str, Any] = json.loads(Path(path).read_text())
    return result


def dataset_repo_file(script_version: str, path: str) -> str | None:
    """A file of the dataset repo at tag v<script_version>: local read-only git first, then the GitHub API."""
    tag = f"v{script_version}"
    if DATASET_REPO.is_dir():
        run = subprocess.run(["git", "-C", str(DATASET_REPO), "show", f"{tag}:{path}"],
                             check=False, capture_output=True, text=True)
        if run.returncode == 0:
            return run.stdout
    run = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw",
                          f"repos/{GITHUB_REPO}/contents/{path}?ref={tag}"], check=False, capture_output=True, text=True)
    return run.stdout if run.returncode == 0 else None


def has_local_tag(script_version: str) -> bool:
    if not DATASET_REPO.is_dir():
        return False
    run = subprocess.run(["git", "-C", str(DATASET_REPO), "rev-parse", "-q", "--verify", f"v{script_version}^{{commit}}"],
                         check=False, capture_output=True, text=True)
    return run.returncode == 0


def section(title: str) -> None:
    print(f"\n## {title}")
