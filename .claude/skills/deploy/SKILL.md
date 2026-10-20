---
name: deploy
description: Deploy a chosen version (the latest release or main) to the HuggingFace Space and see it running — suggest the versions that are ahead of the Space with their GitHub and CI status, ask which one to deploy, push it to the `space` remote, wait for the Space to rebuild on that commit, and smoke-test the live MCP endpoint. Use when the user says "deploy", "/deploy", or asks to update/redeploy the HuggingFace Space.
allowed-tools: Bash(git *) Bash(gh *) Bash(curl *) Bash(python3 *) Bash(npx *) Bash(uv *)
disable-model-invocation: true
---

# deploy

Deploy a version to the HuggingFace Space (README-DEV.md → "Deploy to a HuggingFace Space") and verify that
the Space runs it. The skill suggests two candidates, the latest release and the local `main`, shows whether each
is on GitHub and passed CI, and asks which one to deploy. It only moves the Space forward (never a rollback, never
a force-push), and does not commit or fix code itself. Work through the steps in order; stop and report if a step
can't be completed.

- Space: https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp (git remote `space`)
- Endpoint: `https://ya-alex-anki-addons-mcp.hf.space/mcp`, health check `/healthz`
- Runtime API (public, no token): `https://huggingface.co/api/spaces/Ya-Alex/anki-addons-mcp/runtime`

## 1. Preconditions

Fetch GitHub's `main` and the release tags:

```bash
git fetch -q --tags origin
```

Confirm the remote `space` exists (`git remote get-url space`). If it is missing, stop and point the user to
the setup in README-DEV.md (`git remote add space https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp`).

Only committed code is deployed, so uncommitted changes (`git status --porcelain`) don't block the deploy;
mention them in the report.

## 2. Choose the version to deploy

### 2a. Check what the Space runs now

```bash
git fetch -q space
git rev-parse space/main
curl -s https://huggingface.co/api/spaces/Ya-Alex/anki-addons-mcp/runtime \
  | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r["stage"], r.get("sha"))'
```

If `space/main` is **not** an ancestor of the local `main` (`git merge-base --is-ancestor space/main main`
fails), the Space has commits that are not on `main` (e.g. edits made on huggingface.co). Stop and report;
never force-push to the Space.

### 2b. Build the candidates

- **Release**: the newest published GitHub release and its commit; the version is the tag without the `v`:

  ```bash
  gh release list --exclude-drafts --exclude-pre-releases --limit 1 --json tagName -q '.[0].tagName'
  git rev-parse '<tag>^{commit}'
  ```

- **Main**: the local `main` (`git rev-parse main`); the version is `__version__` in
  `git show main:src/anki_addons_mcp/__init__.py`.

Keep a candidate only if it is **ahead** of the Space: `<sha>` differs from `space/main` and
`git merge-base --is-ancestor space/main <sha>` succeeds. An older or equal commit would need a rollback, which
this skill never does. Remember the reason for each candidate you drop. If the two candidates are the same commit,
keep one (the release).

For each kept candidate, collect its status (information for the user, not a filter):

1. **On GitHub**: `git merge-base --is-ancestor <sha> origin/main` succeeds; otherwise "not on GitHub".
2. **CI**: green, failed, in progress or no run. Don't wait for a run in progress.
   - Main: the Unit-tests run for `<sha>`
     (`gh run list --branch main --commit <sha> --workflow unit-tests.yml --limit 1`).
   - Release: the tag commit has no Unit-tests run of its own when it only bumps the version, so count a green
     Unit-tests run on the tag commit, **or** on its parent (`<sha>^`) when
     `git diff --name-only '<sha>^' <sha>` lists only `.bumpversion.toml` and `src/anki_addons_mcp/__init__.py`.
     The tag's "Publish to PyPI" run must also be green
     (`gh run list --workflow publish.yml --branch <tag> --limit 1`).

### 2c. Ask

If no candidate is left, nothing needs deploying: report each candidate's reason and skip to step 5 to
smoke-test what runs now.

Otherwise ask with `AskUserQuestion` (single-select), even when only one candidate is left — never deploy
without the user's choice. Put the release first. Mark "(Recommended)" the release when its CI is green,
otherwise a candidate with green CI; with no green candidate, recommend none. Each option's description shows
the commit, the version change of the Space, how many commits it moves the Space forward
(`git rev-list --count space/main..<sha>`) and its status, e.g.:

- `v0.5.0 (Recommended)`: release, commit `0b11baa`, `0.5.0.dev0` → `0.5.0`, 1 commit ahead, CI green
- `main`: commit `67d4e14`, `0.5.0.dev0` → `0.6.0.dev0`, 4 commits ahead, not on GitHub, no CI run

The chosen commit is `<sha>` and its version `<version>` for the remaining steps.

## 3. Test a candidate without green CI

Skip this step when the chosen candidate's CI is green. Otherwise run the tests and lint on `<sha>`. If the
working tree is clean and `HEAD` is `<sha>`, run them in place; otherwise in a worktree in the scratchpad:

```bash
git worktree add --detach <scratchpad>/deploy-check <sha>
uv run --directory <scratchpad>/deploy-check pytest -q
uv run --directory <scratchpad>/deploy-check ruff check src tests
git worktree remove --force <scratchpad>/deploy-check
```

If a check fails, report the output and ask with `AskUserQuestion` whether to deploy anyway or stop.

## 4. Push to the Space

```bash
git push space <sha>:main
```

It is a fast-forward: step 2b only keeps commits ahead of `space/main`.

Git authenticates to huggingface.co with the HF token stored in its credential helper. If the push fails with
an authentication error (e.g. `could not read Username for 'https://huggingface.co'`), stop and point the user
to the one-time setup in README-DEV.md → "Deploy to a HuggingFace Space". If the push is rejected for any other
reason, stop and report.

## 5. Wait for the Space to build and start

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
- `RUNNING` with `sha` equal to `<sha>`: continue to step 6.
- `BUILD_ERROR`, `RUNTIME_ERROR` or `CONFIG_ERROR`: stop. Report the stage and point the user to the
  **Logs** tab of the Space page (build and container logs need a token to read through the API). Reproduce
  a build failure locally with `docker build .` if useful.
- Still not running the new sha after ~15 min: stop and report the last stage seen.

## 6. Smoke-test the live endpoint

The Space loads the latest dataset snapshot at startup, so the first requests can be slow.

```bash
curl -s -m 120 https://ya-alex-anki-addons-mcp.hf.space/healthz
npx @modelcontextprotocol/inspector --cli https://ya-alex-anki-addons-mcp.hf.space/mcp --transport http \
  --method tools/list
npx @modelcontextprotocol/inspector --cli https://ya-alex-anki-addons-mcp.hf.space/mcp --transport http \
  --method tools/call --tool-name search_addons --tool-arg query="image occlusion" --tool-arg limit=3
```

- `/healthz` must return `{"status": "ok", "version": "<version>"}`. For a release that proves the release is
  live. A development version doesn't change on every commit, so for `main` the runtime sha (step 5) is what
  proves the new commit is live, not the version. If nothing was deployed (step 2c), compare with the version of
  `space/main` instead.
- `tools/list` must succeed. If the deployed commit added or changed tools, check they appear as expected.
- The `search_addons` call must return addon cards without `isError`.

If a check fails, report the output and point the user to the **Logs** tab of the Space page.

## Done

Report the final state: the chosen candidate (release tag or `main`), the deployed commit SHA and version (and
the previous SHA and version the Space ran), the runtime stage, the `/healthz` version, and the smoke-test
results — or the first step that failed and why. When a candidate was dropped in step 2b, say which and why.
When the deployed commit is not on GitHub, say so and suggest `/push`; when it had no green CI, give the local
test results from step 3.
