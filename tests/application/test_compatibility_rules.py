import pytest

from anki_addons_mcp.domain.compatibility import (
    Support,
    addon_support,
    branch_support,
    manifest_support,
    parse_version,
    point_version,
)
from anki_addons_mcp.domain.models import Branch, Manifest


@pytest.mark.parametrize(("text", "expected"), [
    ("25.02", (25, 2)), ("2.1.66~", (2, 1, 66)), ("26.05+", (26, 5)), ("", None), ("+", None), ("abc", None),
])
def test_parse_version(text: str, expected: tuple[int, ...] | None) -> None:
    assert parse_version(text) == expected


@pytest.mark.parametrize(("low", "high", "version", "expected"), [
    ("2.1.1", "+", "25.02", Support.SUPPORTED),
    ("25.02.5", "+", "25.02", Support.UNSUPPORTED),
    ("2.1.0", "2.1.49", "2.1.49", Support.SUPPORTED),
    ("2.1.0", "2.1.49", "2.1.50", Support.UNSUPPORTED),
    ("2.1.1", "26.05+", "26.05", Support.SUPPORTED),
    ("2.1.1", "26.05+", "26.10", Support.LIKELY),
    ("2.1.0", None, "2.1", Support.SUPPORTED),
    ("2.1.0", None, "2.1.1", Support.UNSUPPORTED),
    (None, "+", "25.02", Support.UNKNOWN),
])
def test_branch_support(low: str | None, high: str | None, version: str, expected: Support) -> None:
    parsed = parse_version(version)
    assert parsed is not None
    assert branch_support(Branch(min_version=low, max_version=high), parsed) == expected


def test_addon_support_picks_best_branch() -> None:
    branches = [Branch(min_version="2.1.0", max_version="2.1.49"), Branch(min_version="23.10", max_version="+")]
    support, branch = addon_support(branches, (25, 2))
    assert support == Support.SUPPORTED and branch == branches[1]
    assert addon_support([], (25, 2)) == (Support.UNKNOWN, None)


def test_point_version() -> None:
    assert point_version((2, 1, 66)) == 66
    assert point_version((23, 10)) == 231000
    assert point_version((25, 9, 2)) == 250902


@pytest.mark.parametrize(("low", "high", "version", "expected"), [
    (None, None, (25, 2), Support.UNKNOWN),
    (66, None, (2, 1, 50), Support.UNSUPPORTED),
    (66, None, (25, 2), Support.SUPPORTED),
    (66, 231000, (25, 2), Support.UNSUPPORTED),
    (66, -231000, (25, 2), Support.LIKELY),
])
def test_manifest_support(low: int | None, high: int | None, version: tuple[int, ...], expected: Support) -> None:
    assert manifest_support(Manifest(min_point_version=low, max_point_version=high), version) == expected
