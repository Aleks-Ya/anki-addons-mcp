from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

from anki_addons_mcp import __version__
from anki_addons_mcp.application.services import Services
from anki_addons_mcp.interface.mcp.prompts import register_prompts
from anki_addons_mcp.interface.mcp.resources import register_resources
from anki_addons_mcp.interface.mcp.tools import register_tools

INSTRUCTIONS = """\
Read-only access to the Anki Addons dataset: every addon in the AnkiWeb catalog, enriched with GitHub,
Anki Forum and AI-summary and AI-tag data, published as monthly snapshots.
- Start with search_addons (free text) or filter_addons (structured); both return compact addon cards.
  search_addons accepts every filter of filter_addons, so a query can be narrowed the same way.
- Use get_addon for one full record and get_addon_readme/get_addon_description for long texts.
- check_compatibility, assess_maintenance and find_similar_addons answer "will it work / is it maintained /
  what else is there".
- forked_from/forks link an addon to its forks and the addon it was forked from; filter_addons(fork_of=id)
  finds forks of an abandoned addon. Fork detection is incomplete and its 'ai' evidence may be inaccurate.
- Addons carry AI tags from a fixed vocabulary (list_tags): function tags (what an addon does) and status
  tags (obsolete, paid, beta, ...). Filter with tags/exclude_tags in search_addons and filter_addons.
- list_anki_versions lists the real Anki releases of a snapshot, newest first: use it to check a version a user
  mentions or to find the latest Anki before check_compatibility or the compatible_with_anki filter.
- Every data tool takes an optional snapshot (YYYY-MM-DD from list_snapshots, default latest);
  get_addon_history and diff_snapshots compare snapshots.
- ai_summary and ai_tags fields are LLM-generated and may be inaccurate.
"""


# MCPServer.custom_route requires an async handler, so the async without await is intended
async def _healthz(request: Request) -> JSONResponse:  # NOSONAR
    return JSONResponse({"status": "ok", "version": __version__})


def build_server(services: Services, log_level: str = "INFO") -> MCPServer:
    mcp = MCPServer(
        name="anki-addons",
        title="Anki Addons Dataset",
        instructions=INSTRUCTIONS,
        website_url="https://huggingface.co/datasets/Ya-Alex/anki-addons",
        version=__version__,
        log_level=log_level.upper(),  # type: ignore[arg-type]
    )
    register_tools(mcp, services)
    register_resources(mcp, services)
    register_prompts(mcp)

    mcp.custom_route("/healthz", methods=["GET"])(_healthz)
    return mcp
