from datetime import date
from typing import Any

import pytest

from anki_addons_mcp.adapters.memory.repository import InMemoryAddonRepository
from anki_addons_mcp.application.catalog import TopMetric
from anki_addons_mcp.application.forks import ForkRole
from anki_addons_mcp.application.maintenance import MaintenanceLabel
from anki_addons_mcp.application.services import Services, build_services
from anki_addons_mcp.application.similarity import SimilarAddon
from anki_addons_mcp.application.snapshots import parse_snapshot
from anki_addons_mcp.domain.compatibility import Support
from anki_addons_mcp.domain.errors import AddonNotFound, InvalidQuery, SnapshotNotFound
from anki_addons_mcp.domain.models import GroupField, TextKind, VersionKind, approval_score
from anki_addons_mcp.domain.query import AddonFilters, ReviewQuery
from tests.fixtures.dataset import (
    ALICE_ADDONS,
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
    addon,
    domain_infos,
    domain_tags,
    latest_records,
    to_details,
)


@pytest.fixture
def services(memory_repository: InMemoryAddonRepository) -> Services:
    return build_services(memory_repository)


def test_parse_snapshot() -> None:
    assert parse_snapshot(None) is None
    assert parse_snapshot("latest") is None
    assert parse_snapshot("2026-09-01") == OLD
    with pytest.raises(InvalidQuery):
        parse_snapshot("last month")


def test_approval_score() -> None:
    assert approval_score(0, 0) == 0
    assert approval_score(10, 0) < approval_score(100, 0) < 1
    assert approval_score(200, 150) < approval_score(200, 10) < approval_score(200, 0)


def test_snapshot_service(services: Services) -> None:
    assert services.snapshots.resolve(None) == LATEST
    assert services.snapshots.previous(LATEST) == OLD
    assert services.snapshots.previous(OLD) is None


def test_search_rejects_empty_query(services: Services) -> None:
    with pytest.raises(InvalidQuery):
        services.catalog.search("  ")


def test_limit_is_bounded(services: Services) -> None:
    filters = AddonFilters()
    with pytest.raises(InvalidQuery):
        services.catalog.filter(filters, limit=1000)


def test_get_with_texts_and_without_links(services: Services) -> None:
    details = services.catalog.get(KANJI, include_description=True, include_readme=True, max_chars=10,
                                   include_links=False)
    assert details.readme == "# Kanji He"
    assert details.description == "Look up ka"
    assert details.anki_web.links == []
    assert details.github is not None
    assert details.github.links == []
    assert services.catalog.get(KANJI).anki_web.links != []


def test_get_missing(services: Services) -> None:
    with pytest.raises(AddonNotFound):
        services.catalog.get(424242)


def test_reviews(services: Services) -> None:
    assert services.catalog.reviews(KANJI, ReviewQuery(limit=1)).total == 5
    query = ReviewQuery()
    with pytest.raises(AddonNotFound):
        services.catalog.reviews(424242, query)
    with pytest.raises(AddonNotFound):
        services.catalog.reviews(NEW_ADDON, query, OLD)
    too_many = ReviewQuery(limit=101)
    with pytest.raises(InvalidQuery):
        services.catalog.reviews(KANJI, too_many)


def test_text_truncation(services: Services) -> None:
    text = services.catalog.text(KANJI, TextKind.README, max_chars=5)
    assert text.text == "# Kan"
    assert text.truncated
    assert text.total_chars > 5
    assert services.catalog.text(NO_GITHUB, TextKind.README).text is None


def test_top(services: Services) -> None:
    assert [c.id for c in services.catalog.top(TopMetric.STARS, 2).items] == [OCCLUSION, HEATMAP]
    assert [c.id for c in services.catalog.top(TopMetric.FORUM_POSTS, 5).items] == [OCCLUSION, KANJI]
    assert services.catalog.top(TopMetric.RECENTLY_UPDATED, 1).items[0].id == VIBE


def test_by_author_is_case_insensitive(services: Services) -> None:
    assert {c.id for c in services.catalog.by_author("ALICE").items} == {KANJI, SAME_AUTHOR}


def test_by_author_id(services: Services) -> None:
    assert {c.id for c in services.catalog.by_author(author_id=KANJI).items} == set(ALICE_ADDONS)


def test_by_author_of_addon(services: Services) -> None:
    assert {c.id for c in services.catalog.by_author(addon_id=SAME_AUTHOR).items} == set(ALICE_ADDONS)


@pytest.mark.parametrize("arguments", [{}, {"github_user": "alice", "author_id": KANJI}])
def test_by_author_needs_exactly_one_key(services: Services, arguments: dict[str, Any]) -> None:
    with pytest.raises(InvalidQuery, match="exactly one"):
        services.catalog.by_author(**arguments)


def test_by_author_of_addon_without_author_data(services: Services) -> None:
    with pytest.raises(InvalidQuery, match="no AnkiWeb author data"):
        services.catalog.by_author(addon_id=KANJI, snapshot=OLD)


def test_by_author_of_missing_addon(services: Services) -> None:
    with pytest.raises(AddonNotFound):
        services.catalog.by_author(addon_id=424242)


def test_compatibility(services: Services) -> None:
    verdicts = services.compatibility.check([KANJI, OCCLUSION, HEATMAP], "25.10")
    assert [v.verdict for v in verdicts] == [Support.SUPPORTED, Support.LIKELY, Support.UNSUPPORTED]
    assert verdicts[0].manifest_verdict == Support.SUPPORTED
    assert verdicts[1].manifest_verdict == Support.UNSUPPORTED
    assert verdicts[1].manifest_max_version == "25.09"
    assert verdicts[1].manifest_max_version_kind == VersionKind.HARD
    assert verdicts[0].anki_point_version == 251000
    assert "tested the addon up to Anki 25.09" in verdicts[1].explanation
    assert "hard upper limit of Anki 2.1.54" in verdicts[2].explanation
    legacy = services.compatibility.check([LEGACY], "25.02")[0]
    assert legacy.verdict == Support.UNKNOWN
    assert "no upper version" in legacy.explanation
    assert services.compatibility.check([NEW_ADDON], "24.11")[0].explanation.startswith("The addon requires at least")
    with pytest.raises(InvalidQuery):
        services.compatibility.check([KANJI], "latest")
    with pytest.raises(AddonNotFound):
        services.compatibility.check([KANJI, 424242], "25.02")


@pytest.mark.parametrize(("addon_id", "label"), [
    (KANJI, MaintenanceLabel.ACTIVE),
    (SAME_AUTHOR, MaintenanceLabel.ACTIVE),
    (HEATMAP, MaintenanceLabel.ABANDONED),
    (LEGACY, MaintenanceLabel.ABANDONED),
    (NO_GITHUB, MaintenanceLabel.STALE),
])
def test_maintenance(services: Services, addon_id: int, label: MaintenanceLabel) -> None:
    report = services.maintenance.assess(addon_id)
    assert report.label == label
    assert report.as_of == LATEST
    assert report.reasons


def test_maintenance_uses_snapshot_date(services: Services) -> None:
    report = services.maintenance.assess(KANJI, OLD)
    assert report.as_of == OLD
    assert report.signals.days_since_last_activity == (OLD - report.signals.last_activity).days  # type: ignore[operator]


def test_history(services: Services) -> None:
    assert len(services.history.history(KANJI).points) == 2
    with pytest.raises(AddonNotFound):
        services.history.history(424242)
    with pytest.raises(InvalidQuery):
        services.history.history(KANJI, LATEST, OLD)


def test_diff(services: Services) -> None:
    diff = services.history.diff()
    assert (diff.from_snapshot, diff.to_snapshot) == (OLD, LATEST)
    assert [c.id for c in diff.added] == [NEW_ADDON]
    assert [c.id for c in diff.removed] == [REMOVED]
    assert [c.id for c in diff.updated] == [KANJI]
    assert diff.rating_movers[0].id == KANJI
    assert diff.rating_movers[0].rating_delta == 30
    assert [(c.id, c.stars_delta) for c in diff.star_movers] == [(OCCLUSION, 50), (KANJI, 10)]


def test_diff_validation(services: Services) -> None:
    with pytest.raises(InvalidQuery):
        services.history.diff(to=OLD)
    with pytest.raises(InvalidQuery):
        services.history.diff(LATEST, OLD)
    unknown = LATEST.replace(year=2000)
    with pytest.raises(SnapshotNotFound):
        services.history.diff(unknown)


def test_similar(services: Services) -> None:
    similar = services.similarity.similar(KANJI, 5)
    by_id = {s.card.id: s for s in similar}
    assert KANJI not in by_id
    assert similar[0].card.id == NEW_ADDON
    assert any("shared GitHub topics" in r for r in by_id[NEW_ADDON].reasons)
    assert "same AnkiWeb author" in by_id[SAME_AUTHOR].reasons


def test_similar_lists_forks(services: Services) -> None:
    by_id = {s.card.id: s for s in services.similarity.similar(KANJI, 5)}
    assert "forked from this addon" in by_id[NEW_ADDON].reasons


def test_similar_lists_fork_parent(services: Services) -> None:
    by_id = {s.card.id: s for s in services.similarity.similar(VIBE, 5)}
    assert "this addon is a fork of it (ai evidence)" in by_id[LEGACY].reasons


def test_maintenance_points_abandoned_addon_to_its_forks(services: Services) -> None:
    report = services.maintenance.assess(LEGACY)
    assert report.signals.forks == [VIBE]
    assert (f'Another addon was forked from this one and may still be maintained: "Vibe Deck Tools" ({VIBE}).'
            in report.reasons)


def test_maintenance_skips_forks_of_active_addon(services: Services) -> None:
    report = services.maintenance.assess(KANJI)
    assert report.signals.forks == [NO_GITHUB, NEW_ADDON]
    assert not any("forked" in reason for reason in report.reasons)


def test_similar_falls_back_to_github_user_without_authors(services: Services) -> None:
    similar = services.similarity.similar(KANJI, 5, OLD)
    same_author = next(s for s in similar if s.card.id == SAME_AUTHOR)
    assert "same author (alice)" in same_author.reasons


@pytest.fixture
def similar_to_kanji_with_unvoted_quiz() -> list[SimilarAddon]:
    records = latest_records()
    quiz = next(r for r in records if r["id"] == NEW_ADDON)
    quiz["anki_web"].update(rating=0, likes=0, dislikes=0)
    repository = InMemoryAddonRepository({LATEST: [to_details(r) for r in records]},
                                         {LATEST: domain_infos()[LATEST]}, tags={LATEST: domain_tags()[LATEST]})
    return build_services(repository).similarity.similar(KANJI, 10)


def test_similar_ranks_unvoted_last(similar_to_kanji_with_unvoted_quiz: list[SimilarAddon]) -> None:
    assert [s.card.id for s in similar_to_kanji_with_unvoted_quiz][-1] == NEW_ADDON


def test_similar_ranks_voted_before_unvoted(similar_to_kanji_with_unvoted_quiz: list[SimilarAddon]) -> None:
    assert all(s.card.likes + s.card.dislikes > 0 for s in similar_to_kanji_with_unvoted_quiz[:-1])


def test_similar_notes_missing_votes(similar_to_kanji_with_unvoted_quiz: list[SimilarAddon]) -> None:
    assert "no AnkiWeb votes yet" in similar_to_kanji_with_unvoted_quiz[-1].reasons


def test_statistics(services: Services) -> None:
    stats = services.stats.statistics(group_by=[GroupField.LICENSE], top_values=2)
    assert stats.snapshot == LATEST
    assert stats.aggregation.addon_number == 8
    assert stats.groups[0].distinct_values == 4
    assert stats.groups[0].counts == {"MIT": 4, "(none)": 2}


def test_sql_disabled_for_memory(services: Services) -> None:
    assert services.sql is None


def test_tag_vocabulary(services: Services) -> None:
    vocabulary = services.tags.vocabulary()
    assert vocabulary[0].name == "dictionary"
    assert vocabulary[0].addon_count == 2
    assert [t.group for t in vocabulary].index("status") == 10
    assert next(t for t in vocabulary if t.name == "paid").addon_count == 0


def test_unknown_tag_is_rejected(services: Services) -> None:
    unknown_tag = AddonFilters(tags=["stats"])
    with pytest.raises(InvalidQuery, match="Unknown tag 'stats'"):
        services.catalog.filter(unknown_tag)
    unknown_exclude_tag = AddonFilters(exclude_tags=["free"])
    with pytest.raises(InvalidQuery, match="Unknown tag 'free'"):
        services.catalog.search("kanji", filters=unknown_exclude_tag)
    with pytest.raises(InvalidQuery):
        services.catalog.by_tag("nope")


def test_top_and_by_tag(services: Services) -> None:
    assert [c.id for c in services.catalog.top(TopMetric.RATING, 5, tag="dictionary").items] == [KANJI, NEW_ADDON]
    assert services.catalog.by_tag("timer").items[0].id == NO_GITHUB


def test_similar_reports_shared_tags(services: Services) -> None:
    similar = services.similarity.similar(KANJI, 5)
    quiz = next(s for s in similar if s.card.id == NEW_ADDON)
    assert "shared tags: dictionary" in quiz.reasons
    assert not any("mobile-compatible" in reason for s in similar for reason in s.reasons)


def test_fork_family_is_the_same_from_every_member(services: Services) -> None:
    for member in (KANJI, NO_GITHUB, NEW_ADDON, SAME_AUTHOR):
        family = services.forks.family(member)
        assert family.addon_id == member
        assert family.original_id == KANJI
        assert [(m.id, m.depth) for m in family.members] == [(KANJI, 0), (NO_GITHUB, 1), (NEW_ADDON, 1),
                                                             (SAME_AUTHOR, 2)]
        assert not family.truncated
        assert family.notes == []


def test_fork_family_places_each_member(services: Services) -> None:
    by_id = {m.id: m for m in services.forks.family(SAME_AUTHOR).members}
    assert (by_id[KANJI].role, by_id[KANJI].forked_from, by_id[KANJI].evidence) == (ForkRole.ORIGINAL, None, None)
    assert by_id[KANJI].forks == [NO_GITHUB, NEW_ADDON]
    assert (by_id[NEW_ADDON].role, by_id[NEW_ADDON].forked_from, by_id[NEW_ADDON].evidence) == (
        ForkRole.FORK, KANJI, "github_fork")
    assert (by_id[NO_GITHUB].forked_from, by_id[NO_GITHUB].evidence) == (KANJI, "ai")
    assert (by_id[SAME_AUTHOR].forked_from, by_id[SAME_AUTHOR].evidence) == (NEW_ADDON, "override")


def test_fork_family_compares_compatibility_and_maintenance(services: Services) -> None:
    family = services.forks.family(KANJI)
    assert (family.as_of, family.anki_version, family.anki_point_version) == (LATEST, "26.09.3", 260903)
    by_id = {m.id: m for m in family.members}
    assert {m.compatibility for m in family.members} == {Support.SUPPORTED}
    assert by_id[KANJI].manifest_compatibility == Support.SUPPORTED
    assert by_id[NO_GITHUB].manifest_compatibility == Support.UNKNOWN
    assert by_id[NO_GITHUB].maintenance == MaintenanceLabel.STALE
    assert by_id[NEW_ADDON].maintenance == MaintenanceLabel.ACTIVE
    assert by_id[KANJI].last_activity == date(2026, 9, 20)
    assert (by_id[KANJI].likes, by_id[KANJI].dislikes, by_id[KANJI].github_stars) == (125, 5, 50)
    assert by_id[KANJI].approval == round(approval_score(125, 5), 4)
    older = {m.id: m.compatibility for m in services.forks.family(KANJI, anki_version="2.1.30").members}
    assert older == {KANJI: Support.SUPPORTED, NO_GITHUB: Support.UNSUPPORTED, NEW_ADDON: Support.UNSUPPORTED,
                     SAME_AUTHOR: Support.UNSUPPORTED}


def test_fork_family_flags(services: Services) -> None:
    family = services.forks.family(VIBE)
    legacy, vibe = family.members
    assert (legacy.id, legacy.obsolete, legacy.github_archived, legacy.maintenance) == (
        LEGACY, True, True, MaintenanceLabel.ABANDONED)
    assert (vibe.id, vibe.beta, vibe.obsolete, vibe.paid, vibe.evidence) == (VIBE, True, False, False, "ai")


def test_fork_family_of_addon_without_forks(services: Services) -> None:
    family = services.forks.family(OCCLUSION)
    assert [(m.id, m.role, m.depth) for m in family.members] == [(OCCLUSION, ForkRole.ORIGINAL, 0)]
    assert family.original_id == OCCLUSION


def test_fork_family_limit(services: Services) -> None:
    family = services.forks.family(KANJI, limit=2)
    assert [m.id for m in family.members] == [KANJI, NO_GITHUB]
    assert family.truncated
    family = services.forks.family(SAME_AUTHOR, limit=2)
    assert [(m.id, m.role, m.depth) for m in family.members] == [(NEW_ADDON, ForkRole.FORK, 0),
                                                                 (SAME_AUTHOR, ForkRole.FORK, 1)]
    assert (family.original_id, family.truncated) == (None, True)
    with pytest.raises(InvalidQuery):
        services.forks.family(KANJI, limit=101)


def test_fork_family_with_parent_missing_from_snapshot(services: Services) -> None:
    family = services.forks.family(SAME_AUTHOR, snapshot=OLD)
    assert [(m.id, m.role, m.forked_from) for m in family.members] == [(SAME_AUTHOR, ForkRole.FORK, NEW_ADDON)]
    assert family.original_id is None
    assert f"{SAME_AUTHOR} was forked from {NEW_ADDON}, which is not in this snapshot." in family.notes
    assert family.anki_version is None
    assert family.members[0].compatibility is None
    assert [m.id for m in services.forks.family(KANJI, snapshot=OLD).members] == [KANJI, NO_GITHUB]
    assert services.forks.family(KANJI, "25.02", snapshot=OLD).members[0].compatibility == Support.SUPPORTED


def test_fork_family_survives_a_loop_of_fork_links() -> None:
    first, second, third = 2001, 2002, 2003
    records = [addon(first, "First", forked_from=(second, "ai")), addon(second, "Second", forked_from=(first, "ai")),
               addon(third, "Third", forked_from=(first, "override"))]
    records[0]["forks"], records[1]["forks"] = [second, third], [first]
    services = build_services(InMemoryAddonRepository({LATEST: [to_details(r) for r in records]}))
    for member in (first, second, third):
        family = services.forks.family(member)
        assert [(m.id, m.depth) for m in family.members] == [(first, 0), (second, 1), (third, 1)]
        assert family.original_id is None
        assert f"The fork links form a loop; the list starts at its smallest id, {first}." in family.notes


def test_fork_family_of_unknown_addon(services: Services) -> None:
    with pytest.raises(AddonNotFound):
        services.forks.family(999)
