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
| AnkiWeb authors | snapshots collected before authors were tracked | `list_addons_by_author` by `author_id`/`addon_id`, `author_id` filter; use `github_user` instead |

History tools (`get_addon_history`, `diff_snapshots`) download older snapshots on first use, which can take a
minute.

## Licenses

The dataset is CC0. The `.ankiaddon` packages listed by `get_addon_packages` stay under their authors' licenses.

## Raw content

`get_addon_description` with `format=html` (and the resource `anki-addons://addons/{addon_id}/description.html`)
returns the author's HTML as published on AnkiWeb, without sanitizing.
