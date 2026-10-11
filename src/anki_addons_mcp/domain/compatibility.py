import re
from enum import StrEnum

from anki_addons_mcp.domain.errors import InvalidQuery
from anki_addons_mcp.domain.models import Branch, Manifest, VersionKind

_VERSION = re.compile(r"\s*(\d+)\.(\d+)(?:\.(\d+))?")


class Support(StrEnum):
    SUPPORTED = "supported"
    LIKELY = "likely"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


_RANK = {Support.SUPPORTED: 3, Support.LIKELY: 2, Support.UNSUPPORTED: 1, Support.UNKNOWN: 0}


def to_point(value: str | None) -> int | None:
    """Anki's point version: 2.1.x -> x, YY.MM[.PP] -> YYMMPP; a beta/rc suffix decodes to its base release."""
    match = _VERSION.match(value or "")
    if not match:
        return None
    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    if major == 2:
        return patch
    return major * 10_000 + minor * 100 + patch


def require_point(value: str) -> int:
    point = to_point(value)
    if point is None:
        raise InvalidQuery(f"Cannot parse Anki version '{value}'. Use a form like 25.02 or 2.1.66")
    return point


def point_to_str(point: int) -> str:
    if point <= 99:
        return f"2.1.{point}"
    version = f"{point // 10_000:02}.{point // 100 % 100:02}"
    return f"{version}.{point % 100}" if point % 100 else version


def branch_support(branch: Branch, point: int) -> Support:
    low = branch.min_point_version
    if low is None:
        return Support.UNKNOWN
    if point < low:
        return Support.UNSUPPORTED
    high = branch.max_point_version
    match branch.max_version_kind:
        case VersionKind.OPEN:
            return Support.SUPPORTED
        case VersionKind.HARD if high is not None:
            return Support.SUPPORTED if point <= high else Support.UNSUPPORTED
        case VersionKind.TESTED if high is not None:
            return Support.SUPPORTED if point <= high else Support.LIKELY
        case VersionKind.UNKNOWN:
            return Support.SUPPORTED if point == low else Support.UNKNOWN
    return Support.UNKNOWN


def addon_support(branches: list[Branch], point: int) -> tuple[Support, Branch | None]:
    best: tuple[Support, Branch | None] = (Support.UNKNOWN, None)
    for branch in branches:
        support = branch_support(branch, point)
        if _RANK[support] > _RANK[best[0]]:
            best = (support, branch)
    return best


def is_compatible(branches: list[Branch], point: int) -> bool:
    return addon_support(branches, point)[0] in (Support.SUPPORTED, Support.LIKELY)


def manifest_support(manifest: Manifest | None, point: int) -> Support:
    if manifest is None or (manifest.min_point_version is None and manifest.max_point_version is None):
        return Support.UNKNOWN
    if manifest.min_point_version is not None and point < manifest.min_point_version:
        return Support.UNSUPPORTED
    high = abs(manifest.max_point_version or 0)
    match manifest.max_version_kind:
        case VersionKind.HARD:
            return Support.SUPPORTED if point <= high else Support.UNSUPPORTED
        case VersionKind.TESTED:
            return Support.SUPPORTED if point <= high else Support.LIKELY
    return Support.SUPPORTED
