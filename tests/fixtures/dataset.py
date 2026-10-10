import json
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from anki_addons_mcp.domain.models import AddonDetails, SnapshotInfo

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


def _manifest(min_point: int | None, max_point: int | None) -> dict[str, Any]:
    return {"package": "pkg", "name": "Pkg", "conflicts": ["other"], "min_point_version": min_point,
            "max_point_version": max_point, "homepage": None, "mod": 1}


def addon(addon_id: int, title: str, *, rating: int = 0, likes: int = 0, dislikes: int = 0,
          update_date: str = "2026-01-01", anki_version: str = "2.1.50~",
          branches: list[tuple[str | None, str | None]] | None = None, description: str = "",
          ai_declaration: list[str] | None = None, lang: str | None = "en",
          github: dict[str, Any] | None = None, forum: dict[str, Any] | None = None,
          ai_summary: str | None = None) -> dict[str, Any]:
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
            "branches": [{"min_version": lo, "max_version": hi, "updated": update_date}
                         for lo, hi in (branches or [("2.1.50", "+")])],
            "links": [f"https://example.com/{addon_id}"],
            "likes": likes,
            "dislikes": dislikes,
            "ai_declaration_markers": ai_declaration or [],
            "description_language": lang,
            "description_language_confidence": 0.9 if lang else None,
        },
        "github": github,
        "forum": forum,
        "ai": {"summary": ai_summary, "model": "test-model"} if ai_summary else None,
    }


def github(user: str, repo: str, *, stars: int = 0, last_commit: str | None = "2026-01-01T10:00:00",
           tests: int | None = 0, actions: int | None = 0, license: str | None = "MIT",
           languages: list[str] | None = None, topics: list[str] | None = None, archived: bool = False,
           manifest: dict[str, Any] | None = None, readme: str | None = None,
           ai_tooling: list[str] | None = None) -> dict[str, Any]:
    return {
        "user": user, "repo": repo, "languages": languages or ["Python"], "stars": stars,
        "last_commit": last_commit,
        "links": [{"url": f"https://github.com/{user}/{repo}", "user": user, "repo": repo}],
        "action_count": actions, "tests_count": tests, "license": license, "forks": 1, "open_issues": 2,
        "size_kb": 100, "topics": topics or [], "repo_description": f"{repo} repository", "homepage": None,
        "archived": archived, "pushed_at": last_commit, "created_at": "2020-01-01T00:00:00",
        "primary_language": (languages or ["Python"])[0],
        "language_bytes": [{"name": (languages or ["Python"])[0], "bytes": 1000}],
        "manifest": manifest, "dependencies": ["requests"] if manifest else [], "readme": readme,
        "ai_tooling_markers": ai_tooling or [],
    }


def forum(topic_id: int, posts: int) -> dict[str, Any]:
    return {"anki_forum_url": f"https://forums.ankiweb.net/t/topic/{topic_id}", "topic_slug": "topic",
            "topic_id": topic_id, "last_posted_at": "2026-09-15 10:00:00+00:00", "posts_count": posts}


def latest_records() -> list[dict[str, Any]]:
    return [
        addon(KANJI, "Kanji Helper", rating=120, likes=125, dislikes=5, update_date="2026-09-20",
              anki_version="25.02~", branches=[("2.1.0", "2.1.49"), ("25.02", "+")],
              description="Look up kanji stroke order and readings while reviewing japanese vocabulary.",
              ai_summary="Shows kanji stroke order and readings during review.",
              github=github("alice", "kanji-helper", stars=50, tests=12, actions=2, topics=["japanese", "kanji"],
                            manifest=_manifest(231000, None), readme="# Kanji Helper\nStroke order for kanji."),
              forum=forum(11, 30)),
        addon(OCCLUSION, "Image Occlusion Plus", rating=300, likes=310, dislikes=10, update_date="2026-08-01",
              anki_version="2.1.66~", branches=[("2.1.66", "25.09+")],
              description="Hide parts of an image to create occlusion cards for anatomy.",
              ai_summary="Creates image occlusion cards.",
              github=github("bob", "image-occlusion", stars=500, tests=40, actions=3, license="GPL-3.0",
                            languages=["Python", "JavaScript"], topics=["image", "occlusion"],
                            manifest=_manifest(66, -250900), readme="# Image Occlusion\nOcclude images."),
              forum=forum(22, 120)),
        addon(HEATMAP, "Review Heatmap", rating=80, likes=82, dislikes=2, update_date="2024-01-10",
              anki_version="2.1.20~", branches=[("2.1.20", "2.1.54")],
              description="Heatmap of review history with streak counter.",
              github=github("carol", "review-heatmap", stars=200, last_commit="2023-12-01T00:00:00",
                            tests=None, license="AGPL-3.0", topics=["heatmap"])),
        addon(LEGACY, "Legacy Scheduler", rating=5, likes=6, dislikes=1, update_date="2019-05-01",
              anki_version="2.1.0~", branches=[("2.1.0", None)], description="Old scheduler tweaks.",
              github=github("dave", "legacy", stars=3, last_commit="2019-04-01T00:00:00", archived=True,
                            license=None)),
        addon(NO_GITHUB, "Simple Timer", rating=15, likes=15, update_date="2025-11-11", anki_version="",
              branches=[("2.1.50", "+")], description="A timer for review sessions. Zeitmesser.", lang="de"),
        addon(VIBE, "Vibe Deck Tools", rating=2, likes=3, dislikes=1, update_date="2026-09-29",
              anki_version="25.09~", branches=[("25.09", "+")], description="Deck tools vibe-coded with claude.",
              ai_declaration=["claude", "vibe-coded"],
              github=github("erin", "vibe-deck", stars=1, last_commit="2026-09-28T12:00:00", license="MIT",
                            ai_tooling=["claude-code", "agents-md"], topics=["deck"])),
        addon(NEW_ADDON, "Kanji Quiz", rating=10, likes=10, update_date="2026-09-25", anki_version="25.02~",
              branches=[("25.02", "+")], description="Quiz yourself on kanji meanings.",
              ai_summary="Kanji meaning quiz.",
              github=github("frank", "kanji-quiz", stars=5, topics=["kanji", "quiz"])),
        addon(SAME_AUTHOR, "Alice Utilities", rating=40, likes=41, dislikes=1, update_date="2026-05-05",
              anki_version="23.10~", branches=[("23.10", "+")], description="Assorted utilities.",
              github=github("Alice", "alice-utils", stars=20, topics=["utilities"])),
    ]


def old_records() -> list[dict[str, Any]]:
    by_id = {r["id"]: json.loads(json.dumps(r)) for r in latest_records()}
    del by_id[NEW_ADDON]
    by_id[KANJI]["anki_web"]["rating"] = 100
    by_id[KANJI]["anki_web"]["update_date"] = "2026-06-01"
    by_id[KANJI]["github"]["stars"] = 40
    by_id[OCCLUSION]["github"]["stars"] = 450
    by_id[REMOVED] = addon(REMOVED, "Gone Addon", rating=7, likes=7, update_date="2022-02-02",
                           description="Will be removed.")
    for record in by_id.values():
        if record["github"]:
            record["github"]["manifest"] = None
            record["github"]["readme"] = None
            record["github"]["dependencies"] = []
    return list(by_id.values())


def _metadata(snapshot: date) -> dict[str, str]:
    return {"data_collection_date": snapshot.isoformat(),
            "report_generation_date": f"{snapshot.isoformat()}T09:30:27", "script_version": "9.9.9"}


def _write_snapshot(folder: Path, records: list[dict[str, Any]], snapshot: date) -> None:
    (folder / "parquet").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(records), folder / "parquet" / "data.parquet", compression="zstd")
    (folder / "metadata.json").write_text(json.dumps(_metadata(snapshot)))


def write_dataset(root: Path) -> Path:
    _write_snapshot(root / "latest", latest_records(), LATEST)
    _write_snapshot(root / "history" / LATEST.isoformat(), latest_records(), LATEST)
    _write_snapshot(root / "history" / OLD.isoformat(), old_records(), OLD)
    (root / "README.md").write_text("# Test dataset card\n")
    return root


def to_details(record: dict[str, Any]) -> AddonDetails:
    data = json.loads(json.dumps(record))
    gh = data.get("github")
    return AddonDetails.model_validate({
        **data,
        "description": data["anki_web"]["description"] or None,
        "readme": gh.get("readme") if gh else None,
    })


def domain_snapshots() -> dict[date, list[AddonDetails]]:
    return {OLD: [to_details(r) for r in old_records()], LATEST: [to_details(r) for r in latest_records()]}


def domain_infos() -> dict[date, SnapshotInfo]:
    return {d: SnapshotInfo.model_validate({**_metadata(d), "date": d, "latest": d == LATEST}) for d in (OLD, LATEST)}
