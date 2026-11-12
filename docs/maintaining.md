# Maintainer guide

Deploying, releasing, updating the dataset version and CI. For running and testing the code, see the [Developer guide](development.md).

## Deploy to a HuggingFace Space

Space: https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp

1. Create a Space with the **Docker** SDK.
2. Let git use your HuggingFace login (once per machine; requires `hf auth login`):
   ```bash
   git config --global credential.helper store
   hf auth login --token "$(hf auth token)" --add-to-git-credential
   ```
3. Push this repository to it. The YAML header of `README.md` configures the Space (`sdk: docker`,
   `app_port: 7860`):
   ```bash
   git remote add space https://huggingface.co/spaces/Ya-Alex/anki-addons-mcp
   git push space main
   ```
4. Optionally add an `HF_TOKEN` secret for higher download rate limits.

The endpoint is `https://ya-alex-anki-addons-mcp.hf.space/mcp`. The Space loads the latest snapshot at
startup; its disk is ephemeral, so snapshots are downloaded again after a restart.

Step 3 for an existing Space is automated by the skill `/deploy`: it suggests the latest release and `main`
(those ahead of the Space, with whether they are on GitHub and passed CI), deploys the chosen one (running the
tests locally first when it has no green CI), waits for the rebuild and smoke-tests the endpoint. It only moves
the Space forward and never force-pushes.

## Update the dataset version

The server reads the dataset at a frozen revision: the default of `hf_revision` in
`src/anki_addons_mcp/config.py`. The dataset publishes these refs (its
[versioning](https://github.com/Aleks-Ya/anki-addons-dataset/blob/main/docs/dataset/versioning.md) and
[changelog](https://github.com/Aleks-Ya/anki-addons-dataset/blob/main/docs/dataset/changelog.md)):

| Revision | Gets |
|---|---|
| `vMAJOR.MINOR-<date>` tag, e.g. `v1.0-2026-11-01` | never changes |
| `v1` branch | every new snapshot, never a breaking change |
| `main` branch | every new snapshot and every change, including breaking |

The default is a tag, so the data is reproducible and no schema change reaches the server untested. The cost is
that the hourly refresh finds nothing new: a new snapshot reaches users only with a new release of the server.

1. List the version tags (ignore the `backup-*` tags):
   ```bash
   uv run python -c "from huggingface_hub import HfApi; print([t.name for t in HfApi().list_repo_refs('Ya-Alex/anki-addons', repo_type='dataset').tags if t.name.startswith('v')])"
   ```
   `list_repo_refs` shows the annotated tag object as a tag's target, not the commit; the commit the server
   loads is `HfApi().dataset_info('Ya-Alex/anki-addons', revision='<tag>').sha`.
2. Read the dataset changelog since the current tag and adapt the code to schema changes. A MAJOR bump means a
   column was removed or renamed.
3. Set the new tag in `hf_revision` (`src/anki_addons_mcp/config.py`) and in the `ANKI_MCP_HF_REVISION` default
   in [Configuration](configuration.md).
4. Run the tests, then start the server against the new tag and check that the log shows its commit and that
   `list_snapshots` lists the new snapshot:
   ```bash
   uv run anki-addons-mcp --transport http --port 8000
   ```
5. [Release a new version](#release-a-new-version) and [deploy](#deploy-to-a-huggingface-space) it.

Steps 1–4 are automated by the skill `/update-dataset`. Its scripts compare the two tags (changelog, docs, real Parquet
schemas and values), list the dataset columns the server doesn't read yet, check the dataset for inconsistencies and
run every tool against the real data. The skill negotiates a modification plan before it edits anything, and it writes
what must change in the dataset itself as a ready-to-paste AI prompt for the dataset repo.

## Release a new version

The version lives in `src/anki_addons_mcp/__init__.py` (`__version__`) and is bumped with
[bump-my-version](https://github.com/callowayproject/bump-my-version) (`.bumpversion.toml`). Development
versions carry the `.dev0` suffix; each bump makes a commit and needs a clean working tree.
Step 1 is automated by the skill `/push`, steps 2–8 by the skill `/release`.

1. Push `main` and wait for a green [Unit-tests](#continuous-integration) run and a clean SonarCloud report
2. Show the next versions: `uv run bump-my-version show-bump`
3. Switch the dev version to a release and tag it (`0.1.0.dev0` -> `0.1.0`, tag `v0.1.0`):
   `uv run bump-my-version bump release --tag`
4. Switch the release to the next dev version (`0.1.0` -> `0.2.0.dev0`): `uv run bump-my-version bump minor`
5. Push the branch and tags: `git push origin HEAD --tags`
6. Create a GitHub release from the tag: `gh release create v0.1.0 --title v0.1.0 --generate-notes`
7. Wait for the publish workflow: https://github.com/Aleks-Ya/anki-addons-mcp/actions
8. Verify the release: `uvx --refresh anki-addons-mcp@0.1.0 --version`

## Publish to PyPI
PyPI package: https://pypi.org/project/anki-addons-mcp

Publishing is automated: creating a GitHub release runs `.github/workflows/publish.yml`
(PyPI Trusted Publishing, no API tokens). The PyPI description is generated from `README.md` by
[hatch-fancy-pypi-readme](https://github.com/hynek/hatch-fancy-pypi-readme): it skips the HuggingFace
Space header and turns relative links into GitHub links.

One-time setup on [pypi.org](https://pypi.org/manage/project/anki-addons-mcp/settings/publishing/): add a
Trusted Publisher pointing at repo `Aleks-Ya/anki-addons-mcp`, workflow `publish.yml`, environment `pypi`.

Manual build/publish (fallback):
```bash
rm -rf dist && uv build                 # creates dist/*.whl and dist/*.tar.gz
uvx twine check --strict dist/*
uv publish                              # requires a PyPI API token (UV_PUBLISH_TOKEN)
```

A version can be uploaded to PyPI only once. To try an upload first, publish to TestPyPI (a separate
account and token): `uv publish --publish-url https://test.pypi.org/legacy/`.

## Continuous integration
`.github/workflows/unit-tests.yml` runs on every push and pull request to `main`: TruffleHog secret scan,
`uv sync --locked` (a stale `uv.lock` fails the build), ruff, mypy, pytest with coverage, and a SonarCloud
scan (`sonar-project.properties`).

- Actions: https://github.com/Aleks-Ya/anki-addons-mcp/actions
- SonarCloud: https://sonarcloud.io/summary/overall?id=Aleks-Ya_anki-addons-mcp&branch=main

One-time setup: import the repository into the `aleks-ya` organization on [SonarCloud](https://sonarcloud.io),
switch its analysis method to CI-based (turn off Automatic Analysis), and add the `SONAR_TOKEN` repository
secret on GitHub.
