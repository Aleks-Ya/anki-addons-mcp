---
name: update-dataset
description: Move the server to a new version of the Anki Addons dataset — find the newest dataset tag, collect what changed (changelog, docs, real Parquet schemas and values, columns the MCP does not read yet, dataset consistency checks, a live run of every tool on the real data), write change requests for the dataset as a ready-to-paste AI prompt, negotiate a modification plan with the user in plan mode, then implement it, verify it and commit. Use when the user says "update dataset", "/update-dataset", or asks to adopt a new dataset version or tag.
allowed-tools: Bash(git *) Bash(gh *) Bash(uv *) Bash(python3 *)
disable-model-invocation: true
---

# update-dataset

Automates docs/maintaining.md → "Update the dataset version", steps 1–4. The server reads the dataset at the frozen
tag in `hf_revision` (`src/anki_addons_mcp/config.py`); this skill moves it to a newer tag and adapts the code.

The skill has **two outputs**, and both are reported explicitly:

1. **MCP changes**: planned, negotiated with the user, implemented, verified and committed in this repo.
2. **Dataset change requests**: what must change in the dataset itself, which this skill must not do. They go to the
   user as a ready-to-paste AI prompt for a Claude Code session in the dataset repo. When there are none, say "none".

The dataset is **read-only** for this skill: never modify the dataset repo (`../anki-addons-dataset`, not even
`git fetch` or a checkout), the local dataset (`~/anki-addons-dataset`) or the HuggingFace dataset.

**No file of this repo is edited before the user approves the plan in step 6.**

Work through the steps in order; stop and report if a step can't be completed.

Scripts (in `.claude/skills/update-dataset/scripts/`, run from the repo root with `uv run python <script>`;
`<s>` below stands for that directory):

| Script | Answers |
|---|---|
| `versions.py [--target TAG]` | Baseline tag and its metadata, version tags on HF, newer tags, branch heads, local dataset repo tags, whether the local bundle matches the target |
| `dataset_docs.py --base REV --target REV` | Changelog entries, commits and docs diff of the dataset repo between the two revisions' script versions; unreleased commits after the target |
| `dataset_diff.py schema values coverage checks --base REV --target REV` | Real Parquet schema diff of every table and snapshot; vocabulary changes; target columns the hf_parquet adapter never reads; dataset consistency checks (`DATASET ISSUE n:` lines) |
| `live_check.py --revision REV` or `--data-dir DIR` | Every tool and resource on the newest and oldest snapshot, `query_sql` on every table of every snapshot; non-zero exit on any failure |

## 1. Preconditions

```bash
git rev-parse --abbrev-ref HEAD
git status --porcelain
```

The branch must be `main` and the tree clean (the result is one reviewable commit). Otherwise stop and report.

## 2. Versions

```bash
uv run python <s>/versions.py
```

- **Newer tags**: with one, it is the target. With several, ask with `AskUserQuestion` which to adopt, newest first and
  marked "(Recommended)"; each option shows its `dataset_version` and whether the MAJOR changes. Rerun with
  `--target <tag>` to see the chosen one.
- **No newer tag**: the target is the baseline. Only the coverage audit and the dataset checks can produce work; if
  step 3 finds neither unread columns nor dataset issues, report "up to date" (with the MCP and dataset parts) and stop.
- **Branch heads** ahead of the newest tag mean an upload without a tag: that is a dataset change request (step 5).
- The baseline is not a version tag: stop and ask the user (the docs assume a tag).

Remember `<base>` (the baseline tag), `<target>` (the target tag), and whether the local bundle matches the target.

## 3. Evidence

Run all four, in one message (they are independent):

```bash
uv run python <s>/dataset_docs.py --base <base> --target <target>
uv run python <s>/dataset_diff.py schema values coverage checks --base <base> --target <target>
uv run python <s>/live_check.py --data-dir ~/anki-addons-dataset/bundle  # when versions.py says the bundle MATCHES
uv run python <s>/live_check.py --revision <target>                      # otherwise; run it in the background
```

`live_check.py` runs the **unchanged** code against the target: its failures show what the new version breaks (a
rename makes `query_sql` fail to bind the `addons` view on every snapshot). Over HuggingFace it downloads every
snapshot (about 20 MB each, at roughly 0.6 MB/s), so run it with `run_in_background` and read the other output
meanwhile.

Then read the documentation the changes touch, at the target's script tag, with read-only git:
`git -C ../anki-addons-dataset show v<script_version>:docs/dataset/addons.md` (also `tables.md`, `files.md`,
`versioning.md`). When the tag is not local, `versions.py` says so; use
`gh api -H 'Accept: application/vnd.github.raw' 'repos/Aleks-Ya/anki-addons-dataset/contents/<path>?ref=v<script_version>'`.

## 4. Analyse the MCP impact

List every finding of step 3 and classify it:

| Kind | Examples | MCP action |
|---|---|---|
| Breaking | a column removed, renamed or retyped; a table or file gone; `live_check` failures | must fix |
| Additive | a new column, table, file or value; columns `coverage` lists as not read | candidate to expose, the user decides |
| Meaning or vocabulary | `values` diff (renamed values, new enum members); changelog says a meaning changed | descriptions, fixtures, filters |
| New snapshots only | `schema` shows added snapshots and no column change | none beyond the tag |

Map each finding to the code. The touch points, from past dataset updates (`git log --grep dataset`):

- `domain/models.py` (pydantic models), `domain/ports.py`, `domain/query.py` (filters)
- `adapters/hf_parquet/sql.py` (the flat `addons` view and the SQL tables: `FLAT_COLUMNS` with their descriptions),
  `mapping.py` (rows → models), `repository.py` (queries, filters, statistics), `source.py` (files of a snapshot)
- `adapters/memory/repository.py` (the reference adapter) and `tests/contract` (keeps both adapters identical)
- `application/*` (services), `interface/mcp/tools.py`, `resources.py`, `prompts.py`, and `server.py` (`INSTRUCTIONS`)
- `tests/fixtures/dataset.py` (the fixture dataset in the published layout), `tests/adapters/test_sql_sandbox.py`,
  `tests/interface/test_mcp_server.py`, `tests/application/test_services.py`
- `docs/reference.md`, `docs/dataset-notes.md` (incl. the "Availability by snapshot" table), README "What it can do"

Rules, learned from past dataset updates:

- A revision shares one schema across its snapshots, so no back-compat code is needed for anything republished in
  all of them. Where `dataset_diff.py` still finds a null-typed column in older snapshots, read it with `TRY_CAST(...
  AS <explicit type>)` or `to_json`, never a plain `CAST`: DuckDB 2.0 raises an INTERNAL error on it that breaks the
  whole database. `query_sql` columns must bind on every snapshot.
- Timestamps stay `str`, never `datetime`: pydantic declares `format: date-time`, which strict clients reject for
  timestamps without a timezone (`test_output_schemas_have_no_date_time_format`).
- Change both adapters, memory and DuckDB, and extend `tests/contract`.
- Formulas that exist twice stay in sync: compatibility in `domain/compatibility.py` and in the DuckDB SQL; approval
  in `domain/models.py` and `_APPROVAL` in the DuckDB adapter.
- Verdicts (`check_compatibility`, maintenance labels) don't change because of new data without the user's ruling.
- `anki_web.rating` is the vote count, not a score: never rank by it.
- A new table the dataset may lack follows the `anki_versions` pattern (`None` → empty result); a required one follows
  `reviews`/`packages`.
- Fixtures reproduce real shapes: if older snapshots lack data, the fixture's OLD snapshot lacks it too.

## 5. Dataset change requests

This step always runs. Collect a request for:

- every `DATASET ISSUE` line of `dataset_diff.py checks`;
- every `ISSUE` line of `dataset_docs.py`;
- every change found in the data (`schema`, `values`) that the changelog or docs don't mention;
- every statement in the dataset docs that the data contradicts;
- branch heads ahead of the newest tag (step 2);
- anything the MCP needs that belongs in the dataset, e.g. a value the MCP would otherwise compute and duplicate.

Each request has: the problem, the evidence with a command that reproduces it, the requested change, the acceptance
criteria, the MCP impact if it stays unfixed, and whether it **blocks** the update (the MCP can't serve the target
correctly without it) or not.

When there is at least one request, write `<scratchpad>/dataset-change-requests.md`, a self-contained prompt for a
Claude Code session opened in `/home/aleks/pr/home/anki-addons-dataset`:

```markdown
# Change requests from anki-addons-mcp for dataset <target> (dataset_version X.Y, script A.B.C)

Context: anki-addons-mcp serves the HF dataset Ya-Alex/anki-addons pinned to a version tag. While adopting
<target> it found the problems below. Fix them in the pipeline and its docs, follow docs/dataset/versioning.md
(bump dataset_version, update schema.json and docs/dataset/changelog.md where it applies), and publish a new tag.

## 1. <short title> (blocking | not blocking)
Problem: ...
Evidence: <command and its output>
Requested change: ...
Acceptance: ...

## 2. ...

Verify: uv run pytest (dataset_schema_test.py included), uv run ruff check, uv run mypy.
```

Print the prompt in full in a fenced block, tell the user to paste it into a Claude Code session in the dataset repo,
and give the file path. For each **blocking** request, ask with `AskUserQuestion`: wait for a fixed dataset (stop
here; rerun `/update-dataset` once the new tag is published) or plan a workaround in the MCP (the plan then names it).
Non-blocking requests don't stop the run.

## 6. Negotiate the plan

Enter plan mode with `EnterPlanMode` and write the plan with these sections:

1. **Context**: `<base>` → `<target>`, `dataset_version` and `script_version` of both, new snapshots.
2. **Dataset changes found**: a table of every finding from step 4, with its kind and evidence.
3. **MCP modifications**: per finding, what changes and in which files; the tag bump is always one of them.
4. **Left unexposed**: findings deliberately not followed, and why.
5. **Dataset change requests**: the numbered list from step 5 with the prompt path, or "None".
6. **Verification**: step 8.
7. **Commit**: the message of step 9.

Ask the user's rulings with `AskUserQuestion` before submitting, wherever the answer changes the plan, e.g.: expose
new field X, and where (addon details, cards, a filter, `query_sql`, `get_statistics` group-by); may a verdict use it;
include it by default or only through `include=`. Recommend an option.

Submit the plan with `ExitPlanMode`. If the user rejects it or comments, revise and submit again. Only an approved plan
is implemented.

## 7. Implement

Implement the approved plan, and always:

- set `<target>` as the `hf_revision` default in `src/anki_addons_mcp/config.py` and as the `ANKI_MCP_HF_REVISION`
  default in docs/configuration.md;
- update the fixtures (`tests/fixtures/dataset.py`) to the new shapes;
- update the docs the change affects: docs/reference.md, docs/dataset-notes.md, README "What it can do".

## 8. Verify

```bash
uv run ruff check src tests
uv run mypy
uv run pytest
uv run python <s>/live_check.py --data-dir ~/anki-addons-dataset/bundle  # or --revision <target>, in the background
uv run python <s>/dataset_diff.py coverage --base <target> --target <target>
```

`live_check.py` must report 0 failures and list the new snapshots; `coverage` must list only the columns the plan
leaves unexposed. Fix failures and rerun until everything passes. If a fix needs a change outside the approved plan,
ask the user first.

## 9. Commit and report

Commit everything as one commit (the plan announced it, so the approval covers it). Use the subject
`Update the dataset to <target>` and a body in the style of the earlier dataset commits
(`git log --grep dataset -3`): what changed in the dataset, what the server does about it. Never push.

Report in two explicitly separate parts:

- **MCP**: `<base>` → `<target>`, the commit SHA, the changes made, the findings left unexposed, the check results.
- **Dataset change requests**: the numbered list with blocking/not blocking, and the path of the prompt file; or
  "None".

Then suggest the next steps: `/push`, then `/release`, then `/deploy` (docs/maintaining.md, step 5).
