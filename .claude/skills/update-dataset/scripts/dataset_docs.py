"""What the dataset repo says changed between two dataset revisions: changelog, docs diff and commits.

The script versions in the revisions' metadata.json name the dataset repo tags (v<script_version>). Reads the local
dataset repo with read-only git only (never fetch); falls back to the GitHub API when a tag is not local.

Usage: uv run python .claude/skills/update-dataset/scripts/dataset_docs.py --base REV --target REV
"""
import argparse
import json
import re
import subprocess

from _common import DATASET_REPO, GITHUB_REPO, dataset_repo_file, has_local_tag, read_metadata, section

DOC_PATHS = ["docs/dataset", "src/anki_addons_dataset/huggingface/README.md"]
CHANGELOG = "docs/dataset/changelog.md"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def changelog_entries(text: str, after: str, up_to: str) -> list[str]:
    """The '## MAJOR.MINOR' sections with after < version <= up_to."""
    entries = re.split(r"(?m)^(?=## )", text)
    picked = []
    for entry in entries:
        match = re.match(r"## (\d+(?:\.\d+)*)", entry)
        if match and _version_key(after) < _version_key(match.group(1)) <= _version_key(up_to):
            picked.append(entry.strip())
    return picked


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(DATASET_REPO), *args], capture_output=True, text=True, check=True).stdout


def _gh_compare(base: str, target: str) -> dict[str, object]:
    run = subprocess.run(["gh", "api", f"repos/{GITHUB_REPO}/compare/{base}...{target}"],
                         capture_output=True, text=True, check=True)
    result: dict[str, object] = json.loads(run.stdout)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Baseline HF revision")
    parser.add_argument("--target", required=True, help="Target HF revision")
    args = parser.parse_args()

    base_meta, target_meta = read_metadata(args.base), read_metadata(args.target)
    base_script, target_script = base_meta.get("script_version"), target_meta.get("script_version")
    base_version = str(base_meta.get("dataset_version", "0.0"))
    target_version = str(target_meta.get("dataset_version", "0.0"))
    print(f"Script {base_script} -> {target_script}, dataset_version "
          f"{base_meta.get('dataset_version', '(none: before versioning)')} -> {target_version}")
    if not base_script or not target_script:
        raise SystemExit("A metadata.json has no script_version, so the dataset repo tags are unknown")
    base_tag, target_tag = f"v{base_script}", f"v{target_script}"

    section(f"Changelog entries after {base_version} up to {target_version} ({CHANGELOG} at {target_tag})")
    changelog = dataset_repo_file(target_script, CHANGELOG)
    if changelog is None:
        print(f"ISSUE: {CHANGELOG} is missing at {target_tag}")
    else:
        entries = changelog_entries(changelog, base_version, target_version)
        print("\n\n".join(entries) if entries else "(none)")
        if base_version != target_version and not re.search(rf"(?m)^## {re.escape(target_version)}\b", changelog):
            print(f"ISSUE: the changelog has no entry for {target_version}")

    local = has_local_tag(base_script) and has_local_tag(target_script)
    section(f"Commits {base_tag}..{target_tag}")
    if base_tag == target_tag:
        print("(same tag)")
    elif local:
        print(_git("log", "--format=%h %ad %s", "--date=short", f"{base_tag}..{target_tag}") or "(none)")
    else:
        compare = _gh_compare(base_tag, target_tag)
        for commit in compare.get("commits", []):  # type: ignore[attr-defined]
            print(commit["sha"][:7], commit["commit"]["message"].splitlines()[0])

    section(f"Docs diff {base_tag}..{target_tag} ({', '.join(DOC_PATHS)})")
    if base_tag == target_tag:
        print("(same tag)")
    elif local:
        print(_git("diff", f"{base_tag}..{target_tag}", "--", *DOC_PATHS) or "(no changes)")
    else:
        compare = _gh_compare(base_tag, target_tag)
        for file in compare.get("files", []):  # type: ignore[attr-defined]
            if any(file["filename"].startswith(p) for p in DOC_PATHS):
                print(f"--- {file['filename']}\n{file.get('patch', '(binary or too large)')}")

    section(f"Unreleased commits after {target_tag} (a heads-up for the next dataset version)")
    if DATASET_REPO.is_dir():
        print(_git("log", "--format=%h %ad %s", "--date=short", f"{target_tag}..main") or "(none)")
        print("(local main; it may be behind GitHub, the skill never fetches)")
    else:
        compare = _gh_compare(target_tag, "main")
        for commit in compare.get("commits", []):  # type: ignore[attr-defined]
            print(commit["sha"][:7], commit["commit"]["message"].splitlines()[0])


if __name__ == "__main__":
    main()
