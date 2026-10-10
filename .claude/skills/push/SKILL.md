---
name: push
description: Push the main branch and see it through green — verify a clean tree, upgrade deps and run ruff, mypy and pytest locally, push, wait for the GitHub Actions "Unit-tests" workflow and fix any failures, then review SonarCloud issues on the new code and fix them. Use when the user says "push", "/push", or asks to push and make sure CI/Sonar are clean.
allowed-tools: Bash(uv *) Bash(gh run *) Bash(git *) Bash(curl *)
disable-model-invocation: true
---

# push

Push `main` and drive it to a fully green state: CI passing and no new SonarCloud issues. Work through the steps in order; stop and report if a step can't be completed.

## 1. Verify a clean working tree

```bash
git status --porcelain
```

- If the output is **empty**, the tree is clean — continue.
- If there is **any** output, there are uncommitted or untracked files. **Stop.** Do not push. Report the uncommitted files to the user and ask whether to commit them (and how) before pushing. Never commit on the user's behalf here unless they explicitly ask.

Also confirm the current branch is `main`:

```bash
git rev-parse --abbrev-ref HEAD
```

If not on `main`, stop and ask the user before pushing.

## 2. Upgrade dependencies and run checks locally

Before pushing, sync the environment and run the same checks as CI so failures are caught locally rather than in CI.

```bash
uv lock --upgrade && uv sync
uv run ruff check src tests
uv run mypy
uv run pytest
```

- `uv lock --upgrade && uv sync` upgrades every dependency to its latest allowed version, refreshes `uv.lock`, and syncs `.venv` with the project (editable) plus its `dev` dependency group, so `pytest` and the rest of the toolchain are present and up to date. If it changes `uv.lock`, that change must be committed (CI runs `uv sync --locked` and fails on a stale lock).
- If ruff, mypy or pytest **fails**, **stop.** Do not push. Fix the failures in the working tree first (and, per step 1, don't commit on the user's behalf unless they ask). Re-run the checks until green, then continue.

## 3. Push the main branch

```bash
git push origin main
```

If the push is rejected (e.g. remote is ahead), a force-push is allowed — but only when the user has explicitly asked for it (e.g. "force push", "/push force"). Use the safer `--force-with-lease`, which refuses to overwrite if the remote has commits you haven't seen:

```bash
git push --force-with-lease origin main
```

Never force-push on your own initiative: if the push is rejected and the user hasn't asked to force, stop and report the rejection instead. Avoid the bare `--force`.

## 4. Wait for GitHub Actions and check success

The push triggers the **Unit-tests** workflow (`.github/workflows/unit-tests.yml`: TruffleHog → Ruff → Mypy → PyTest → SonarCloud Scan). Wait for the run that corresponds to the commit just pushed.

```bash
# Find the run for the just-pushed commit
git rev-parse HEAD
gh run list --branch main --limit 5
```

Watch it to completion (this blocks until the run finishes):

```bash
gh run watch --exit-status
```

- `gh run watch --exit-status` exits non-zero if the run fails.
- If it **succeeds**, continue to step 5.
- If it **fails**, inspect the failing job and fix the errors:

```bash
gh run view --log-failed
```

Diagnose the failure (failing test, ruff or mypy error, TruffleHog secret finding, dependency issue, etc.), fix it in the working tree, commit, and push again. Then repeat step 4 until the workflow is green. Report clearly what failed and what you changed.

## 5. Review SonarCloud issues and fix

The workflow's SonarCloud Scan publishes analysis to SonarCloud (project `Aleks-Ya_anki-addons-mcp`, org `aleks-ya`, https://sonarcloud.io). After CI is green (step 4), check for open issues introduced on the pushed code.

```bash
# Open issues for the project (public API; add -H "Authorization: Bearer $SONAR_TOKEN" if needed)
curl -s 'https://sonarcloud.io/api/issues/search?componentKeys=Aleks-Ya_anki-addons-mcp&resolved=false&statuses=OPEN,CONFIRMED,REOPENED&ps=100' \
  | python3 -m json.tool
```

Focus on issues touching the code just pushed (recent `creationDate`, or files in the diff). For each real issue:

- Read the `rule`, `message`, `component` (file), and `line`.
- Fix the underlying code — don't just silence it. Only suppress (e.g. `# NOSONAR`) when the rule is a genuine false positive, and say so.
- Re-run the checks locally (ruff, mypy, `uv run pytest`) before pushing the fix.

Commit and push the fixes, then loop back through steps 4–5 (CI runs again, Sonar re-analyzes) until CI is green and there are no new/open Sonar issues on the changed code.

If the SonarCloud API returns nothing usable (auth required and no token available), tell the user and point them to the dashboard: https://sonarcloud.io/project/issues?id=Aleks-Ya_anki-addons-mcp&resolved=false

## Done

Report the final state: pushed commit SHA, CI result, and Sonar status (clean, or what was fixed).
