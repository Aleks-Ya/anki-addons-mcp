import json

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError
from pydantic import BaseModel, TypeAdapter

from anki_addons_mcp.application.services import Services
from anki_addons_mcp.application.snapshots import parse_snapshot
from anki_addons_mcp.application.tags import TagUsage
from anki_addons_mcp.domain.models import AddonDetails, AnkiRelease, SnapshotInfo, TextKind
from anki_addons_mcp.interface.mcp.errors import parse_addon_id, resource_errors

JSON = "application/json"
_SNAPSHOTS = TypeAdapter(list[SnapshotInfo])
_TAGS = TypeAdapter(list[TagUsage])
_ANKI_RELEASES = TypeAdapter(list[AnkiRelease])

ANKI_VERSIONS_GUIDE = """# Anki versions in the dataset

Every addon keeps the raw version strings as AnkiWeb shows them and parsed values that follow Anki's own rules.

## Point version
Anki encodes a version as one sortable integer (as strings, `2.1.66` > `23.10` would sort wrongly):

| Version | Point version | Rule |
|---|---|---|
| `2.1.66` | `66` | `2.1.x` -> `x` |
| `23.10` | `231000` | `YY.MM` -> `YYMM00` |
| `25.09.2` | `250902` | `YY.MM.PP` -> `YYMMPP` |
| `26.05b1` | `260500` | a beta/rc suffix decodes to its base release |

## Max version kind
| Kind | Meaning |
|---|---|
| `hard` | Anki disables the addon on any newer version |
| `tested` | the author tested up to this version; newer versions still run it |
| `open` | no upper limit |
| `unknown` | the author gave no upper version |

## Fields
- `anki_web.anki_version` (raw: `B~` tested, `<=B` hard, empty unknown), `anki_point_version`, `anki_version_kind`:
  the newest supported version from the AnkiWeb addons list.
- `anki_web.branches[]`: `min_version`/`max_version` raw (`A-B+` tested, `A-B` hard, `A+` open, `A` unknown),
  `min_point_version`, `max_point_version`, `max_version_kind`.
- `github.manifest`: `min_point_version`/`max_point_version` as the author wrote them (negative max = hard),
  `min_version`, `max_version`, `max_version_kind` parsed. Manifest values are often odd (`260000` gives
  "26.00"), so the AnkiWeb branches are the more reliable source.

## Anki releases
list_anki_versions (and anki-addons://anki-versions for the latest snapshot) lists the stable Anki releases from
2.1.0 on as known when the snapshot was collected, newest first: `version` as Anki writes it and its
`point_version`. Betas and release candidates are left out. query_sql has the same rows as the `anki_versions`
table. Snapshots collected before the dataset published the list have none.

## Compatibility verdicts (check_compatibility, compatible_with_anki)
- supported: a branch covers the version (between min and max, or open-ended).
- likely: the version is above a `tested` max; Anki still runs the addon, untested.
- unsupported: below every branch minimum, or above a `hard` max.
- unknown: the only matching branch has no upper version, or there is no version data.
The compatible_with_anki filter keeps supported and likely addons.
"""


def _json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def register_resources(mcp: MCPServer, services: Services) -> None:
    catalog = services.catalog

    @mcp.resource("anki-addons://dataset/readme", mime_type="text/markdown",
                  description="Dataset card: sources, field meanings, AI-summary disclaimer, license")
    def dataset_readme() -> str:
        return services.repository.get_documentation()

    @mcp.resource("anki-addons://dataset/schema", mime_type=JSON,
                  description="JSON Schema of the full addon record returned by get_addon")
    def dataset_schema() -> str:
        return json.dumps(AddonDetails.model_json_schema(mode="serialization"), indent=2)

    @mcp.resource("anki-addons://dataset/anki-versions", mime_type="text/markdown",
                  description="How Anki versions are encoded (point versions, hard/tested/open/unknown kinds) "
                              "and how compatibility verdicts are derived")
    def anki_versions() -> str:
        return ANKI_VERSIONS_GUIDE

    @mcp.resource("anki-addons://snapshots", mime_type=JSON, description="Available snapshots with metadata")
    def snapshots() -> str:
        with resource_errors():
            return _SNAPSHOTS.dump_json(services.snapshots.list(), indent=2).decode()

    @mcp.resource("anki-addons://snapshots/{snapshot}/metadata", mime_type=JSON,
                  description="Metadata of one snapshot (YYYY-MM-DD or 'latest')")
    def snapshot_metadata(snapshot: str) -> str:
        with resource_errors():
            return _json(services.snapshots.get(parse_snapshot(snapshot)))

    @mcp.resource("anki-addons://snapshots/{snapshot}/aggregation", mime_type=JSON,
                  description="Addon counts of one snapshot (YYYY-MM-DD or 'latest')")
    def snapshot_aggregation(snapshot: str) -> str:
        with resource_errors():
            return _json(services.stats.aggregation(services.snapshots.resolve(parse_snapshot(snapshot))))

    @mcp.resource("anki-addons://addons/{addon_id}", mime_type=JSON,
                  description="Full record of an addon in the latest snapshot")
    def addon(addon_id: str) -> str:
        with resource_errors():
            return _json(catalog.get(parse_addon_id(addon_id), include_links=False))

    @mcp.resource("anki-addons://addons/{addon_id}/readme", mime_type="text/markdown",
                  description="GitHub README of an addon")
    def addon_readme(addon_id: str) -> str:
        with resource_errors():
            text = catalog.text(parse_addon_id(addon_id), TextKind.README).text
        if text is None:
            raise ResourceNotFoundError(f"Addon {addon_id} has no README")
        return text

    @mcp.resource("anki-addons://addons/{addon_id}/description", mime_type="text/plain",
                  description="AnkiWeb description of an addon")
    def addon_description(addon_id: str) -> str:
        with resource_errors():
            text = catalog.text(parse_addon_id(addon_id), TextKind.DESCRIPTION).text
        if text is None:
            raise ResourceNotFoundError(f"Addon {addon_id} has no description")
        return text

    @mcp.resource("anki-addons://addons/{addon_id}/description.html", mime_type="text/html",
                  description="AnkiWeb description of an addon as the author's HTML (not sanitized)")
    def addon_description_html(addon_id: str) -> str:
        with resource_errors():
            text = catalog.text(parse_addon_id(addon_id), TextKind.DESCRIPTION_HTML).text
        if text is None:
            raise ResourceNotFoundError(f"Addon {addon_id} has no HTML description")
        return text

    @mcp.resource("anki-addons://addons/{addon_id}/history", mime_type=JSON,
                  description="Rating, likes and stars of an addon across snapshots")
    def addon_history(addon_id: str) -> str:
        with resource_errors():
            return _json(services.history.history(parse_addon_id(addon_id)))

    @mcp.resource("anki-addons://authors/{github_user}", mime_type=JSON,
                  description="Addons of a GitHub user in the latest snapshot")
    def author(github_user: str) -> str:
        with resource_errors():
            return _json(catalog.by_author(github_user))

    @mcp.resource("anki-addons://tags", mime_type=JSON,
                  description="AI tag vocabulary with descriptions and addon counts (latest snapshot)")
    def tags() -> str:
        with resource_errors():
            return _TAGS.dump_json(services.tags.vocabulary(), indent=2).decode()

    @mcp.resource("anki-addons://anki-versions", mime_type=JSON,
                  description="Stable Anki releases from 2.1.0 on, newest first, with point versions (latest snapshot)")
    def anki_releases() -> str:
        with resource_errors():
            return _ANKI_RELEASES.dump_json(services.repository.list_anki_versions(), indent=2).decode()

    @mcp.resource("anki-addons://tags/{tag}", mime_type=JSON,
                  description="Addons with an AI tag in the latest snapshot")
    def tag_addons(tag: str) -> str:
        with resource_errors():
            return _json(catalog.by_tag(tag))
