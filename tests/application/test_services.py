import pytest

from anki_addons_mcp.adapters.memory.repository import InMemoryAddonRepository
from anki_addons_mcp.application.catalog import TopMetric
from anki_addons_mcp.application.maintenance import MaintenanceLabel
from anki_addons_mcp.application.services import Services, build_services
from anki_addons_mcp.application.snapshots import parse_snapshot
from anki_addons_mcp.domain.compatibility import Support
from anki_addons_mcp.domain.errors import AddonNotFound, InvalidQuery, SnapshotNotFound
from anki_addons_mcp.domain.models import GroupField, TextKind, VersionKind
from anki_addons_mcp.domain.query import AddonFilters
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


@pytest.fixture
def services(memory_repository: InMemoryAddonRepository) -> Services:
    return build_services(memory_repository)


def test_parse_snapshot() -> None:
    assert parse_snapshot(None) is None
    assert parse_snapshot("latest") is None
    assert parse_snapshot("2026-09-01") == OLD
    with pytest.raises(InvalidQuery):
        parse_snapshot("last month")


def test_snapshot_service(services: Services) -> None:
    assert services.snapshots.resolve(None) == LATEST
    assert services.snapshots.previous(LATEST) == OLD
    assert services.snapshots.previous(OLD) is None


def test_search_rejects_empty_query(services: Services) -> None:
    with pytest.raises(InvalidQuery):
        services.catalog.search("  ")


def test_limit_is_bounded(services: Services) -> None:
    with pytest.raises(InvalidQuery):
        services.catalog.filter(AddonFilters(), limit=1000)


def test_get_with_texts_and_without_links(services: Services) -> None:
    details = services.catalog.get(KANJI, include_description=True, include_readme=True, max_chars=10,
                                   include_links=False)
    assert details.readme == "# Kanji He"
    assert details.description == "Look up ka"
    assert details.anki_web.links == []
    assert details.github is not None and details.github.links == []
    assert services.catalog.get(KANJI).anki_web.links != []


def test_get_missing(services: Services) -> None:
    with pytest.raises(AddonNotFound):
        services.catalog.get(424242)


def test_text_truncation(services: Services) -> None:
    text = services.catalog.text(KANJI, TextKind.README, max_chars=5)
    assert text.text == "# Kan" and text.truncated and text.total_chars > 5
    assert services.catalog.text(NO_GITHUB, TextKind.README).text is None


def test_top(services: Services) -> None:
    assert [c.id for c in services.catalog.top(TopMetric.STARS, 2).items] == [OCCLUSION, HEATMAP]
    assert [c.id for c in services.catalog.top(TopMetric.FORUM_POSTS, 5).items] == [OCCLUSION, KANJI]
    assert services.catalog.top(TopMetric.RECENTLY_UPDATED, 1).items[0].id == VIBE


def test_by_author_is_case_insensitive(services: Services) -> None:
    assert {c.id for c in services.catalog.by_author("ALICE").items} == {KANJI, SAME_AUTHOR}


def test_compatibility(services: Services) -> None:
    verdicts = services.compatibility.check([KANJI, OCCLUSION, HEATMAP], "25.10")
    assert [v.verdict for v in verdicts] == [Support.SUPPORTED, Support.LIKELY, Support.UNSUPPORTED]
    assert verdicts[0].manifest_verdict == Support.SUPPORTED
    assert verdicts[1].manifest_verdict == Support.UNSUPPORTED
    assert verdicts[1].manifest_max_version == "25.09" and verdicts[1].manifest_max_version_kind == VersionKind.HARD
    assert verdicts[0].anki_point_version == 251000
    assert "tested the addon up to Anki 25.09" in verdicts[1].explanation
    assert "hard upper limit of Anki 2.1.54" in verdicts[2].explanation
    legacy = services.compatibility.check([LEGACY], "25.02")[0]
    assert legacy.verdict == Support.UNKNOWN and "no upper version" in legacy.explanation
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
    assert diff.rating_movers[0].id == KANJI and diff.rating_movers[0].rating_delta == 20
    assert [(c.id, c.stars_delta) for c in diff.star_movers] == [(OCCLUSION, 50), (KANJI, 10)]


def test_diff_validation(services: Services) -> None:
    with pytest.raises(InvalidQuery):
        services.history.diff(to=OLD)
    with pytest.raises(InvalidQuery):
        services.history.diff(LATEST, OLD)
    with pytest.raises(SnapshotNotFound):
        services.history.diff(LATEST.replace(year=2000))


def test_similar(services: Services) -> None:
    similar = services.similarity.similar(KANJI, 5)
    by_id = {s.card.id: s for s in similar}
    assert KANJI not in by_id
    assert similar[0].card.id == NEW_ADDON
    assert any("shared GitHub topics" in r for r in by_id[NEW_ADDON].reasons)
    assert any("same author" in r for r in by_id[SAME_AUTHOR].reasons)


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
    assert vocabulary[0].name == "dictionary" and vocabulary[0].addon_count == 2
    assert [t.group for t in vocabulary].index("status") == 10
    assert next(t for t in vocabulary if t.name == "paid").addon_count == 0


def test_unknown_tag_is_rejected(services: Services) -> None:
    with pytest.raises(InvalidQuery, match="Unknown tag 'stats'"):
        services.catalog.filter(AddonFilters(tags=["stats"]))
    with pytest.raises(InvalidQuery, match="Unknown tag 'free'"):
        services.catalog.search("kanji", filters=AddonFilters(exclude_tags=["free"]))
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
