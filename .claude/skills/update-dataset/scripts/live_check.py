"""Run the real server in process against real dataset data and call every tool and resource.

Tools and resources run on the newest and the oldest snapshot; query_sql binds every SQL table on every snapshot,
which is what breaks first when the dataset renames, removes or retypes a column. Prints PASS/FAIL per call and
exits non-zero on any failure.

Usage: uv run python .claude/skills/update-dataset/scripts/live_check.py --revision TAG
       uv run python .claude/skills/update-dataset/scripts/live_check.py --data-dir ~/anki-addons-dataset/bundle
"""
import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from mcp import Client

from anki_addons_mcp.bootstrap import create_services
from anki_addons_mcp.config import Settings
from anki_addons_mcp.interface.mcp.server import build_server

SQL_TABLES = ["addons", "tags", "anki_versions", "reviews", "packages"]


class CauseCapture(logging.Handler):
    """Keeps the root cause of the exceptions the server logs: a client sees only 'Error executing tool <name>'."""

    def __init__(self) -> None:
        super().__init__()
        self.causes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        error = record.exc_info[1] if record.exc_info else None
        while error is not None and error.__cause__ is not None:
            error = error.__cause__
        if error is not None:
            self.causes.append(f"{type(error).__name__}: {error}".replace("\n", " ")[:500])

    def pop(self) -> str:
        cause = self.causes[-1] if self.causes else ""
        self.causes.clear()
        return cause


class Checker:
    def __init__(self, client: Client, capture: CauseCapture) -> None:
        self.client = client
        self.capture = capture
        self.failures: list[str] = []
        self.calls = 0

    def _report(self, label: str, error: str | None, started: float) -> None:
        self.calls += 1
        elapsed = f"{time.monotonic() - started:5.1f}s"
        if error is None:
            print(f"PASS {elapsed} {label}", flush=True)
        else:
            self.failures.append(f"{label}: {error}")
            print(f"FAIL {elapsed} {label}: {error}", flush=True)

    async def tool(self, name: str, **arguments: Any) -> Any:
        label = f"{name}({', '.join(f'{k}={v!r}' for k, v in arguments.items())})"
        started = time.monotonic()
        try:
            result = await self.client.call_tool(name, arguments)
        except Exception as error:  # noqa: BLE001 - every failure is reported, none stops the run
            self._report(label, f"{type(error).__name__}: {error}", started)
            return None
        if result.is_error:
            text = " ".join(getattr(c, "text", "") for c in result.content)[:500]
            cause = self.capture.pop()
            text = f"{text} <- {cause}" if cause else text
            self._report(label, text, started)
            return None
        self._report(label, None, started)
        return result.structured_content

    async def resource(self, uri: str) -> None:
        started = time.monotonic()
        try:
            result = await self.client.read_resource(uri)
            error = None if result.contents else "no contents"
        except Exception as exc:  # noqa: BLE001 - every failure is reported, none stops the run
            error = f"{type(exc).__name__}: {exc}"
        self._report(f"resource {uri}", error, started)


def _items(page: Any) -> list[dict[str, Any]]:
    return page["items"] if page else []


async def check_snapshot(checker: Checker, snapshot: str) -> None:
    """Every data tool on one snapshot, with addons picked from the snapshot itself."""
    tool = checker.tool
    picks = _items(await tool("filter_addons", has_github=True, has_forks=True, limit=1, snapshot=snapshot)) \
        or _items(await tool("filter_addons", has_github=True, limit=1, snapshot=snapshot))
    top = _items(await tool("top_addons", limit=5, snapshot=snapshot))
    if not picks or not top:
        checker.failures.append(f"{snapshot}: no addon to check the per-addon tools with")
        return
    addon = picks[0]
    addon_id, ids = addon["id"], [a["id"] for a in top]
    await tool("search_addons", query="image occlusion", limit=3, snapshot=snapshot)
    await tool("filter_addons", sort_by="anki_version", is_fork=True, limit=3, snapshot=snapshot)
    await tool("filter_addons", language="Python", has_tests=True, tags=["statistics"], limit=3, snapshot=snapshot)
    await tool("get_addon", addon_id=addon_id, include=["description", "readme", "links", "releases"],
               snapshot=snapshot)
    await tool("get_addon_readme", addon_id=addon_id, snapshot=snapshot)
    await tool("get_addon_description", addon_id=addon_id, snapshot=snapshot)
    await tool("get_addon_description", addon_id=addon_id, format="html", snapshot=snapshot)
    await tool("get_addon_reviews", addon_id=ids[0], vote="dislike", snapshot=snapshot)
    await tool("get_addon_packages", addon_id=ids[0], include=["manifest", "config", "files"], snapshot=snapshot)
    versions = await tool("list_anki_versions", snapshot=snapshot)
    anki = versions["result"][0]["version"] if versions and versions.get("result") else "25.02"
    await tool("check_compatibility", addon_ids=ids, anki_version=anki, snapshot=snapshot)
    await tool("assess_maintenance", addon_id=addon_id, snapshot=snapshot)
    await tool("compare_forks", addon_id=addon_id, snapshot=snapshot)
    await tool("find_similar_addons", addon_id=addon_id, limit=5, snapshot=snapshot)
    if snapshot == "latest":  # snapshots collected before AnkiWeb authors were tracked have none
        await tool("list_addons_by_author", addon_id=ids[0], snapshot=snapshot)
    if addon.get("github_user"):
        await tool("list_addons_by_author", github_user=addon["github_user"], snapshot=snapshot)
    await tool("get_statistics", group_by=["license", "primary_language", "package_language", "description_language",
                                           "anki_version", "anki_version_kind", "update_year", "github_topic",
                                           "ai_declaration_marker", "ai_tooling_marker", "ai_tag"], snapshot=snapshot)
    for metric in ("rating", "likes", "stars", "forum_posts", "recently_updated"):
        await tool("top_addons", metric=metric, limit=3, snapshot=snapshot)
    await tool("list_tags", snapshot=snapshot)


async def check_resources(checker: Checker, addon_id: int, github_user: str, tag: str, snapshot: str) -> None:
    values = {"addon_id": str(addon_id), "github_user": github_user, "tag": tag, "snapshot": snapshot}
    for resource in (await checker.client.list_resources()).resources:
        await checker.resource(str(resource.uri))
    for template in (await checker.client.list_resource_templates()).resource_templates:
        await checker.resource(template.uri_template.format(**values))


async def run(settings: Settings, sql_snapshots: str) -> int:
    server = build_server(create_services(settings))
    capture = CauseCapture()
    logging.getLogger().handlers = [capture]  # the server's tracebacks become one cause line per failure
    async with Client(server) as client:
        checker = Checker(client, capture)
        snapshots = await checker.tool("list_snapshots")
        if not snapshots:
            return 1
        dates = sorted(s["date"] for s in snapshots["result"])
        latest = next(s for s in snapshots["result"] if s["latest"])
        print(f"Snapshots: {len(dates)}, {dates[0]} .. {dates[-1]}; latest {json.dumps(latest)}", flush=True)

        for snapshot in dict.fromkeys(["latest", dates[0]]):
            print(f"\n## Tools on snapshot {snapshot}", flush=True)
            await check_snapshot(checker, snapshot)

        print("\n## History tools", flush=True)
        top = _items(await checker.tool("top_addons", limit=1))
        if top:
            await checker.tool("get_addon_history", addon_id=top[0]["id"])
        await checker.tool("diff_snapshots", from_snapshot=dates[0], to_snapshot="latest", limit=5)
        await checker.tool("diff_snapshots", limit=5)

        print("\n## Resources", flush=True)
        card = _items(await checker.tool("filter_addons", has_github=True, limit=1))
        tags = await checker.tool("list_tags")
        tag = tags["result"][0]["name"] if tags and tags.get("result") else "statistics"
        if card:
            await check_resources(checker, card[0]["id"], card[0].get("github_user") or "", tag, dates[-1])

        if settings.sql_enabled:
            picked = dates if sql_snapshots == "all" else sorted({dates[0], dates[-1]})
            print(f"\n## query_sql: every table on {len(picked)} snapshot(s)", flush=True)
            for snapshot in picked:
                for table in SQL_TABLES:
                    await checker.tool("query_sql", sql_query=f"SELECT * FROM {table} LIMIT 1", snapshot=snapshot)

        print(f"\n{checker.calls} calls, {len(checker.failures)} failure(s)")
        for failure in checker.failures:
            print(f"FAILED: {failure}")
        return 1 if checker.failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--revision", help="HF revision to read (tag, branch or SHA)")
    source.add_argument("--data-dir", type=Path, help="A local copy with latest/ and history/<date>/")
    parser.add_argument("--sql-snapshots", choices=["all", "ends"], default="all",
                        help="query_sql on every snapshot, or only the oldest and the newest")
    args = parser.parse_args()
    common: dict[str, Any] = {"refresh_interval_seconds": 0, "warm_up": False, "log_level": "WARNING"}
    settings = (Settings(backend="local_parquet", data_dir=args.data_dir.expanduser(), **common) if args.data_dir
                else Settings(hf_revision=args.revision, **common))
    raise SystemExit(asyncio.run(run(settings, args.sql_snapshots)))


if __name__ == "__main__":
    main()
