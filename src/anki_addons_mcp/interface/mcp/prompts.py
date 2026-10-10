from mcp.server.mcpserver import MCPServer

from anki_addons_mcp.application.services import Services

AI_NOTE = ("AI summaries (ai_summary) are LLM-generated and can be wrong; say so when you rely on them "
           "and prefer the AnkiWeb description or README for important claims.")


def register_prompts(mcp: MCPServer, services: Services) -> None:
    @mcp.prompt(description="Recommend addons for a task, checking compatibility and maintenance")
    def find_addon_for_task(task: str, anki_version: str = "") -> str:
        version = f" The user runs Anki {anki_version}." if anki_version else ""
        compat = (f"3. Call check_compatibility with the candidate ids and anki_version={anki_version}.\n"
                  if anki_version else "3. Note each candidate's supported Anki versions (anki_version field).\n")
        return (
            f"Find Anki addons for this task: {task}.{version}\n\n"
            "1. Call search_addons with a few different phrasings of the task (limit 10 each).\n"
            "2. Pick up to 8 promising candidates; use get_addon (include=['description']) where the card is "
            "not enough to judge.\n"
            f"{compat}"
            "4. Call assess_maintenance for the candidates.\n"
            "5. Recommend 3-5 addons. For each: what it does, why it fits, rating/likes, compatibility, "
            "maintenance label, and the AnkiWeb link. Mention trade-offs and warn about stale or "
            "incompatible ones.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Side-by-side comparison of addons")
    def compare_addons(addon_ids: str) -> str:
        return (
            f"Compare these Anki addons: {addon_ids} (comma-separated AnkiWeb ids).\n\n"
            "For each, call get_addon (include=['description']) and assess_maintenance; call "
            "get_addon_readme when the description is thin.\n"
            "Produce a markdown table with columns: addon, main features, rating (likes/dislikes), "
            "supported Anki versions, maintenance label, license, GitHub stars. Then summarize which one "
            "suits which kind of user.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Health report of one addon")
    def addon_health_report(addon_id: str) -> str:
        return (
            f"Write a health report for Anki addon {addon_id}.\n\n"
            "1. get_addon for the basics.\n2. assess_maintenance for activity signals.\n"
            "3. get_addon_history to show the trend of rating, likes and stars.\n"
            "4. check_compatibility against the newest Anki version mentioned in any branch.\n"
            "Conclude with a verdict (safe to rely on / use with care / avoid) and the reasons.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Which installed addons will keep working after an Anki upgrade")
    def upgrade_readiness(addon_ids: str, target_anki_version: str) -> str:
        return (
            f"The user plans to upgrade to Anki {target_anki_version} and has these addons installed: "
            f"{addon_ids} (comma-separated AnkiWeb ids).\n\n"
            f"1. Call check_compatibility with all ids and anki_version={target_anki_version}.\n"
            "2. Group the result into: ready (supported), probably fine (likely), blocked (unsupported), "
            "unknown.\n"
            "3. For blocked and unknown addons, call assess_maintenance, then find alternatives with "
            f"find_similar_addons or search_addons using compatible_with_anki={target_anki_version}.\n"
            "4. Give a short upgrade recommendation.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Narrative digest of what changed in the addon ecosystem between snapshots")
    def monthly_ecosystem_digest(from_snapshot: str = "", to_snapshot: str = "latest") -> str:
        frm = f"from_snapshot={from_snapshot}, " if from_snapshot else ""
        return (
            "Write a digest of the Anki addon ecosystem.\n\n"
            f"1. Call diff_snapshots with {frm}to_snapshot={to_snapshot}, limit 20.\n"
            "2. Call get_statistics for both snapshots with group_by=['license', 'ai_tooling_marker'].\n"
            "3. Write sections: headline numbers, notable new addons, rising addons (rating and stars), "
            "removed addons, recently updated popular addons, trends (licenses, AI-assisted development).\n"
            "Link every addon to its AnkiWeb page.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="For addon developers: what already exists for an idea")
    def before_you_build(idea: str) -> str:
        return (
            f"An addon developer is considering building: {idea}\n\n"
            "1. search_addons with several phrasings to find overlapping addons.\n"
            "2. For the closest 5, call get_addon (include=['readme']) to see languages, dependencies, tests "
            "and manifest, and assess_maintenance.\n"
            "3. Report: existing solutions and how well they are received, how they are implemented, "
            "which are abandoned (fork or replacement opportunity), and gaps the idea could fill.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Portfolio summary of a GitHub author's addons")
    def author_portfolio(github_user: str) -> str:
        return (
            f"Summarize the Anki addons published by GitHub user {github_user}.\n\n"
            "1. list_addons_by_author.\n2. assess_maintenance for each (up to 15).\n"
            "3. Report: what the author builds, reception (rating, likes, stars), upkeep, and the standout "
            "addons.\n\n" + AI_NOTE
        )
