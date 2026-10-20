---
name: deploy
description: Deploy a chosen version (the latest release or main) to the HuggingFace Space and see it running — suggest the versions that are ahead of the Space and passed CI, ask which one to deploy, push it to the `space` remote, wait for the Space to rebuild on that commit, and smoke-test the live MCP endpoint. Use when the user says "deploy", "/deploy", or asks to update/redeploy the HuggingFace Space.
allowed-tools: Bash(git *) Bash(gh *) Bash(curl *) Bash(python3 *) Bash(npx *)
disable-model-invocation: true
---

# deploy

Deploy a version to the HuggingFace Space (README-DEV.md → "Deploy to a HuggingFace Space") and verify that
the Space runs it. The skill suggests two candidates, the latest release (after `/release`) and `main` (after
`/push`), and asks which one to deploy. It only deploys what is already on GitHub and green, only moves the
Space forward (never a rollback, never a force-push), and does not commit or fix code itself. Work through the
steps in order; stop and report if a step can't be completed.

- Space: https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp (git remote `space`)
- Endpoint: `https://ya-alex-anki-addons-mcp.hf.space/mcp`, health check `/healthz`
- Runtime API (public, no token): `https://huggingface.co/api/spaces/Ya-Alex/anki-addons-mcp/runtime`

## 1. Preconditions

Confirm the current branch is `main` and the working tree is clean:

```bash
git rev-parse --abbrev-ref HEAD
git status --porcelain
```

If not on `main`, or there is **any** `git status` output, stop and report. Do not commit on the user's behalf.

Confirm `main` is pushed to GitHub, and fetch the release tags:

```bash
git fetch -q --tags origin
git rev-parse HEAD origin/main
```

If `HEAD` differs from `origin/main`, stop and tell the user to run `/push` first.

Confirm the remote `space` exists (`git remote get-url space`). If it is missing, stop and point the user to
the setup in README-DEV.md (`git remote add space https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp`).

## 2. Choose the version to deploy

### 2a. Check what the Space runs now

```bash
git fetch -q space
git rev-parse space/main
curl -s https://huggingface.co/api/spaces/Ya-Alex/anki-addons-mcp/runtime \
  | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r["stage"], r.get("sha"))'
```

If `space/main` is **not** an ancestor of `origin/main` (`git merge-base --is-ancestor space/main origin/main`
fails), the Space has commits that are not on `main` (e.g. edits made on huggingface.co). Stop and report;
never force-push to the Space.

### 2b. Build the candidates

- **Release**: the newest published GitHub release and its commit; the version is the tag without the `v`:

  ```bash
  gh release list --exclude-drafts --exclude-pre-releases --limit 1 --json tagName -q '.[0].tagName'
  git rev-parse '<tag>^{commit}'
  ```

- **Main**: `HEAD`; the version is `__version__` in `git show HEAD:src/anki_addons_mcp/__init__.py`.

Keep a candidate only if all of these hold, and remember the reason for each one you drop:

1. It is reachable from `main`: `git merge-base --is-ancestor <sha> origin/main`.
2. It is **ahead** of the Space: `<sha>` differs from `space/main` and
   `git merge-base --is-ancestor space/main <sha>` succeeds. An older or equal commit would need a rollback,
   which this skill never does.
3. It passed CI — the Space must only get code that passed CI:
   - Main: the Unit-tests run for `HEAD` is green
     (`gh run list --branch main --commit <sha> --workflow unit-tests.yml --limit 1`). If it is in progress,
     wait with `gh run watch <run-id> --exit-status`. Failed or missing: drop it ("run `/push` first").
   - Release: the tag commit has no Unit-tests run of its own when it only bumps the version, so accept a green
     Unit-tests run on the tag commit, **or** on its parent (`<sha>^`) when
     `git diff --name-only '<sha>^' <sha>` lists only `.bumpversion.toml` and `src/anki_addons_mcp/__init__.py`.
     The tag's "Publish to PyPI" run must also be green
     (`gh run list --workflow publish.yml --branch <tag> --limit 1`).

If the two candidates are the same commit, keep one (the release).

### 2c. Ask

If no candidate is left, nothing needs deploying: report each candidate's reason and skip to step 5 to
smoke-test what runs now.

Otherwise ask with `AskUserQuestion` (single-select), even when only one candidate is left — never deploy
without the user's choice. Put the release first and mark it "(Recommended)". Each option's description shows
the commit, the version change of the Space, and how many commits it moves the Space forward
(`git rev-list --count space/main..<sha>`), e.g.:

- `v0.5.0 (Recommended)`: release, commit `0b11baa`, `0.5.0.dev0` → `0.5.0`, 1 commit ahead
- `main`: commit `f7f0ecc`, `0.5.0.dev0` → `0.6.0.dev0`, 2 commits ahead

The chosen commit is `<sha>` and its version `<version>` for the remaining steps.

## 3. Push to the Space

```bash
git push space <sha>:main
```

It is a fast-forward: step 2b only keeps commits ahead of `space/main`.

Git authenticates to huggingface.co with the HF token stored in its credential helper. If the push fails with
an authentication error (e.g. `could not read Username for 'https://huggingface.co'`), stop and point the user
to the one-time setup in README-DEV.md → "Deploy to a HuggingFace Space". If the push is rejected for any other
reason, stop and report.

## 4. Wait for the Space to build and start

Pushing triggers a Docker rebuild. Poll the runtime API every 20 s, for up to 15 min, until the Space runs the
pushed commit. Run the poll as a single `python3` command (no shell `for`/`sleep` loop, which needs extra
permission), with a Bash timeout of at least 960000 ms:

```bash
python3 -c '
import json, sys, time, urllib.request
url = "https://huggingface.co/api/spaces/Ya-Alex/anki-addons-mcp/runtime"
for _ in range(45):
    runtime = json.load(urllib.request.urlopen(url))
    stage, sha = runtime["stage"], runtime.get("sha")
    print(time.strftime("%H:%M:%S"), stage, sha, flush=True)
    if (stage == "RUNNING" and sha == sys.argv[1]) or stage.endswith("ERROR"):
        break
    time.sleep(20)
' <sha>
```

- `BUILDING`, `RUNNING_BUILDING`, `APP_STARTING` (or the old sha still `RUNNING`): keep waiting.
- `RUNNING` with `sha` equal to `<sha>`: continue to step 5.
- `BUILD_ERROR`, `RUNTIME_ERROR` or `CONFIG_ERROR`: stop. Report the stage and point the user to the
  **Logs** tab of the Space page (build and container logs need a token to read through the API). Reproduce
  a build failure locally with `docker build .` if useful.
- Still not running the new sha after ~15 min: stop and report the last stage seen.

## 5. Smoke-test the live endpoint

The Space loads the latest dataset snapshot at startup, so the first requests can be slow.

```bash
curl -s -m 120 https://ya-alex-anki-addons-mcp.hf.space/healthz
npx @modelcontextprotocol/inspector --cli https://ya-alex-anki-addons-mcp.hf.space/mcp --transport http \
  --method tools/list
npx @modelcontextprotocol/inspector --cli https://ya-alex-anki-addons-mcp.hf.space/mcp --transport http \
  --method tools/call --tool-name search_addons --tool-arg query="image occlusion" --tool-arg limit=3
```

- `/healthz` must return `{"status": "ok", "version": "<version>"}`. For a release that proves the release is
  live. A development version doesn't change on every commit, so for `main` the runtime sha (step 4) is what
  proves the new commit is live, not the version. If nothing was deployed (step 2c), compare with the version of
  `space/main` instead.
- `tools/list` must succeed. If the deployed commit added or changed tools, check they appear as expected.
- The `search_addons` call must return addon cards without `isError`.

If a check fails, report the output and point the user to the **Logs** tab of the Space page.

## Done

Report the final state: the chosen candidate (release tag or `main`), the deployed commit SHA and version (and
the previous SHA and version the Space ran), the runtime stage, the `/healthz` version, and the smoke-test
results — or the first step that failed and why. When a candidate was dropped in step 2b, say which and why.
