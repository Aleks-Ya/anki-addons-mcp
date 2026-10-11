from datetime import date

from pydantic import BaseModel

from anki_addons_mcp.application.catalog import CatalogService
from anki_addons_mcp.domain.compatibility import Support, addon_support, manifest_support, point_to_str, require_point
from anki_addons_mcp.domain.models import AnkiWebInfo, Branch, VersionKind


class CompatibilityVerdict(BaseModel):
    addon_id: int
    title: str
    anki_version: str
    anki_point_version: int
    verdict: Support
    matching_branch: Branch | None
    branches: list[Branch]
    manifest_verdict: Support
    manifest_min_point_version: int | None
    manifest_max_point_version: int | None
    manifest_min_version: str | None
    manifest_max_version: str | None
    manifest_max_version_kind: VersionKind | None
    explanation: str


def _unsupported_reason(anki_web: AnkiWebInfo, point: int) -> str:
    branches = anki_web.branches
    lows = [b.min_point_version for b in branches if b.min_point_version is not None]
    if lows and point < min(lows):
        return f"The addon requires at least Anki {point_to_str(min(lows))}."
    hard = [b.max_point_version for b in branches
            if b.max_version_kind == VersionKind.HARD and b.max_point_version is not None]
    if anki_web.anki_version_kind == VersionKind.HARD and anki_web.anki_point_version is not None:
        hard.append(anki_web.anki_point_version)
    if hard:
        return f"The addon has a hard upper limit of Anki {point_to_str(max(hard))}; Anki disables it on newer versions."
    return "No AnkiWeb branch covers this Anki version."


def _explain(verdict: Support, branch: Branch | None, anki_web: AnkiWebInfo, point: int) -> str:
    branches = anki_web.branches
    if verdict == Support.SUPPORTED:
        return "A branch on AnkiWeb covers this Anki version."
    if verdict == Support.LIKELY and branch is not None and branch.max_point_version is not None:
        return (f"The author tested the addon up to Anki {point_to_str(branch.max_point_version)}; newer versions still run it, "
                "but it is untested there.")
    open_ended = [b for b in branches if b.max_version_kind == VersionKind.UNKNOWN
                  and b.min_point_version is not None and b.min_point_version <= point]
    if verdict == Support.UNKNOWN and open_ended:
        return (f"The branch starting at Anki {open_ended[-1].min_version} gives no upper version, so support "
                "for this version is unknown.")
    if verdict == Support.UNSUPPORTED:
        return _unsupported_reason(anki_web, point)
    return "The addon publishes no parsable version information."


class CompatibilityService:
    def __init__(self, catalog: CatalogService):
        self._catalog = catalog

    def check(self, addon_ids: list[int], anki_version: str, snapshot: date | None = None) -> list[CompatibilityVerdict]:
        point = require_point(anki_version)
        verdicts = []
        for details in self._catalog.get_many(addon_ids, snapshot):
            branches = details.anki_web.branches
            verdict, branch = addon_support(branches, point)
            manifest = details.github.manifest if details.github else None
            verdicts.append(CompatibilityVerdict(
                addon_id=details.id,
                title=details.anki_web.title,
                anki_version=anki_version,
                anki_point_version=point,
                verdict=verdict,
                matching_branch=branch,
                branches=branches,
                manifest_verdict=manifest_support(manifest, point),
                manifest_min_point_version=manifest.min_point_version if manifest else None,
                manifest_max_point_version=manifest.max_point_version if manifest else None,
                manifest_min_version=manifest.min_version if manifest else None,
                manifest_max_version=manifest.max_version if manifest else None,
                manifest_max_version_kind=manifest.max_version_kind if manifest else None,
                explanation=_explain(verdict, branch, details.anki_web, point),
            ))
        return verdicts
