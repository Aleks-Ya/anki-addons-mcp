# Maintainer guide

Deploying, releasing and CI. For running and testing the code, see the [Developer guide](development.md).

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
