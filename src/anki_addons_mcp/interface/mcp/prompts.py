from mcp.server.mcpserver import MCPServer

from anki_addons_mcp.application.services import Services

AI_NOTE = ("AI summaries and tags (ai_summary, ai_tags) are LLM-generated and can be wrong; say so when you rely "
           "on them and prefer the AnkiWeb description or README for important claims.")
SKIP_TAGS = "exclude_tags=['obsolete', 'no-description']"
WARN_TAGS = "Flag addons tagged paid, beta, fork-or-reupload or service-client."
VERDICTS = ("Verdicts: 'unsupported' above a hard limit means Anki disables the addon; 'likely' means it was "
            "tested on an older Anki and still runs, untested; 'unknown' means the author gave no upper version.")


def register_prompts(mcp: MCPServer, services: Services) -> None:
    @mcp.prompt(description="Recommend addons for a task, checking compatibility and maintenance")
    def find_addon_for_task(task: str, anki_version: str = "") -> str:
        version = f" The user runs Anki {anki_version}." if anki_version else ""
        compat = (f"3. Call check_compatibility with the candidate ids and anki_version={anki_version}. {VERDICTS}\n"
                  if anki_version else "3. Note each candidate's newest supported Anki version (anki_version and "
                                       "anki_version_kind fields).\n")
        narrow = (f" Pass compatible_with_anki={anki_version} to search_addons and filter_addons when the "
                  "unfiltered results are crowded with incompatible addons." if anki_version else "")
        return (
            f"Find Anki addons for this task: {task}.{version}{narrow}\n\n"
            "1. Call search_addons with a few different phrasings of the task (limit 10 each). Also call "
            "list_tags, pick the function tags that match the task and call filter_addons with them "
            f"(tags=[...], {SKIP_TAGS}).\n"
            "2. Pick up to 8 promising candidates; use get_addon (include=['description']) where the card is "
            "not enough to judge.\n"
            f"{compat}"
            "4. Call assess_maintenance for the candidates.\n"
            "5. Recommend 3-5 addons. For each: what it does, why it fits, likes/dislikes, compatibility, "
            "maintenance label, and the AnkiWeb link. Mention trade-offs and warn about stale or "
            f"incompatible ones. {WARN_TAGS}\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Side-by-side comparison of addons")
    def compare_addons(addon_ids: str) -> str:
        return (
            f"Compare these Anki addons: {addon_ids} (comma-separated AnkiWeb ids).\n\n"
            "For each, call get_addon (include=['description']) and assess_maintenance; call "
            "get_addon_readme when the description is thin.\n"
            "Produce a markdown table with columns: addon, main features, likes/dislikes, "
            "supported Anki versions, maintenance label, license, GitHub stars. Then summarize which one "
            "suits which kind of user.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Health report of one addon")
    def addon_health_report(addon_id: str) -> str:
        return (
            f"Write a health report for Anki addon {addon_id}.\n\n"
            "1. get_addon for the basics.\n2. assess_maintenance for activity signals.\n"
            "3. get_addon_history to show the trend of rating, likes and stars.\n"
            "4. Find the newest Anki release known to the dataset with filter_addons(sort_by='anki_version', "
            "limit=1) (its anki_version), then call check_compatibility against it and report the addon's "
            f"anki_version_kind. {VERDICTS}\n"
            "Conclude with a verdict (safe to rely on / use with care / avoid) and the reasons.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Which installed addons will keep working after an Anki upgrade")
    def upgrade_readiness(addon_ids: str, target_anki_version: str) -> str:
        return (
            f"The user plans to upgrade to Anki {target_anki_version} and has these addons installed: "
            f"{addon_ids} (comma-separated AnkiWeb ids).\n\n"
            f"1. Call check_compatibility with all ids and anki_version={target_anki_version}.\n"
            "2. Group the result into: ready (supported), probably fine (likely), blocked (unsupported), "
            f"unknown. {VERDICTS} Mention when the manifest_verdict disagrees with the AnkiWeb verdict.\n"
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
            "2. Call get_statistics for both snapshots with group_by=['license', 'ai_tooling_marker', 'ai_tag'].\n"
            "3. Write sections: headline numbers, notable new addons, rising addons (rating and stars), "
            "removed addons, recently updated popular addons, trends (categories by AI tag, licenses, "
            "AI-assisted development).\n"
            "Link every addon to its AnkiWeb page.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="For addon developers: what already exists for an idea")
    def before_you_build(idea: str) -> str:
        return (
            f"An addon developer is considering building: {idea}\n\n"
            "1. search_addons with several phrasings to find overlapping addons; also call list_tags and "
            "filter_addons with the function tags that fit the idea.\n"
            "2. For the closest 5, call get_addon (include=['readme']) to see languages, dependencies, tests "
            "and manifest, and assess_maintenance.\n"
            "3. Report: existing solutions and how well they are received, how they are implemented, "
            "which are abandoned (fork or replacement opportunity), and gaps the idea could fill.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Portfolio summary of a GitHub author's addons")
    def author_portfolio(github_user: str) -> str:
        return (
            f"Summarize the Anki addons published by GitHub user {github_user}.\n\n"
            "1. list_addons_by_author with github_user; also call it with addon_id of one of the addons to "
            "include the author's addons without a GitHub repository (when the snapshot has author data).\n"
            "2. assess_maintenance for each (up to 15).\n"
            "3. Report: what the author builds, reception (likes/dislikes, stars), upkeep, and the standout "
            "addons.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Best addons in one category (AI tag)")
    def best_in_category(tag: str, anki_version: str = "") -> str:
        compat = (f"4. Call check_compatibility with the candidate ids and anki_version={anki_version}.\n"
                  if anki_version else "4. Note each candidate's supported Anki versions (anki_version field).\n")
        return (
            f"Find the best Anki addons in the category '{tag}'.\n\n"
            "1. Call list_tags to confirm what the tag means (if it is not in the vocabulary, pick the closest "
            "tags and say so).\n"
            f"2. Call filter_addons with tags=['{tag}'], {SKIP_TAGS}, sorted by rating (limit 20); "
            "also call top_addons with tag and metric=stars.\n"
            "3. Call assess_maintenance for the top 8 candidates.\n"
            f"{compat}"
            "5. Recommend 3-5 addons, each with what it does, likes/dislikes, maintenance label and the AnkiWeb "
            f"link. {WARN_TAGS}\n\n" + AI_NOTE
        )

    @mcp.prompt(description="Map of the addon ecosystem by category (AI tags)")
    def category_landscape() -> str:
        return (
            "Describe the landscape of Anki addon categories.\n\n"
            "1. Call list_tags for the categories and their addon counts.\n"
            "2. For the 10 largest function tags, call top_addons with that tag (limit 3).\n"
            "3. For each status tag, note how many addons carry it (e.g. how much of the catalog is obsolete "
            "or paid).\n"
            "4. Report: crowded categories and their leaders, small or under-served categories that could "
            "use new addons, and categories where the leaders look stale (check with assess_maintenance).\n"
            "Link every addon to its AnkiWeb page.\n\n" + AI_NOTE
        )

    @mcp.prompt(description="How ready the addon ecosystem is for an Anki release")
    def anki_release_readiness(anki_version: str) -> str:
        return (
            f"Assess how ready the Anki addon ecosystem is for Anki {anki_version}.\n\n"
            "1. Read anki-addons://dataset/anki-versions if you need the meaning of point versions and kinds.\n"
            "2. Call get_statistics with group_by=['anki_version_kind', 'anki_version'] (top_values 30) for the "
            "overall picture.\n"
            f"3. Call filter_addons with compatible_with_anki={anki_version} (limit 1) for the number of ready "
            f"addons, and with anki_version_at_least={anki_version} for the ones explicitly supporting it.\n"
            "4. Call filter_addons with anki_version_kind='hard', sorted by likes (limit 30), and use "
            f"check_compatibility with anki_version={anki_version} on them to find popular addons that Anki "
            "will disable.\n"
            "5. For the 5 most popular blocked addons, call assess_maintenance and find alternatives with "
            f"find_similar_addons or search_addons using compatible_with_anki={anki_version}.\n"
            "6. Report: headline numbers (ready, untested but likely working, blocked, unknown), notable blocked "
            f"addons with alternatives, and advice for users planning the upgrade. {VERDICTS}\n"
            "Link every addon to its AnkiWeb page.\n\n" + AI_NOTE
        )
