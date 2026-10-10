import json

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError
from pydantic import BaseModel, TypeAdapter

from anki_addons_mcp.application.services import Services
from anki_addons_mcp.application.snapshots import parse_snapshot
from anki_addons_mcp.domain.models import AddonDetails, SnapshotInfo, TextKind
from anki_addons_mcp.interface.mcp.errors import parse_addon_id, resource_errors

JSON = "application/json"
_SNAPSHOTS = TypeAdapter(list[SnapshotInfo])


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
