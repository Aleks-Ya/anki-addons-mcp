"""Where the server's dataset pin stands: the baseline tag, newer tags, branch heads and local copies.

Usage: uv run python .claude/skills/update-dataset/scripts/versions.py [--target TAG]
"""
import argparse
import json

from _common import (
    DATASET_REPO,
    LOCAL_BUNDLE,
    REPO_ID,
    baseline_revision,
    has_local_tag,
    parse_tag,
    read_metadata,
    revision_sha,
    section,
    version_tags,
)
from huggingface_hub import HfApi


def _describe(api: HfApi, revision: str) -> dict[str, str]:
    metadata = read_metadata(revision)
    return {"revision": revision, "sha": revision_sha(api, revision),
            **{k: str(v) for k, v in metadata.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", help="Target tag; default: the newest version tag")
    args = parser.parse_args()
    api = HfApi()

    baseline = baseline_revision()
    tags = version_tags(api)
    base_tag = parse_tag(baseline)
    newer = [t for t in tags if base_tag is None or t > base_tag]
    target = args.target or (tags[-1].name if tags else baseline)

    section("Baseline (hf_revision default in src/anki_addons_mcp/config.py)")
    if base_tag is None:
        print(f"WARNING: {baseline} is not a version tag vMAJOR.MINOR-<date>")
    base = _describe(api, baseline)
    print(json.dumps(base, indent=2))

    section("Version tags on HuggingFace, oldest first (backup-* ignored)")
    for tag in tags:
        mark = " <- baseline" if tag.name == baseline else (" (newer)" if tag in newer else "")
        print(f"{tag.name}  dataset_version {tag.dataset_version}{mark}")
    print(f"Newer than the baseline: {', '.join(t.name for t in newer) or 'none'}")

    section("Target")
    current = base if target == baseline else _describe(api, target)
    print(json.dumps(current, indent=2))
    if target == baseline:
        print("The target is the baseline: only the coverage audit and the dataset checks can produce work.")
    elif base.get("dataset_version") != current.get("dataset_version"):
        old, new = base.get("dataset_version", "?"), current.get("dataset_version", "?")
        kind = "MAJOR (breaking changes expected)" if old.split(".")[0] != new.split(".")[0] else "MINOR (additive)"
        print(f"dataset_version {old} -> {new}: {kind}")
    else:
        print("Same dataset_version: new snapshots or regenerated history, no schema change expected.")

    section("Branch heads")
    for branch in ("main", f"v{current.get('dataset_version', '1').split('.')[0]}"):
        try:
            sha = revision_sha(api, branch)
        except Exception as error:  # noqa: BLE001 - report and go on
            print(f"{branch}: not found ({type(error).__name__})")
            continue
        state = "at the target" if sha == current["sha"] else "AHEAD of the target or diverged: a newer upload has no tag"
        print(f"{branch}: {sha[:12]} {state}")

    section("Dataset repo (read-only)")
    print(f"Path: {DATASET_REPO} ({'present' if DATASET_REPO.is_dir() else 'missing: dataset_docs.py uses gh api'})")
    for label, meta in (("baseline", base), ("target", current)):
        script = meta.get("script_version")
        if script:
            print(f"{label} script tag v{script}: {'local' if has_local_tag(script) else 'not local, use gh api'}")

    section("Local bundle")
    local = LOCAL_BUNDLE / "latest" / "metadata.json"
    if not local.is_file():
        print(f"{local}: missing; live_check.py reads the target from HuggingFace")
    else:
        bundle = json.loads(local.read_text())
        keys = ("dataset_version", "script_version", "report_generation_date")
        same = all(str(bundle.get(k)) == current.get(k) for k in keys)
        print(json.dumps(bundle, indent=2))
        print(f"MATCHES the target: live_check.py --data-dir {LOCAL_BUNDLE}" if same
              else "Differs from the target: live_check.py must read HuggingFace (slow) "
                   "or the bundle is a newer, not yet uploaded build")
    print(f"\nDataset: https://huggingface.co/datasets/{REPO_ID}/tree/{target}")


if __name__ == "__main__":
    main()
