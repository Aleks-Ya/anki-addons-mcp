---
name: release
description: Create the GitHub release for the just-bumped version and see it published — push the release tag, create a GitHub release with auto-generated notes, wait for the PyPI publish workflow, and verify the released version with uvx. Use when the user says "release", "/release", or asks to create/publish the GitHub release.
allowed-tools: Bash(git *) Bash(gh *) Bash(uv *) Bash(uvx *) Bash(curl *) Bash(python3 *) Bash(grep *)
disable-model-invocation: true
---

# release

Automate README-DEV.md → "Release a new version" → **steps 5–8** (push, GitHub
release, publish, verify). This runs *after* the version has been bumped (README steps 1–4, i.e.
`bump-my-version bump release --tag` created the `vX.Y.Z` tag and `bump minor` moved the tree to the
next `.dev0`). This skill does **not** bump the version — it is the natural follow-on to `/push`.

Push the release tag, create the GitHub release (which triggers PyPI publishing), watch the publish
workflow to green, and verify the released version is live. Work through the steps in order; stop and
report if a step can't be completed.

## 1. Preconditions & determine the release tag

Confirm the current branch is `main`:

```bash
git rev-parse --abbrev-ref HEAD
```

If not on `main`, stop and ask the user before releasing.

Confirm a clean working tree — the version-bump commits should already be in place:

```bash
git status --porcelain
```

If there is **any** output, stop and report the uncommitted files. Do not commit on the user's behalf.

Determine the release tag = the latest `v*` release tag reachable from HEAD:

```bash
git describe --tags --abbrev=0 --match 'v*'
```

Sanity-check it looks like a released version (`vMAJOR.MINOR.PATCH`, **no** `.dev` suffix) and show it
to the user. If it carries a `.dev` suffix, the version wasn't bumped to a release — stop and tell the
user to run README steps 1–4 first.

Guard against re-releasing an existing release:

```bash
gh release view <tag>
```

If the release already exists, stop and report — nothing to do. If you're unsure the tag matches the
bump the user just made, confirm with them before proceeding.

## 2. Push branch and tags

```bash
git push origin HEAD --tags
```

If the push is rejected (e.g. remote is ahead), **stop and report**. Do not force-push on your own
initiative.

## 3. Create the GitHub release

```bash
gh release create <tag> --title <tag> --generate-notes
```

`--generate-notes` auto-builds the release notes from merged PRs/commits since the previous release.
Print the resulting release URL. Creating (publishing) the release is what triggers the PyPI publish
workflow.

## 4. Wait for the PyPI publish workflow

The published release triggers the **Publish to PyPI** workflow (`.github/workflows/publish.yml`), which
builds the distributions and publishes to PyPI via Trusted Publishing. Find the run and watch it to
completion:

```bash
gh run list --workflow publish.yml --limit 5
gh run watch <run-id> --exit-status
```

- `gh run watch --exit-status` exits non-zero if the run fails.
- If it **succeeds**, continue to step 5.
- If it **fails**, inspect and diagnose:

```bash
gh run view <run-id> --log-failed
```

Report the real cause clearly (build/`twine check` failure, OIDC/Trusted-Publisher misconfig, etc.). **Do
not retry blindly** — republishing the same version to PyPI will fail, so the fix usually involves the
user (e.g. correcting the publisher config), not re-running the job.

## 5. Verify the published version

A green publish workflow means PyPI *accepted* the upload, but the index/CDN needs a moment to expose it.
Verify in two phases — don't rely on `uvx --refresh` alone, which can silently resolve to the previous
version if the index hasn't caught up.

`<version>` = the tag without the leading `v` (tag `v1.8.0` → `1.8.0`).

### 5a. Confirm the version is available on the PyPI index

The version-specific JSON endpoint returns `200` only once that exact version is published. Poll it,
retrying a few times with a short sleep between attempts until it returns `200` (propagation typically
takes seconds to a couple of minutes):

```bash
curl -sf -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/anki-addons-mcp/<version>/json
```

If it never appears within a sensible window, report that the publish workflow was green but the version
isn't visible on PyPI yet, and stop.

### 5b. Pull it to this machine and verify end-to-end

Only after 5a returns `200`, run the README's check so the just-published package is actually fetched and
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

Then run the pinned check:

```bash
uvx --refresh -p "$PYMIN" "anki-addons-mcp@<version>" --version 2>&1 | grep -x "<version>" \
  || { echo "FAILED: uvx did not run <version>"; exit 1; }
```

`--refresh` bypasses uvx's cache so it fetches the newly published version; `@<version>` pins the release
and `-p "$PYMIN"` picks an interpreter that release's `requires-python` accepts — without them, uv picks
an interpreter first and silently falls back to an older release. The `grep` makes the app's own `--version`
output the pass condition, so the step cannot succeed on the wrong version.

### 5c. Check the bare command users actually type

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

Report the final state: the pushed tag, the release URL, the publish-workflow result, the verified pinned
`uvx` version, and what the bare `uvx anki-addons-mcp --version` resolves to (with the cause if it is not
the new release) — or the first step that failed and why.
