from enum import StrEnum

from anki_addons_mcp.domain.models import Branch, Manifest

Version = tuple[int, ...]


class Support(StrEnum):
    SUPPORTED = "supported"
    LIKELY = "likely"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


_RANK = {Support.SUPPORTED: 3, Support.LIKELY: 2, Support.UNSUPPORTED: 1, Support.UNKNOWN: 0}


def parse_version(value: str | None) -> Version | None:
    if not value:
        return None
    cleaned = value.strip().rstrip("+~").strip()
    parts = cleaned.split(".")
    if not cleaned or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _cmp(left: Version, right: Version) -> int:
    width = max(len(left), len(right))
    a = left + (0,) * (width - len(left))
    b = right + (0,) * (width - len(right))
    return (a > b) - (a < b)


def branch_support(branch: Branch, version: Version) -> Support:
    low = parse_version(branch.min_version)
    if low is None:
        return Support.UNKNOWN
    if _cmp(version, low) < 0:
        return Support.UNSUPPORTED
    high_raw = (branch.max_version or "").strip()
    if not high_raw:
        return Support.SUPPORTED if _cmp(version, low) == 0 else Support.UNSUPPORTED
    if high_raw == "+":
        return Support.SUPPORTED
    high = parse_version(high_raw)
    if high is None:
        return Support.UNKNOWN
    if _cmp(version, high) <= 0:
        return Support.SUPPORTED
    return Support.LIKELY if high_raw.endswith("+") else Support.UNSUPPORTED


def addon_support(branches: list[Branch], version: Version) -> tuple[Support, Branch | None]:
    best: tuple[Support, Branch | None] = (Support.UNKNOWN, None)
    for branch in branches:
        support = branch_support(branch, version)
        if _RANK[support] > _RANK[best[0]]:
            best = (support, branch)
    return best


def is_compatible(branches: list[Branch], version_text: str) -> bool:
    version = parse_version(version_text)
    if version is None:
        return False
    return addon_support(branches, version)[0] in (Support.SUPPORTED, Support.LIKELY)


def point_version(version: Version) -> int:
    if len(version) >= 2 and version[0] == 2 and version[1] == 1:
        return version[2] if len(version) > 2 else 0
    padded = version + (0,) * (3 - len(version))
    return padded[0] * 10000 + padded[1] * 100 + padded[2]


def manifest_support(manifest: Manifest | None, version: Version) -> Support:
    if manifest is None or (manifest.min_point_version is None and manifest.max_point_version is None):
        return Support.UNKNOWN
    point = point_version(version)
    if manifest.min_point_version is not None and point < manifest.min_point_version:
        return Support.UNSUPPORTED
    maximum = manifest.max_point_version
    if maximum is None or maximum == 0:
        return Support.SUPPORTED
    if maximum < 0:
        return Support.SUPPORTED if point <= -maximum else Support.LIKELY
    return Support.SUPPORTED if point <= maximum else Support.UNSUPPORTED
