---
name: deploy
description: Deploy main to the HuggingFace Space and see it running — check that main is pushed and green, push it to the `space` remote, wait for the Space to rebuild on that commit, and smoke-test the live MCP endpoint. Use when the user says "deploy", "/deploy", or asks to update/redeploy the HuggingFace Space.
allowed-tools: Bash(git *) Bash(gh *) Bash(curl *) Bash(python3 *) Bash(npx *) Bash(hf auth whoami)
disable-model-invocation: true
---

# deploy

Deploy `main` to the HuggingFace Space (README-DEV.md → "Deploy to a HuggingFace Space") and verify that the
Space runs the pushed commit. This is the natural follow-on to `/push`: it deploys what is already on GitHub
and green, and does not commit or fix code itself. Work through the steps in order; stop and report if a step
can't be completed.

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

Confirm `main` is pushed to GitHub and its CI is green — the Space must only get code that passed CI:

```bash
git fetch -q origin
git rev-parse HEAD origin/main
gh run list --branch main --commit "$(git rev-parse HEAD)" --workflow unit-tests.yml --limit 1
```

- If `HEAD` differs from `origin/main`, stop and tell the user to run `/push` first.
- If the Unit-tests run for `HEAD` is in progress, wait for it with `gh run watch <run-id> --exit-status`.
- If it failed, or there is no run, stop and tell the user to run `/push` first.

Confirm the remote `space` exists (`git remote get-url space`). If it is missing, stop and point the user to
the setup in README-DEV.md (`git remote add space https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp`).

## 2. Check what the Space runs now

```bash
git fetch -q space
git rev-parse space/main
curl -s https://huggingface.co/api/spaces/Ya-Alex/anki-addons-mcp/runtime \
  | python3 -c 'import sys,json; r=json.load(sys.stdin); print(r["stage"], r.get("sha"))'
```

- If `space/main` already equals `HEAD` and the runtime is `RUNNING` on that sha, nothing needs deploying —
  skip to step 5 to smoke-test and report.
- If `space/main` is **not** an ancestor of `HEAD` (`git merge-base --is-ancestor space/main HEAD` fails), the
  Space has commits that are not on `main` (e.g. edits made on huggingface.co). Stop and report; never
  force-push to the Space.

## 3. Push to the Space

The `space` remote uses HTTPS and needs HuggingFace credentials. Use the user's current `hf` CLI login; don't
ask the user to push or to set up credentials. Pass the token to git through a credential helper given only for
this command, so nothing is written to the git config and the token never appears in the output:

```bash
hf auth whoami
git -c 'credential.https://huggingface.co.helper=!f() { test "$1" = get && echo username=Ya-Alex && echo "password=$(hf auth token)"; }; f' \
  push space main
```

- If `hf auth whoami` shows no login, stop and ask the user to run `! hf auth login`.
- Never print the token, and never save it in the git config or `~/.git-credentials`.
- If the push is rejected for any other reason, stop and report.

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
' "$(git rev-parse HEAD)"
```

- `BUILDING`, `RUNNING_BUILDING`, `APP_STARTING` (or the old sha still `RUNNING`): keep waiting.
- `RUNNING` with `sha` equal to `git rev-parse HEAD`: continue to step 5.
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

- `/healthz` must return `{"status": "ok", "version": ...}` with the version in
  `src/anki_addons_mcp/__init__.py`. Development versions don't change on every commit, so the runtime sha
  (step 4) is what proves the new commit is live, not the version.
- `tools/list` must succeed. If the deployed commit added or changed tools, check they appear as expected.
- The `search_addons` call must return addon cards without `isError`.

If a check fails, report the output and point the user to the **Logs** tab of the Space page.

## Done

Report the final state: the deployed commit SHA (and the previous one the Space ran), the runtime stage, the
`/healthz` version, and the smoke-test results — or the first step that failed and why.
