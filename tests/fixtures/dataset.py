import json
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from anki_addons_mcp.domain.compatibility import point_to_str, to_point
from anki_addons_mcp.domain.models import (
    AddonDetails,
    AddonPackage,
    AddonReview,
    AnkiRelease,
    LanguageBytes,
    ReviewVote,
    SnapshotInfo,
    Tag,
)

OLD = date(2026, 9, 1)
LATEST = date(2026, 10, 1)

KANJI = 1001
OCCLUSION = 1002
HEATMAP = 1003
LEGACY = 1004
NO_GITHUB = 1005
VIBE = 1006
NEW_ADDON = 1007
REMOVED = 1008
SAME_AUTHOR = 1009

# AnkiWeb author groups of the latest snapshot; the id is the smallest addon id of the group.
ALICE_ADDONS = [KANJI, NO_GITHUB, SAME_AUTHOR]

TAGS = [
    Tag(name="card-creation", group="function", description="Building notes from text"),
    Tag(name="card-templates", group="function", description="Note types and templates"),
    Tag(name="deck-management", group="function", description="Deck tree, subdecks, deck options"),
    Tag(name="dictionary", group="function", description="Lookup, definitions, translation"),
    Tag(name="image-occlusion", group="function", description="Image occlusion"),
    Tag(name="progress-tracking", group="function", description="Progress bars, daily goals"),
    Tag(name="quiz", group="function", description="Multiple choice, typing answers"),
    Tag(name="scheduling", group="function", description="Intervals, ease, reschedule"),
    Tag(name="statistics", group="function", description="Graphs, heatmaps, retention"),
    Tag(name="timer", group="function", description="Pomodoro, session timers"),
    Tag(name="beta", group="status", description="Self-declared alpha, beta or WIP"),
    Tag(name="mobile-compatible", group="status", description="Works on AnkiDroid or AnkiMobile"),
    Tag(name="obsolete", group="status", description="Built into Anki now, or no longer working"),
    Tag(name="paid", group="status", description="Patreon-only, Pro tiers, subscriptions"),
]

# Newest first, as published. The OLD snapshot has no anki_versions file (collected before the table existed).
ANKI_VERSIONS = [AnkiRelease(version=v, point_version=p, release_date=d) for v, p, d in [
    ("26.09.3", 260903, date(2026, 9, 23)), ("26.09", 260900, date(2026, 9, 1)), ("25.02.7", 250207, date(2025, 6, 1)),
    ("23.10", 231000, date(2023, 10, 31)), ("2.1.66", 66, date(2023, 8, 1)), ("2.1.0", 0, None),
]]

# Per addon newest first, as published; the three reviews of 2026-09-25 pin the order of same-day reviews.
_LIKE, _DISLIKE = ReviewVote.LIKE, ReviewVote.DISLIKE
LATEST_REVIEWS: dict[int, list[AddonReview]] = {
    KANJI: [AddonReview(date=date(*d), vote=v, text=t, author_reply=r) for d, v, t, r in [
        ((2026, 9, 25), _LIKE, "Great for kanji study.", None),
        ((2026, 9, 25), _DISLIKE, "Crashes on Anki 25.09 when reviewing.", "Fixed in the next VERSION."),
        ((2026, 9, 25), _LIKE, "", None),
        ((2026, 3, 1), _LIKE, "Stroke order works well.", None),
        ((2025, 1, 10), _DISLIKE, "Too slow.", None),
    ]],
    OCCLUSION: [AddonReview(date=date(2026, 7, 1), vote=_LIKE, text="Essential for anatomy.")],
}
_REVIEW_SCHEMA = pa.schema([("addon_id", pa.int64()), ("date", pa.date32()), ("vote", pa.large_string()),
                            ("text", pa.large_string()), ("author_reply", pa.large_string())])



def _languages(**byte_counts: int) -> list[LanguageBytes]:
    return [LanguageBytes(name=name, bytes=count) for name, count in byte_counts.items()]


# Sorted by addon and minimum Anki version, as published. Only the LATEST snapshot holds packages.
# KANJI's newest package ships Handlebars, which its GitHub repo does not list.
LATEST_PACKAGES: dict[int, list[AddonPackage]] = {
    KANJI: [
        AddonPackage(file_name="0-2021-03-01-aaaaaaaaaaaa.ankiaddon", min_point_version=0, updated=date(2021, 3, 1),
                     size_bytes=5000, config_json='{"font": "serif"}', file_count=2, uncompressed_bytes=12000,
                     python_file_count=1, python_lines=120, files=["__init__.py", "config.json"],
                     language_bytes=_languages(Python=3000, JSON=20)),
        AddonPackage(file_name="250200-2026-09-20-bbbbbbbbbbbb.ankiaddon", min_point_version=250200,
                     updated=date(2026, 9, 20), size_bytes=9000, manifest_json='{"name": "Kanji Helper"}',
                     config_json='{"font": "sans"}', file_count=3, uncompressed_bytes=30000, python_file_count=2,
                     python_lines=450, files=["__init__.py", "manifest.json", "lib/strokes.py"],
                     language_bytes=_languages(JSON=12000, Python=9000, Handlebars=300)),
    ],
    OCCLUSION: [
        AddonPackage(file_name="66-2026-08-01-cccccccccccc.ankiaddon", min_point_version=66, updated=date(2026, 8, 1),
                     size_bytes=70000, file_count=1, uncompressed_bytes=90000, python_file_count=1, python_lines=900,
                     files=["__init__.py"], language_bytes=_languages(Python=60000, JavaScript=20000)),
    ],
}
_PACKAGE_SCHEMA = pa.schema([
    ("addon_id", pa.int64()), ("file_name", pa.string()), ("min_point_version", pa.int64()),
    ("updated", pa.date32()), ("size_bytes", pa.int64()), ("manifest_json", pa.string()), ("config_json", pa.string()),
    ("file_count", pa.int64()), ("uncompressed_bytes", pa.int64()), ("python_file_count", pa.int64()),
    ("python_lines", pa.int64()), ("files", pa.list_(pa.string())),
    ("language_bytes", pa.list_(pa.struct([("name", pa.string()), ("bytes", pa.int64())]))),
])
_DATA_LANGUAGES = {"JSON", "CSV", "YAML"}


def packages_at(snapshot: date) -> dict[int, list[AddonPackage]]:
    return LATEST_PACKAGES if snapshot == LATEST else {}


def _package_summary(addon_id: int) -> dict[str, Any] | None:
    packages = LATEST_PACKAGES.get(addon_id)
    if not packages:
        return None
    newest = packages[-1]
    return {"file_name": newest.file_name, "updated": newest.updated.isoformat() if newest.updated else None,
            "size_bytes": newest.size_bytes, "file_count": newest.file_count,
            "uncompressed_bytes": newest.uncompressed_bytes, "python_file_count": newest.python_file_count,
            "python_lines": newest.python_lines,
            "primary_language": next((lb.name for lb in newest.language_bytes if lb.name not in _DATA_LANGUAGES), None),
            "language_bytes": [lb.model_dump() for lb in newest.language_bytes]}


def reviews_at(snapshot: date) -> dict[int, list[AddonReview]]:
    return {addon_id: [r for r in reviews if r.date < snapshot] for addon_id, reviews in LATEST_REVIEWS.items()}


def _manifest(min_point: int | None, max_point: int | None) -> dict[str, Any]:
    kind = "hard" if max_point and max_point < 0 else "tested" if max_point else "unknown"
    return {"package": "pkg", "name": "Pkg", "conflicts": ["other"], "min_point_version": min_point,
            "max_point_version": max_point, "homepage": None, "mod": 1,
            "min_version": point_to_str(min_point) if min_point is not None else None,
            "max_version": point_to_str(abs(max_point)) if max_point else None, "max_version_kind": kind}


def _addons_list_version(raw: str) -> tuple[int | None, str]:
    if raw.startswith("<="):
        return to_point(raw[2:]), "hard"
    if raw.endswith("~"):
        return to_point(raw), "tested"
    return None, "unknown"


def _branch(low: str | None, high: str | None, updated: str) -> dict[str, Any]:
    if high == "+":
        max_point, kind = None, "open"
    elif high is None:
        max_point, kind = None, "unknown"
    else:
        max_point, kind = to_point(high), "tested" if high.endswith("+") else "hard"
    return {"min_version": low, "max_version": high, "updated": updated, "min_point_version": to_point(low),
            "max_point_version": max_point, "max_version_kind": kind}


def addon(addon_id: int, title: str, *, rating: int = 0, likes: int = 0, dislikes: int = 0,
          update_date: str = "2026-01-01", anki_version: str = "2.1.50~",
          branches: list[tuple[str | None, str | None]] | None = None, description: str = "",
          ai_declaration: list[str] | None = None, lang: str | None = "en",
          github: dict[str, Any] | None = None, forum: dict[str, Any] | None = None,
          ai_summary: str | None = None, ai_tags: list[str] | None = None,
          author_addons: list[int] | None = None,
          forked_from: tuple[int, str] | None = None, package_size_kb: int | None = 10) -> dict[str, Any]:
    point_version, version_kind = _addons_list_version(anki_version)
    group = author_addons or [addon_id]
    return {
        "id": addon_id,
        "anki_web": {
            "title": title,
            "addon_page_url": f"https://ankiweb.net/shared/info/{addon_id}",
            "addon_page_content": f"<html>{title}</html>",
            "contact_author_url": None,
            "description": description,
            "rating": rating,
            "update_date": update_date,
            "anki_version": anki_version,
            "anki_point_version": point_version,
            "anki_version_kind": version_kind,
            "branches": [_branch(lo, hi, update_date) for lo, hi in (branches or [("2.1.50", "+")])],
            "links": [{"url": f"https://example.com/{addon_id}", "section": "description", "count": 1,
                       "texts": ["site"]}],
            "likes": likes,
            "dislikes": dislikes,
            "ai_declaration_markers": ai_declaration or [],
            "description_language": lang,
            "description_language_confidence": 0.9 if lang else None,
            "description_html": f"<p>{description}</p>" if description else None,
            "description_pre_wrap": update_date < "2023-08",
            "other_items_count": len(group) - 1,
            "package_size_kb": package_size_kb,
        },
        "github": github,
        "forum": forum,
        "ai": {"summary": ai_summary, "model": "test-model", "tags": ai_tags or []} if ai_summary or ai_tags else None,
        "author": {"id": min(group), "addon_count": len(group)},
        "forked_from": {"id": forked_from[0], "evidence": forked_from[1]} if forked_from else None,
        "forks": [],
        "package": _package_summary(addon_id),
    }


def _link_forks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fills `forks` as the reverse of `forked_from`, as the dataset does."""
    by_id = {r["id"]: r for r in records}
    for record in by_id.values():
        record["forks"] = []
    for record in sorted(records, key=lambda r: r["id"]):
        relation = record["forked_from"]
        if relation and relation["id"] in by_id:
            by_id[relation["id"]]["forks"].append(record["id"])
    return records


def _activity(user: str) -> dict[str, Any]:
    return {
        "releases": [], "release_count": 0, "latest_release_tag": None, "latest_release_at": None,
        "release_downloads": 0, "contributors": [{"login": user, "contributions": 1}], "contributor_count": 1,
        "weekly_commits": [0] * 52, "commits_last_year": 0, "open_issue_count": 1, "closed_issue_count": 0,
        "open_pr_count": 1, "closed_pr_count": 0, "merged_pr_count": 0, "has_issues_enabled": True,
        "last_issue_closed_at": None, "median_first_response_hours": None, "first_response_sample": 0,
        "outside_pr_merge_share": None, "outside_prs_decided": 0, "outside_prs_merged": 0,
    }


# Snapshots before activity was tracked, and repos GitHub gave no answer about: all null.
NO_ACTIVITY = dict.fromkeys(_activity(""))
KANJI_ACTIVITY = {
    "releases": [
        {"tag_name": "v3.0b1", "name": None, "published_at": "2026-09-25T10:00:00", "prerelease": True, "assets": []},
        {"tag_name": "v2.0", "name": "Version 2", "published_at": "2026-09-20T10:00:00", "prerelease": False,
         "assets": [{"name": "kanji.ankiaddon", "size": 9000, "download_count": 75}]},
    ],
    "release_count": 2, "latest_release_tag": "v2.0", "latest_release_at": "2026-09-20T10:00:00",
    "release_downloads": 75,
    "contributors": [{"login": "alice", "contributions": 40}, {"login": "bob", "contributions": 2}],
    "contributor_count": 2, "weekly_commits": [0] * 51 + [3], "commits_last_year": 3, "closed_issue_count": 6,
    "closed_pr_count": 1, "merged_pr_count": 4, "last_issue_closed_at": "2026-09-10T08:00:00",
    "median_first_response_hours": 12.5, "first_response_sample": 8, "outside_pr_merge_share": 0.75,
    "outside_prs_decided": 4, "outside_prs_merged": 3,
}


def github(user: str, repo: str, *, stars: int = 0, last_commit: str | None = "2026-01-01T10:00:00",
           tests: int | None = 0, actions: int | None = 0, license: str | None = "MIT",
           languages: list[str] | None = None, topics: list[str] | None = None, archived: bool = False,
           manifest: dict[str, Any] | None = None, readme: str | None = None,
           ai_tooling: list[str] | None = None, repo_source: str = "self_reference",
           fork_source: str | None = None, activity: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "user": user, "repo": repo, "repo_source": repo_source, "languages": languages or ["Python"], "stars": stars,
        "last_commit": last_commit,
        "links": [{"url": f"https://github.com/{user}/{repo}", "user": user, "repo": repo}],
        "action_count": actions, "tests_count": tests, "license": license, "fork_count": 1, "open_issues": 2,
        "size_kb": 100, "topics": topics or [], "repo_description": f"{repo} repository", "homepage": None,
        "archived": archived, "pushed_at": last_commit, "created_at": "2020-01-01T00:00:00",
        "primary_language": (languages or ["Python"])[0],
        "language_bytes": [{"name": (languages or ["Python"])[0], "bytes": 1000}],
        "manifest": manifest, "dependencies": ["requests"] if manifest else [], "readme": readme,
        "ai_tooling_markers": ai_tooling or [], "fork_source": fork_source,
        **_activity(user), **(activity or {}),
    }


def forum(topic_id: int, posts: int, topic_source: str = "contact_author") -> dict[str, Any]:
    return {"anki_forum_url": f"https://forums.ankiweb.net/t/topic/{topic_id}", "topic_slug": "topic",
            "topic_id": topic_id, "last_posted_at": "2026-09-15 10:00:00+00:00", "posts_count": posts,
            "topic_source": topic_source}


def latest_records() -> list[dict[str, Any]]:
    # Fork families: KANJI -> NEW_ADDON -> SAME_AUTHOR (a fork of a fork) and KANJI -> NO_GITHUB (a sibling);
    # LEGACY -> VIBE.
    return _link_forks([
        addon(KANJI, "Kanji Helper", rating=130, likes=125, dislikes=5, update_date="2026-09-20",
              anki_version="25.02~", branches=[("2.1.0", "2.1.49"), ("25.02", "+")],
              description="Look up kanji stroke order and readings while reviewing japanese vocabulary.",
              author_addons=ALICE_ADDONS,
              ai_summary="Shows kanji stroke order and readings during review.",
              ai_tags=["dictionary", "card-templates", "mobile-compatible"],
              github=github("alice", "kanji-helper", stars=50, tests=12, actions=2, topics=["japanese", "kanji"],
                            manifest=_manifest(231000, None), readme="# Kanji Helper\nStroke order for kanji.",
                            activity=KANJI_ACTIVITY),
              forum=forum(11, 30)),
        addon(OCCLUSION, "Image Occlusion Plus", rating=320, likes=310, dislikes=10, update_date="2026-08-01",
              anki_version="2.1.66~", branches=[("2.1.66", "25.09+")],
              description="Hide parts of an image to create occlusion cards for anatomy.",
              ai_summary="Creates image occlusion cards.", ai_tags=["image-occlusion", "card-creation"],
              github=github("bob", "image-occlusion", stars=500, tests=40, actions=3, license="GPL-3.0",
                            languages=["Python", "JavaScript"], topics=["image", "occlusion"],
                            manifest=_manifest(66, -250900), readme="# Image Occlusion\nOcclude images."),
              forum=forum(22, 120, topic_source="ai")),
        addon(HEATMAP, "Review Heatmap", rating=84, likes=82, dislikes=2, update_date="2024-01-10",
              anki_version="<=2.1.54", branches=[("2.1.20", "2.1.54")],
              description="Heatmap of review history with streak counter.",
              ai_tags=["statistics", "progress-tracking"],
              github=github("carol", "review-heatmap", stars=200, last_commit="2023-12-01T00:00:00",
                            tests=None, license="AGPL-3.0", topics=["heatmap"], activity=NO_ACTIVITY)),
        addon(LEGACY, "Legacy Scheduler", rating=350, likes=200, dislikes=150, update_date="2019-05-01",
              anki_version="2.1.0~", branches=[("2.1.0", None)], description="Old scheduler tweaks.",
              ai_tags=["scheduling", "obsolete"],
              github=github("dave", "legacy", stars=3, last_commit="2019-04-01T00:00:00", archived=True,
                            license=None)),
        addon(NO_GITHUB, "Simple Timer", rating=15, likes=15, update_date="2025-11-11", anki_version="",
              branches=[("2.1.50", "+")], description="A timer for review sessions. Zeitmesser.", lang="de",
              author_addons=ALICE_ADDONS, package_size_kb=None,
              ai_tags=["timer"], forked_from=(KANJI, "ai")),
        addon(VIBE, "Vibe Deck Tools", rating=4, likes=3, dislikes=1, update_date="2026-09-29",
              anki_version="25.09~", branches=[("25.09", "+")], description="Deck tools vibe-coded with claude.",
              ai_declaration=["claude", "vibe-coded"], ai_tags=["deck-management", "beta"],
              forked_from=(LEGACY, "ai"),
              github=github("erin", "vibe-deck", stars=1, last_commit="2026-09-28T12:00:00", license="MIT",
                            ai_tooling=["claude-code", "agents-md"], topics=["deck"], repo_source="ai",
                            activity={"has_issues_enabled": False})),
        addon(NEW_ADDON, "Kanji Quiz", rating=10, likes=10, update_date="2026-09-25", anki_version="25.02~",
              branches=[("25.02", "+")], description="Quiz yourself on kanji meanings.",
              ai_summary="Kanji meaning quiz.", ai_tags=["quiz", "dictionary"], forked_from=(KANJI, "github_fork"),
              github=github("frank", "kanji-quiz", stars=5, topics=["kanji", "quiz"],
                            fork_source="alice/kanji-helper")),
        addon(SAME_AUTHOR, "Alice Utilities", rating=42, likes=41, dislikes=1, update_date="2026-05-05",
              anki_version="23.10~", branches=[("23.10", "+")], description="Assorted utilities.",
              author_addons=ALICE_ADDONS, forked_from=(NEW_ADDON, "override"),
              github=github("Alice", "alice-utils", stars=20, topics=["utilities"])),
    ])


def old_records() -> list[dict[str, Any]]:
    by_id = {r["id"]: json.loads(json.dumps(r)) for r in latest_records()}
    del by_id[NEW_ADDON]
    by_id[KANJI]["anki_web"].update(rating=100, likes=95, dislikes=5)
    by_id[KANJI]["anki_web"]["update_date"] = "2026-06-01"
    by_id[KANJI]["github"]["stars"] = 40
    by_id[OCCLUSION]["github"]["stars"] = 450
    by_id[REMOVED] = addon(REMOVED, "Gone Addon", rating=7, likes=7, update_date="2022-02-02",
                           description="Will be removed.")
    for record in by_id.values():
        # Snapshots collected before authors were tracked: an all-null column, as published.
        record["author"] = None
        record["package"] = None
        if record["github"]:
            record["github"]["manifest"] = None
            record["github"]["readme"] = None
            record["github"]["dependencies"] = []
            record["github"].update(NO_ACTIVITY)
    return _link_forks(list(by_id.values()))


def _metadata(snapshot: date) -> dict[str, str]:
    return {"data_collection_date": snapshot.isoformat(),
            "report_generation_date": f"{snapshot.isoformat()}T09:30:27", "script_version": "9.9.9"}


def _write_snapshot(folder: Path, records: list[dict[str, Any]], snapshot: date,
                    anki_versions: list[AnkiRelease] | None = None) -> None:
    (folder / "parquet").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records), folder / "parquet" / "data.parquet", compression="zstd")
    pq.write_table(pa.Table.from_pylist([t.model_dump() for t in TAGS]), folder / "parquet" / "tags.parquet")
    reviews = [{"addon_id": addon_id, **r.model_dump()} for addon_id, rs in sorted(reviews_at(snapshot).items())
               for r in rs]
    pq.write_table(pa.Table.from_pylist(reviews, schema=_REVIEW_SCHEMA), folder / "parquet" / "reviews.parquet")
    packages = [{"addon_id": addon_id, **p.model_dump()} for addon_id, ps in sorted(packages_at(snapshot).items())
                for p in ps]
    pq.write_table(pa.Table.from_pylist(packages, schema=_PACKAGE_SCHEMA), folder / "parquet" / "packages.parquet")
    if anki_versions is not None:
        pq.write_table(pa.Table.from_pylist([r.model_dump() for r in anki_versions]),
                       folder / "parquet" / "anki_versions.parquet")
    (folder / "metadata.json").write_text(json.dumps(_metadata(snapshot)))


def write_dataset(root: Path) -> Path:
    _write_snapshot(root / "latest", latest_records(), LATEST, ANKI_VERSIONS)
    _write_snapshot(root / "history" / LATEST.isoformat(), latest_records(), LATEST, ANKI_VERSIONS)
    _write_snapshot(root / "history" / OLD.isoformat(), old_records(), OLD)
    (root / "README.md").write_text("# Test dataset card\n")
    return root


def to_details(record: dict[str, Any]) -> AddonDetails:
    data = json.loads(json.dumps(record))
    gh = data.get("github")
    return AddonDetails.model_validate({
        **data,
        "description": data["anki_web"]["description"] or None,
        "description_html": data["anki_web"]["description_html"],
        "readme": gh.get("readme") if gh else None,
    })


def domain_snapshots() -> dict[date, list[AddonDetails]]:
    return {OLD: [to_details(r) for r in old_records()], LATEST: [to_details(r) for r in latest_records()]}


def domain_infos() -> dict[date, SnapshotInfo]:
    return {d: SnapshotInfo.model_validate({**_metadata(d), "date": d, "latest": d == LATEST}) for d in (OLD, LATEST)}


def domain_tags() -> dict[date, list[Tag]]:
    return {OLD: list(TAGS), LATEST: list(TAGS)}


def domain_anki_versions() -> dict[date, list[AnkiRelease]]:
    return {LATEST: list(ANKI_VERSIONS)}


def domain_reviews() -> dict[date, dict[int, list[AddonReview]]]:
    return {d: reviews_at(d) for d in (OLD, LATEST)}


def domain_packages() -> dict[date, dict[int, list[AddonPackage]]]:
    return {d: packages_at(d) for d in (OLD, LATEST)}
