# Dataset notes

What the [Anki Addons dataset](https://huggingface.co/datasets/Ya-Alex/anki-addons) can and cannot tell, and
how the server reflects it. The dataset card is also available to clients as the resource
`anki-addons://dataset/readme`, and the full record schema as `anki-addons://dataset/schema`.

## AI-generated data

Some fields are produced by an LLM and may be wrong; the server labels them as such:
- `ai_summary` and `ai_tags` of every addon. Tags come from a fixed vocabulary (`list_tags`): function tags
  say what an addon does, status tags flag its state (`obsolete`, `paid`, `beta`, ...).
- Fork relations with evidence `ai` (other evidence kinds: `github_fork`, `override`).
- Anki Forum topics found with source `ai`.

## Incomplete data

- **Forks.** Fork detection is incomplete: an addon without `forked_from` may still be a fork, and a fork
  family of one member only means no relations are known.
- **Shared repos.** Addons in `github.shared_with` have the same repo, so stars, commits, issues and releases
  repeat across them: count each repo once before summing in `query_sql`. `github.manifest` is the addon's own
  manifest in such a repo, and null when none is clearly its own.
- **Forum topics.** `forum.topic_source` in `get_addon` tells how the topic was matched: `override`,
  `contact_author`, `ai`, `most_linked` or `title_match`.
- **Maintenance label.** `assess_maintenance` labels an addon by dates and the archived flag only; a stable addon
  can go long without a commit and still answer its users, so read its signals too.

## Availability by snapshot

Snapshots are monthly, and older ones lack data that was added to the dataset later:

| Data | Missing in | Affects |
|---|---|---|
| `.ankiaddon` packages | snapshots before 2026-11-01 | `get_addon_packages` (empty), package languages |
| GitHub activity (commits per week, contributors, issue and PR counts, response time, releases) | snapshots before 2026-11-01 | `get_addon`, `assess_maintenance` signals |
| Anki release dates | snapshots before 2026-11-01, most versions before 2.1.22 | `list_anki_versions` |
| Anki releases list | snapshots collected before the dataset published it | `list_anki_versions` (empty) |
| Duplicates (`duplicate_of`, `duplicates`) | snapshots before 2026-11-01 (they need packages) | `get_addon`, `is_duplicate`/`has_duplicates`/`duplicate_of` filters |
| Repo sharing kind (`github.repo_sharing`) | snapshots before 2026-11-01 (it needs authors); `shared_with` is present | `get_addon`, `find_similar_addons` reasons |
| Package license, ClamAV scan | snapshots before 2026-11-01 (they need packages) | `get_addon_packages`, `get_addon` package |
| Addon license from the package (`package_file`, `package_header`) | snapshots before 2026-11-01: the license comes from GitHub, the README or the description only | `license` on cards and in `get_addon` |
| AnkiWeb authors | snapshots collected before authors were tracked | `list_addons_by_author` by `author_id`/`addon_id`, `author_id` filter; use `github_user` instead |

History tools (`get_addon_history`, `diff_snapshots`) download older snapshots on first use, which can take a
minute.

## Licenses

The dataset is CC0. The `.ankiaddon` packages listed by `get_addon_packages` stay under their authors' licenses.

`license` on addon cards and in `get_addon` (and `get_statistics` `group_by=license`) is the addon's license as an
SPDX id, from the first source that names one, strongest first (`license_source`):
`package_file` (the license file in the package), `github` (the repo's license), `package_header` (the license most
`.py` files of the package declare; many copy Anki's AGPL header), `readme`, `description` (possibly a bundled
library's). It is null for about half the addons: none of these sources names a license, which is not proof that
the addon has none. `github.license` is what GitHub detects in the repo, `NOASSERTION` for a license file GitHub
cannot identify. `get_addon_packages` shows each package's own license, which can differ from the repo's.

## Malware scan

`get_addon_packages` and the package in `get_addon` show the ClamAV signatures a package matched (`[]` when clean,
null when not scanned). A match is not proof of malware (it can be a heuristic or a bundled tool), and ClamAV rarely
detects malicious Python, so `[]` does not mean the code is safe.

## Raw content

`get_addon_description` with `format=html` (and the resource `anki-addons://addons/{addon_id}/description.html`)
returns the author's HTML as published on AnkiWeb, without sanitizing.
