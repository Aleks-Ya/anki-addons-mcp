from datetime import date

import pytest

from anki_addons_mcp.adapters.hf_parquet.repository import DuckDbAddonRepository
from anki_addons_mcp.adapters.memory.repository import InMemoryAddonRepository
from anki_addons_mcp.domain.errors import SnapshotNotFound
from anki_addons_mcp.domain.models import NONE_GROUP, GroupField, TextKind
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.domain.query import AddonFilters, AddonQuery, SortField
from tests.fixtures.dataset import (
    HEATMAP,
    KANJI,
    LATEST,
    LEGACY,
    NEW_ADDON,
    NO_GITHUB,
    OCCLUSION,
    OLD,
    REMOVED,
    SAME_AUTHOR,
    VIBE,
)


def ids(repository: AddonRepository, query: AddonQuery, snapshot: date | None = None) -> list[int]:
    return [card.id for card in repository.find(query, snapshot).items]


def test_list_snapshots(repository: AddonRepository) -> None:
    snapshots = repository.list_snapshots()
    assert [s.date for s in snapshots] == [OLD, LATEST]
    assert [s.latest for s in snapshots] == [False, True]
    assert snapshots[1].script_version == "9.9.9"


def test_get_addon(repository: AddonRepository) -> None:
    details = repository.get_addon(OCCLUSION)
    assert details is not None
    assert details.anki_web.title == "Image Occlusion Plus"
    assert details.github is not None and details.github.stars == 500
    assert details.github.manifest is not None and details.github.manifest.max_point_version == -250900
    assert details.github.url == "https://github.com/bob/image-occlusion"
    assert details.forum is not None and details.forum.posts_count == 120
    assert details.ai is not None and details.ai.summary == "Creates image occlusion cards."
    assert details.description is None and details.readme is None


def test_get_addon_missing(repository: AddonRepository) -> None:
    assert repository.get_addon(424242) is None


def test_get_addon_in_old_snapshot_with_drifted_schema(repository: AddonRepository) -> None:
    details = repository.get_addon(KANJI, OLD)
    assert details is not None
    assert details.anki_web.rating == 100
    assert details.github is not None and details.github.manifest is None
    assert repository.get_text(KANJI, TextKind.README, OLD) is None


def test_unknown_snapshot(repository: AddonRepository) -> None:
    with pytest.raises(SnapshotNotFound):
        repository.get_addon(KANJI, date(2000, 1, 1))


def test_get_addons_keeps_order_and_skips_missing(repository: AddonRepository) -> None:
    assert [d.id for d in repository.get_addons([HEATMAP, 424242, KANJI, HEATMAP])] == [HEATMAP, KANJI]


def test_get_text(repository: AddonRepository) -> None:
    assert repository.get_text(KANJI, TextKind.README) == "# Kanji Helper\nStroke order for kanji."
    assert "stroke order" in (repository.get_text(KANJI, TextKind.DESCRIPTION) or "")
    assert repository.get_text(NO_GITHUB, TextKind.README) is None


def test_find_default_sort_is_rating(repository: AddonRepository) -> None:
    page = repository.find(AddonQuery(limit=3))
    assert [c.id for c in page.items] == [OCCLUSION, KANJI, HEATMAP]
    assert page.total == 8


def test_find_paging(repository: AddonRepository) -> None:
    page = repository.find(AddonQuery(limit=2, offset=6))
    assert [c.id for c in page.items] == [LEGACY, VIBE]
    assert page.total == 8
    assert repository.find(AddonQuery(limit=5, offset=50)).items == []


def test_find_text(repository: AddonRepository) -> None:
    found = ids(repository, AddonQuery(text="kanji", limit=10))
    assert set(found) == {KANJI, NEW_ADDON}
    assert all(c.score is not None for c in repository.find(AddonQuery(text="kanji")).items)


def test_find_text_in_old_snapshot(repository: AddonRepository) -> None:
    assert set(ids(repository, AddonQuery(text="kanji"), OLD)) == {KANJI}


def test_find_text_no_match(repository: AddonRepository) -> None:
    assert repository.find(AddonQuery(text="xylophone")).total == 0


@pytest.mark.parametrize(("filters", "expected"), [
    (AddonFilters(min_rating=80), {OCCLUSION, KANJI, HEATMAP}),
    (AddonFilters(min_stars=100), {OCCLUSION, HEATMAP}),
    (AddonFilters(has_github=False), {NO_GITHUB}),
    (AddonFilters(has_tests=True), {KANJI, OCCLUSION}),
    (AddonFilters(has_forum=True), {KANJI, OCCLUSION}),
    (AddonFilters(license="gpl-3.0"), {OCCLUSION}),
    (AddonFilters(language="javascript"), {OCCLUSION}),
    (AddonFilters(description_language="DE"), {NO_GITHUB}),
    (AddonFilters(github_user="alice"), {KANJI, SAME_AUTHOR}),
    (AddonFilters(topic="Kanji"), {KANJI, NEW_ADDON}),
    (AddonFilters(updated_after=date(2026, 9, 1)), {KANJI, VIBE, NEW_ADDON}),
    (AddonFilters(updated_before=date(2020, 1, 1)), {LEGACY}),
    (AddonFilters(archived=True), {LEGACY}),
    (AddonFilters(has_ai_declaration=True), {VIBE}),
    (AddonFilters(has_ai_tooling=True), {VIBE}),
    (AddonFilters(compatible_with_anki="25.02"), {KANJI, OCCLUSION, NO_GITHUB, NEW_ADDON, SAME_AUTHOR}),
    (AddonFilters(compatible_with_anki="2.1.0"), {KANJI, LEGACY}),
    (AddonFilters(addon_ids=[KANJI, LEGACY, 424242]), {KANJI, LEGACY}),
    (AddonFilters(has_github=True, min_rating=50, has_tests=False), {HEATMAP}),
])
def test_find_filters(repository: AddonRepository, filters: AddonFilters, expected: set[int]) -> None:
    page = repository.find(AddonQuery(filters=filters, limit=None))
    assert {c.id for c in page.items} == expected
    assert page.total == len(expected)


def test_find_text_and_filter(repository: AddonRepository) -> None:
    assert ids(repository, AddonQuery(text="kanji", filters=AddonFilters(min_rating=50))) == [KANJI]


@pytest.mark.parametrize(("sort", "first"), [
    (SortField.STARS, OCCLUSION),
    (SortField.LIKES, OCCLUSION),
    (SortField.UPDATE_DATE, VIBE),
    (SortField.LAST_COMMIT, VIBE),
    (SortField.FORUM_POSTS, OCCLUSION),
])
def test_find_sort(repository: AddonRepository, sort: SortField, first: int) -> None:
    assert ids(repository, AddonQuery(sort=sort, limit=1)) == [first]


def test_find_sort_puts_nulls_last_in_both_directions(repository: AddonRepository) -> None:
    ascending = ids(repository, AddonQuery(sort=SortField.STARS, descending=False, limit=None))
    assert ascending[0] == VIBE
    assert ascending[-1] == NO_GITHUB


def test_card_fields(repository: AddonRepository) -> None:
    card = repository.find(AddonQuery(filters=AddonFilters(addon_ids=[KANJI]))).items[0]
    assert card.title == "Kanji Helper"
    assert card.github_user == "alice" and card.github_stars == 50
    assert card.license == "MIT" and card.forum_posts_count == 30
    assert "ai_model" not in card.model_dump()
    no_github = repository.find(AddonQuery(filters=AddonFilters(addon_ids=[NO_GITHUB]))).items[0]
    assert no_github.anki_version is None and no_github.github_stars is None


def test_history(repository: AddonRepository) -> None:
    points = repository.get_history(KANJI)
    assert [(p.snapshot, p.rating, p.github_stars) for p in points] == [(OLD, 100, 40), (LATEST, 120, 50)]
    added = repository.get_history(NEW_ADDON)
    assert [p.present for p in added] == [False, True]
    assert [p.snapshot for p in repository.get_history(KANJI, from_=LATEST)] == [LATEST]
    assert [p.present for p in repository.get_history(REMOVED)] == [True, False]


def test_aggregation(repository: AddonRepository) -> None:
    aggregation = repository.get_aggregation()
    assert aggregation.addon_number == 8
    assert aggregation.addon_with_github_number == 7
    assert aggregation.addon_with_anki_forum_page_number == 2
    assert aggregation.addon_with_unit_tests_number == 2
    assert repository.get_aggregation(OLD).addon_number == 8


def test_group_counts(repository: AddonRepository) -> None:
    assert repository.group_counts(GroupField.LICENSE) == {
        "MIT": 4, "GPL-3.0": 1, "AGPL-3.0": 1, NONE_GROUP: 2}
    topics = repository.group_counts(GroupField.GITHUB_TOPIC)
    assert topics["kanji"] == 2 and topics[NONE_GROUP] == 2
    assert repository.group_counts(GroupField.AI_TOOLING_MARKER) == {
        "claude-code": 1, "agents-md": 1, NONE_GROUP: 7}
    assert repository.group_counts(GroupField.UPDATE_YEAR)["2026"] == 5
    assert repository.group_counts(GroupField.ANKI_VERSION)[NONE_GROUP] == 1


def test_documentation(repository: AddonRepository) -> None:
    assert "Test dataset card" in repository.get_documentation()


@pytest.mark.parametrize("snapshot", [OLD, LATEST])
def test_adapters_return_identical_records(memory_repository: InMemoryAddonRepository,
                                           duckdb_repository: DuckDbAddonRepository, snapshot: date) -> None:
    all_ids = ids(memory_repository, AddonQuery(limit=None), snapshot)
    assert ids(duckdb_repository, AddonQuery(limit=None), snapshot) == all_ids
    assert duckdb_repository.get_addons(all_ids, snapshot) == memory_repository.get_addons(all_ids, snapshot)
    duck_cards = duckdb_repository.find(AddonQuery(limit=None), snapshot).items
    assert duck_cards == memory_repository.find(AddonQuery(limit=None), snapshot).items


def test_list_tags(repository: AddonRepository) -> None:
    tags = repository.list_tags()
    assert [t.name for t in tags][:2] == ["card-creation", "card-templates"]
    assert {t.group for t in tags} == {"function", "status"}
    assert [t.name for t in repository.list_tags(OLD)] == [t.name for t in tags]
    with pytest.raises(SnapshotNotFound):
        repository.list_tags(date(2000, 1, 1))


def test_ai_tags_on_cards_and_details(repository: AddonRepository) -> None:
    details = repository.get_addon(HEATMAP)
    assert details is not None and details.ai is not None
    assert details.ai.summary is None and details.ai.tags == ["statistics", "progress-tracking"]
    card = repository.find(AddonQuery(filters=AddonFilters(addon_ids=[KANJI]))).items[0]
    assert card.ai_tags == ["dictionary", "card-templates", "mobile-compatible"]
    no_tags = repository.get_addon(SAME_AUTHOR)
    assert no_tags is not None and no_tags.ai is None


def test_filter_by_tags(repository: AddonRepository) -> None:
    assert set(ids(repository, AddonQuery(filters=AddonFilters(tags=["dictionary"])))) == {KANJI, NEW_ADDON}
    assert ids(repository, AddonQuery(filters=AddonFilters(tags=["Dictionary", "QUIZ"]))) == [NEW_ADDON]
    assert ids(repository, AddonQuery(filters=AddonFilters(tags=["dictionary", "statistics"]))) == []


def test_exclude_tags(repository: AddonRepository) -> None:
    found = set(ids(repository, AddonQuery(filters=AddonFilters(exclude_tags=["obsolete", "beta"]), limit=None)))
    assert found == {KANJI, OCCLUSION, HEATMAP, NO_GITHUB, NEW_ADDON, SAME_AUTHOR}


def test_group_counts_by_ai_tag(repository: AddonRepository) -> None:
    counts = repository.group_counts(GroupField.AI_TAG)
    assert counts["dictionary"] == 2
    assert counts["statistics"] == 1
    assert counts[NONE_GROUP] == 1
    assert "paid" not in counts


def test_search_matches_tags(repository: AddonRepository) -> None:
    assert ids(repository, AddonQuery(text="statistics")) == [HEATMAP]
