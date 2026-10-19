---
name: release
description: Bump the version and release it — suggest the next major/minor/patch version and bump to the chosen one (tagging the release and moving to the next .dev0), push the release tag, create a GitHub release with auto-generated notes, wait for the PyPI publish workflow, and verify the released version with uvx. Use when the user says "release", "/release", or asks to bump the version or create/publish the GitHub release.
allowed-tools: Bash(git *) Bash(gh *) Bash(uv *) Bash(uvx *) Bash(curl *) Bash(python3 *) Bash(grep *)
disable-model-invocation: true
---

# release

Automate README-DEV.md → "Release a new version" → **steps 2–8** (bump, push, GitHub release,
publish, verify). It is the natural follow-on to `/push` (README step 1), which should have left `main`
pushed with green CI and a clean SonarCloud report.

Suggest the next major/minor/patch version and bump to the one the user picks, push the release tag,
create the GitHub release (which triggers PyPI publishing), watch the publish workflow to green, and
verify the released version is live. Work through the steps in order; stop and report if a step can't be
completed.

## 1. Preconditions

Confirm the current branch is `main`:

```bash
git rev-parse --abbrev-ref HEAD
```

If not on `main`, stop and ask the user before releasing.

Confirm a clean working tree — `bump-my-version` refuses to bump a dirty tree:

```bash
git status --porcelain
```

If there is **any** output, stop and report the uncommitted files. Do not commit on the user's behalf.

Read the current version — it must be a development version (`X.Y.Z.dev0`):

```bash
uv run bump-my-version show current_version
```

If it has no `.dev0` suffix, the tree is already on a release version — stop and report.

Check for an unfinished previous release — the latest `v*` tag reachable from HEAD and whether it was
released on GitHub:

```bash
git describe --tags --abbrev=0 --match 'v*'
gh release view <latest-tag>
```

If `gh release view` fails (the tag exists but has no GitHub release), an earlier run bumped and tagged
but didn't finish. Ask the user whether to release that existing tag — if yes, use it as the release tag
and skip to step 3; otherwise stop and report.

## 2. Choose and bump the version

Compute three candidates from the last release (the latest `v*` tag without the `v`; if there is no tag
yet, the current version without `.dev0`). For last release `0.3.0`:

| Bump  | Rule                         | Example |
|-------|------------------------------|---------|
| major | `MAJOR+1.0.0`                | `1.0.0` |
| minor | `MAJOR.MINOR+1.0`            | `0.4.0` |
| patch | `MAJOR.MINOR.PATCH+1`        | `0.3.1` |

Ask the user to pick one with `AskUserQuestion` (single-select, three options). Put **minor** first and
mark it "(Recommended)" when it equals the current dev version without `.dev0` (the version already in
progress). Each option's description shows the change, e.g. `0.4.0.dev0 → 0.4.0 (tag v0.4.0)`. Never
bump without the user's choice.

Bump to the chosen release version and tag it (one commit + tag `v<version>`):

```bash
uv run bump-my-version bump --new-version <version> --tag
```

`--new-version` sets the exact version, so it works for every choice — including a patch release below
the in-progress dev version.

Move the tree to the next development version (`<version>` → `MAJOR.MINOR+1.0.dev0`, one commit):

```bash
uv run bump-my-version bump minor
```

Verify both commits and the tag:

```bash
git log --oneline -2
git describe --tags --abbrev=0 --match 'v*'
```

The tag must be `v<version>`; it is the release tag for the remaining steps. If a bump fails, stop and
report — do not reset or delete commits/tags on your own initiative.

## 3. Push branch and tags

```bash
git push origin HEAD --tags
```

If the push is rejected (e.g. remote is ahead), **stop and report**. Do not force-push on your own
initiative.

## 4. Create the GitHub release

```bash
gh release create <tag> --title <tag> --generate-notes
```

`--generate-notes` auto-builds the release notes from merged PRs/commits since the previous release.
Print the resulting release URL. Creating (publishing) the release is what triggers the PyPI publish
workflow.

## 5. Wait for the PyPI publish workflow

The published release triggers the **Publish to PyPI** workflow (`.github/workflows/publish.yml`), which
builds the distributions and publishes to PyPI via Trusted Publishing. Find the run and watch it to
completion:

```bash
gh run list --workflow publish.yml --limit 5
gh run watch <run-id> --exit-status
```

- `gh run watch --exit-status` exits non-zero if the run fails.
- If it **succeeds**, continue to step 6.
- If it **fails**, inspect and diagnose:

```bash
gh run view <run-id> --log-failed
```

Report the real cause clearly (build/`twine check` failure, OIDC/Trusted-Publisher misconfig, etc.). **Do
not retry blindly** — republishing the same version to PyPI will fail, so the fix usually involves the
user (e.g. correcting the publisher config), not re-running the job.

## 6. Verify the published version

A green publish workflow means PyPI *accepted* the upload, but the index/CDN needs a moment to expose it.
Verify in two phases — don't rely on `uvx --refresh` alone, which can silently resolve to the previous
version if the index hasn't caught up.

`<version>` = the tag without the leading `v` (tag `v1.8.0` → `1.8.0`).

### 6a. Confirm the version is available on the PyPI index

The version-specific JSON endpoint returns `200` only once that exact version is published. Poll it,
retrying a few times with a short sleep between attempts until it returns `200` (propagation typically
takes seconds to a couple of minutes):

```bash
curl -sf -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/anki-addons-mcp/<version>/json
```

If it never appears within a sensible window, report that the publish workflow was green but the version
isn't visible on PyPI yet, and stop.

### 6b. Pull it to this machine and verify end-to-end

Only after 6a returns `200`, run the README's check so the just-published package is actually fetched and
executed here. First make sure a satisfying interpreter exists locally — derive it from the release's own
`requires-python` rather than assuming, and install it if missing (`uv python install` is a no-op when it
is already there):

```bash
REQ=$(curl -s https://pypi.org/pypi/anki-addons-mcp/<version>/json \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["info"]["requires_python"] or "")')
PYMIN=$(printf '%s' "$REQ" | grep -oE '[0-9]+\.[0-9]+' | head -1)
echo "requires-python: $REQ (installing $PYMIN)"
uv python install "$PYMIN"
```

Then run the pinned check, retrying every 15 s for up to ~3 min. The JSON endpoint in 6a can return `200`
before the simple index that uv installs from lists the new files, so the first attempts may fail on
propagation alone. Run the retry as a single `python3` command (no shell `for`/`sleep` loop), with a Bash
timeout of at least 300000 ms:

```bash
python3 -c '
import subprocess, sys, time
version, pymin = sys.argv[1], sys.argv[2]
cmd = ["uvx", "--refresh", "-p", pymin, f"anki-addons-mcp@{version}", "--version"]
for attempt in range(1, 13):
    run = subprocess.run(cmd, capture_output=True, text=True)
    lines = [line.strip() for line in (run.stdout + run.stderr).splitlines()]
    last = lines[-1] if lines else ""
    print(time.strftime("%H:%M:%S"), f"attempt {attempt}:", last or "(no output)", flush=True)
    if version in lines:
        break
    time.sleep(15)
else:
    sys.exit(f"FAILED: uvx did not run {version}")
' "<version>" "$PYMIN"
```

Only if every attempt fails is the release broken: report the last output and stop.

`--refresh` bypasses uvx's cache so it fetches the newly published version; `@<version>` pins the release
and `-p "$PYMIN"` picks an interpreter that release's `requires-python` accepts — without them, uv picks
an interpreter first and silently falls back to an older release. Requiring a line that is exactly `<version>` makes the app's own
`--version` output the pass condition, so the step cannot succeed on the wrong version.

### 6c. Check the bare command users actually type

The pinned check proves the release works; it does *not* prove a plain `uvx anki-addons-mcp` resolves
to it. uvx selects an interpreter first and then the newest release compatible with it, so after a
`requires-python` bump a machine whose default interpreter is older silently keeps running the previous
version:

```bash
uvx anki-addons-mcp --version 2>&1 | tail -1
```

This step is **informational — never fail the release on it.** If the reported version is not
`<version>`, say so explicitly in the final report, name the cause (compare the release's
`requires-python` against the Python uvx chose, shown by `uvx --from anki-addons-mcp python --version`), and give the workaround
(`uvx -p <PYMIN> anki-addons-mcp --version`, or pin `anki-addons-mcp@<version>`). A `requires-python`
bump makes this expected, not a defect — but it must be surfaced, not discovered later.

## Done

Report the final state: the version bump (old dev → release → next dev), the pushed tag, the release URL, the publish-workflow result, the verified pinned
`uvx` version, and what the bare `uvx anki-addons-mcp --version` resolves to (with the cause if it is not
the new release) — or the first step that failed and why.
