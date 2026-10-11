import pytest

from anki_addons_mcp.domain.compatibility import (
    Support,
    addon_support,
    branch_support,
    manifest_support,
    point_to_str,
    require_point,
    to_point,
)
from anki_addons_mcp.domain.errors import InvalidQuery
from anki_addons_mcp.domain.models import Branch, Manifest, VersionKind

HARD, TESTED, OPEN, UNKNOWN = VersionKind.HARD, VersionKind.TESTED, VersionKind.OPEN, VersionKind.UNKNOWN


@pytest.mark.parametrize(("text", "expected"), [
    ("2.1.66", 66), ("2.1.66~", 66), ("2.1", 0), ("23.10", 231000), ("25.09.2", 250902), ("26.05b1", 260500),
    ("26.05+", 260500), ("", None), ("+", None), ("abc", None), ("25", None), (None, None),
])
def test_to_point(text: str | None, expected: int | None) -> None:
    assert to_point(text) == expected


def test_require_point_rejects_garbage() -> None:
    assert require_point("25.02") == 250200
    with pytest.raises(InvalidQuery):
        require_point("latest")


@pytest.mark.parametrize(("point", "expected"), [(66, "2.1.66"), (231000, "23.10"), (250902, "25.09.2")])
def test_point_to_str(point: int, expected: str) -> None:
    assert point_to_str(point) == expected


@pytest.mark.parametrize(("low", "high", "kind", "version", "expected"), [
    (1, None, OPEN, "25.02", Support.SUPPORTED),
    (250205, None, OPEN, "25.02", Support.UNSUPPORTED),
    (0, 49, HARD, "2.1.49", Support.SUPPORTED),
    (0, 49, HARD, "2.1.50", Support.UNSUPPORTED),
    (1, 260500, TESTED, "26.05", Support.SUPPORTED),
    (1, 260500, TESTED, "26.10", Support.LIKELY),
    (0, None, UNKNOWN, "2.1", Support.SUPPORTED),
    (0, None, UNKNOWN, "2.1.1", Support.UNKNOWN),
    (None, None, OPEN, "25.02", Support.UNKNOWN),
    (1, None, HARD, "25.02", Support.UNKNOWN),
])
def test_branch_support(low: int | None, high: int | None, kind: VersionKind, version: str,
                        expected: Support) -> None:
    branch = Branch(min_point_version=low, max_point_version=high, max_version_kind=kind)
    assert branch_support(branch, require_point(version)) == expected


def test_addon_support_picks_best_branch() -> None:
    branches = [Branch(min_point_version=0, max_point_version=49, max_version_kind=HARD),
                Branch(min_point_version=231000, max_version_kind=OPEN)]
    support, branch = addon_support(branches, 250200)
    assert support == Support.SUPPORTED
    assert branch == branches[1]
    assert addon_support([], 250200) == (Support.UNKNOWN, None)


def test_branch_kind_defaults_to_unknown() -> None:
    assert Branch.model_validate({"max_version_kind": None}).max_version_kind == UNKNOWN


@pytest.mark.parametrize(("low", "high", "kind", "point", "expected"), [
    (None, None, UNKNOWN, 250200, Support.UNKNOWN),
    (66, None, UNKNOWN, 50, Support.UNSUPPORTED),
    (66, None, UNKNOWN, 250200, Support.SUPPORTED),
    (66, 0, UNKNOWN, 250200, Support.SUPPORTED),
    (66, 231000, TESTED, 250200, Support.LIKELY),
    (66, 231000, TESTED, 231000, Support.SUPPORTED),
    (66, -231000, HARD, 250200, Support.UNSUPPORTED),
    (66, -231000, HARD, 230600, Support.SUPPORTED),
])
def test_manifest_support(low: int | None, high: int | None, kind: VersionKind, point: int,
                          expected: Support) -> None:
    manifest = Manifest(min_point_version=low, max_point_version=high, max_version_kind=kind)
    assert manifest_support(manifest, point) == expected
