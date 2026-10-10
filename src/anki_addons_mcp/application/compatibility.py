from datetime import date

from pydantic import BaseModel

from anki_addons_mcp.application.catalog import CatalogService
from anki_addons_mcp.domain.compatibility import Support, addon_support, manifest_support, parse_version
from anki_addons_mcp.domain.errors import InvalidQuery
from anki_addons_mcp.domain.models import Branch


class CompatibilityVerdict(BaseModel):
    addon_id: int
    title: str
    anki_version: str
    verdict: Support
    matching_branch: Branch | None
    branches: list[Branch]
    manifest_verdict: Support
    manifest_min_point_version: int | None
    manifest_max_point_version: int | None
    explanation: str


_EXPLANATIONS = {
    Support.SUPPORTED: "A branch on AnkiWeb explicitly covers this Anki version.",
    Support.LIKELY: "The newest branch was tested on an older version and is marked open-ended ('+'); "
                    "it probably works but is untested.",
    Support.UNSUPPORTED: "No AnkiWeb branch covers this Anki version.",
    Support.UNKNOWN: "The addon publishes no parsable version information.",
}


class CompatibilityService:
    def __init__(self, catalog: CatalogService):
        self._catalog = catalog

    def check(self, addon_ids: list[int], anki_version: str, snapshot: date | None = None) -> list[CompatibilityVerdict]:
        version = parse_version(anki_version)
        if version is None:
            raise InvalidQuery(f"Cannot parse Anki version '{anki_version}'. Use a form like 25.02 or 2.1.66")
        verdicts = []
        for details in self._catalog.get_many(addon_ids, snapshot):
            branches = details.anki_web.branches
            verdict, branch = addon_support(branches, version)
            manifest = details.github.manifest if details.github else None
            verdicts.append(CompatibilityVerdict(
                addon_id=details.id,
                title=details.anki_web.title,
                anki_version=anki_version,
                verdict=verdict,
                matching_branch=branch,
                branches=branches,
                manifest_verdict=manifest_support(manifest, version),
                manifest_min_point_version=manifest.min_point_version if manifest else None,
                manifest_max_point_version=manifest.max_point_version if manifest else None,
                explanation=_EXPLANATIONS[verdict],
            ))
        return verdicts
