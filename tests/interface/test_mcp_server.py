import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from mcp import Client

from anki_addons_mcp.application.services import build_services
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.interface.mcp.server import build_server
from tests.fixtures.dataset import KANJI, NEW_ADDON, OCCLUSION, OLD

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    "search_addons", "filter_addons", "get_addon", "get_addon_readme", "get_addon_description",
    "check_compatibility", "assess_maintenance", "find_similar_addons", "list_addons_by_author",
    "get_addon_history", "diff_snapshots", "get_statistics", "top_addons", "list_snapshots",
}
EXPECTED_PROMPTS = {
    "find_addon_for_task", "compare_addons", "addon_health_report", "upgrade_readiness",
    "monthly_ecosystem_digest", "before_you_build", "author_portfolio",
}


@pytest.fixture
async def client(repository: AddonRepository) -> AsyncIterator[Client]:
    async with Client(build_server(build_services(repository))) as connected:
        yield connected


async def call(client: Client, tool: str, **arguments: Any) -> Any:
    result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


async def test_lists_tools_with_read_only_annotations(client: Client, repository: AddonRepository) -> None:
    tools = (await client.list_tools()).tools
    names = {t.name for t in tools}
    sql_expected = {"query_sql"} if type(repository).__name__.startswith("DuckDb") else set()
    assert names == EXPECTED_TOOLS | sql_expected
    for tool in tools:
        assert tool.annotations is not None and tool.annotations.read_only_hint
        assert tool.description


async def test_lists_prompts_and_resources(client: Client) -> None:
    assert {p.name for p in (await client.list_prompts()).prompts} == EXPECTED_PROMPTS
    assert {str(r.uri) for r in (await client.list_resources()).resources} == {
        "anki-addons://dataset/readme", "anki-addons://dataset/schema", "anki-addons://snapshots"}
    templates = {t.uri_template for t in (await client.list_resource_templates()).resource_templates}
    assert "anki-addons://addons/{addon_id}" in templates
    assert len(templates) == 7


async def test_search(client: Client) -> None:
    page = await call(client, "search_addons", query="kanji", limit=5)
    assert {item["id"] for item in page["items"]} == {KANJI, NEW_ADDON}


async def test_filter(client: Client) -> None:
    page = await call(client, "filter_addons", has_tests=True, sort_by="stars", limit=5)
    assert [item["id"] for item in page["items"]] == [OCCLUSION, KANJI]
    assert page["total"] == 2


async def test_filter_by_date(client: Client) -> None:
    page = await call(client, "filter_addons", updated_after="2026-09-21", limit=5)
    assert page["total"] == 2


async def test_get_addon_include(client: Client) -> None:
    plain = await call(client, "get_addon", addon_id=KANJI)
    assert plain["description"] is None and plain["anki_web"]["links"] == []
    full = await call(client, "get_addon", addon_id=KANJI, include=["readme", "links"])
    assert full["readme"].startswith("# Kanji Helper")
    assert full["anki_web"]["links"]
    assert full["ai"]["provenance"]


async def test_get_addon_unknown_is_tool_error(client: Client) -> None:
    result = await client.call_tool("get_addon", {"addon_id": 424242})
    assert result.is_error
    assert "424242" in result.content[0].text


async def test_invalid_snapshot_is_tool_error(client: Client) -> None:
    result = await client.call_tool("search_addons", {"query": "kanji", "snapshot": "yesterday"})
    assert result.is_error
    assert "YYYY-MM-DD" in result.content[0].text


async def test_texts(client: Client) -> None:
    readme = await call(client, "get_addon_readme", addon_id=KANJI, max_chars=100)
    assert readme["kind"] == "readme" and not readme["truncated"]
    description = await call(client, "get_addon_description", addon_id=KANJI)
    assert "kanji" in description["text"]


async def test_compatibility_and_maintenance(client: Client) -> None:
    verdicts = await call(client, "check_compatibility", addon_ids=[KANJI, OCCLUSION], anki_version="25.10")
    assert [v["verdict"] for v in verdicts["result"]] == ["supported", "likely"]
    report = await call(client, "assess_maintenance", addon_id=KANJI)
    assert report["label"] == "active"


async def test_history_diff_and_snapshots(client: Client) -> None:
    snapshots = await call(client, "list_snapshots")
    assert [s["date"] for s in snapshots["result"]] == [OLD.isoformat(), "2026-10-01"]
    history = await call(client, "get_addon_history", addon_id=KANJI)
    assert [p["rating"] for p in history["points"]] == [100, 120]
    diff = await call(client, "diff_snapshots")
    assert diff["added_count"] == 1 and diff["removed_count"] == 1


async def test_statistics_top_similar_author(client: Client) -> None:
    stats = await call(client, "get_statistics", group_by=["license"])
    assert stats["aggregation"]["addon_number"] == 8
    top = await call(client, "top_addons", metric="stars", limit=1)
    assert top["items"][0]["id"] == OCCLUSION
    similar = await call(client, "find_similar_addons", addon_id=KANJI, limit=3)
    assert similar["result"][0]["card"]["id"] == NEW_ADDON
    author = await call(client, "list_addons_by_author", github_user="alice")
    assert author["total"] == 2


async def test_query_sql_when_available(client: Client, repository: AddonRepository) -> None:
    if not type(repository).__name__.startswith("DuckDb"):
        pytest.skip("adapter has no SQL capability")
    result = await call(client, "query_sql", sql_query="SELECT count(*) AS n FROM addons WHERE has_github")
    assert result["rows"] == [[7]]
    rejected = await client.call_tool("query_sql", {"sql_query": "SELECT * FROM read_csv('/etc/passwd')"})
    assert rejected.is_error


async def test_resources(client: Client) -> None:
    record = json.loads((await client.read_resource(f"anki-addons://addons/{KANJI}")).contents[0].text)
    assert record["id"] == KANJI
    readme = (await client.read_resource(f"anki-addons://addons/{KANJI}/readme")).contents[0].text
    assert readme.startswith("# Kanji Helper")
    history = json.loads((await client.read_resource(f"anki-addons://addons/{KANJI}/history")).contents[0].text)
    assert len(history["points"]) == 2
    aggregation = json.loads((await client.read_resource("anki-addons://snapshots/latest/aggregation")).contents[0].text)
    assert aggregation["addon_number"] == 8
    metadata = json.loads((await client.read_resource(f"anki-addons://snapshots/{OLD}/metadata")).contents[0].text)
    assert metadata["date"] == OLD.isoformat()
    schema = json.loads((await client.read_resource("anki-addons://dataset/schema")).contents[0].text)
    assert "anki_web" in schema["properties"]
    card = (await client.read_resource("anki-addons://dataset/readme")).contents[0].text
    assert "Test dataset card" in card
    author = json.loads((await client.read_resource("anki-addons://authors/alice")).contents[0].text)
    assert author["total"] == 2


async def test_missing_resource_is_error(client: Client) -> None:
    with pytest.raises(Exception, match="424242"):
        await client.read_resource("anki-addons://addons/424242")


async def test_prompt(client: Client) -> None:
    prompt = await client.get_prompt("upgrade_readiness", {"addon_ids": "1,2", "target_anki_version": "25.02"})
    text = prompt.messages[0].content.text  # type: ignore[union-attr]
    assert "check_compatibility" in text and "25.02" in text
