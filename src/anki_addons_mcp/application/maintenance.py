from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from anki_addons_mcp.application.catalog import CatalogService
from anki_addons_mcp.application.snapshots import SnapshotService
from anki_addons_mcp.domain.errors import AddonNotFound
from anki_addons_mcp.domain.models import AddonDetails, GithubInfo


class MaintenanceLabel(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class MaintenanceThresholds(BaseModel):
    active_days: int = 180
    stale_days: int = 730


class MaintenanceSignals(BaseModel):
    ankiweb_update_date: str | None
    github_last_commit: str | None = None
    github_pushed_at: str | None = None
    github_archived: bool | None = None
    github_open_issues: int | None = Field(default=None, description="Open issues and open pull requests together")
    github_open_issue_count: int | None = None
    github_closed_issue_count: int | None = None
    github_open_pr_count: int | None = None
    github_merged_pr_count: int | None = None
    github_has_issues_enabled: bool | None = None
    github_last_issue_closed_at: str | None = None
    github_median_first_response_hours: float | None = Field(
        default=None, description="Items nobody answered are left out, so a low median can hide ignored issues")
    github_first_response_sample: int | None = None
    github_outside_pr_merge_share: float | None = None
    github_outside_prs_decided: int | None = None
    github_commits_last_year: int | None = None
    github_contributor_count: int | None = None
    github_latest_release_at: str | None = None
    github_tests_count: int | None = None
    github_action_count: int | None = None
    forum_last_posted_at: str | None
    forum_posts_count: int | None
    last_activity: date | None
    days_since_last_activity: int | None
    forked_from: int | None = Field(default=None, description="Addon this one was forked from")
    forks: list[int] = Field(default_factory=list, description="Addons forked from this one")


class MaintenanceReport(BaseModel):
    addon_id: int
    title: str
    as_of: date
    label: MaintenanceLabel
    reasons: list[str]
    signals: MaintenanceSignals


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError:
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None


def _last_activity(details: AddonDetails) -> date | None:
    github = details.github
    dates = [details.anki_web.update_date, github.last_commit, github.pushed_at] if github \
        else [details.anki_web.update_date]
    activity = [d for d in map(_to_date, dates) if d is not None]
    return max(activity) if activity else None


def _github_signals(github: GithubInfo | None) -> dict[str, Any]:
    if github is None:
        return {}
    return {
        "github_last_commit": github.last_commit,
        "github_pushed_at": github.pushed_at,
        "github_archived": github.archived,
        "github_open_issues": github.open_issues,
        "github_open_issue_count": github.open_issue_count,
        "github_closed_issue_count": github.closed_issue_count,
        "github_open_pr_count": github.open_pr_count,
        "github_merged_pr_count": github.merged_pr_count,
        "github_has_issues_enabled": github.has_issues_enabled,
        "github_last_issue_closed_at": github.last_issue_closed_at,
        "github_median_first_response_hours": github.median_first_response_hours,
        "github_first_response_sample": github.first_response_sample,
        "github_outside_pr_merge_share": github.outside_pr_merge_share,
        "github_outside_prs_decided": github.outside_prs_decided,
        "github_commits_last_year": github.commits_last_year,
        "github_contributor_count": github.contributor_count,
        "github_latest_release_at": github.latest_release_at,
        "github_tests_count": github.tests_count,
        "github_action_count": github.action_count,
    }


def _responsiveness_reasons(signals: MaintenanceSignals) -> list[str]:
    """Context for the label, which rests on dates alone: a stable addon can go long without a commit."""
    reasons = []
    if signals.github_commits_last_year is not None:
        reasons.append(f"The repository had {signals.github_commits_last_year} commits in the last year.")
    if signals.github_has_issues_enabled is False:
        reasons.append("The repository has issues turned off.")
    elif signals.github_open_issue_count is not None and signals.github_closed_issue_count is not None:
        reasons.append(f"The repository has {signals.github_open_issue_count} open and "
                       f"{signals.github_closed_issue_count} closed issues.")
    if signals.github_open_pr_count is not None and signals.github_merged_pr_count is not None:
        reasons.append(f"The repository has {signals.github_open_pr_count} open and "
                       f"{signals.github_merged_pr_count} merged pull requests.")
    if signals.github_median_first_response_hours is not None:
        reasons.append(f"The median first response took {signals.github_median_first_response_hours:g} hours over "
                       f"{signals.github_first_response_sample} answered issues and pull requests; unanswered ones "
                       "are not counted.")
    if signals.github_outside_pr_merge_share is not None:
        reasons.append(f"{signals.github_outside_pr_merge_share:.0%} of the {signals.github_outside_prs_decided} "
                       "decided pull requests from outside authors were merged.")
    return reasons


class MaintenanceService:
    def __init__(self, catalog: CatalogService, snapshots: SnapshotService, thresholds: MaintenanceThresholds):
        self._catalog = catalog
        self._snapshots = snapshots
        self._thresholds = thresholds

    def assess(self, addon_id: int, snapshot: date | None = None) -> MaintenanceReport:
        as_of = self._snapshots.resolve(snapshot)
        details = self._catalog.get(addon_id, snapshot)
        label, reasons, signals = self.classify(details, as_of)
        if signals.forks and label in (MaintenanceLabel.STALE, MaintenanceLabel.ABANDONED):
            reasons.append(self._forks_reason(signals.forks, snapshot))
        return MaintenanceReport(addon_id=addon_id, title=details.anki_web.title, as_of=as_of, label=label,
                                 reasons=reasons, signals=signals)

    def classify(self, details: AddonDetails,
                 as_of: date) -> tuple[MaintenanceLabel, list[str], MaintenanceSignals]:
        """The label, its reasons and the signals of an already loaded addon, as of the snapshot date."""
        forum = details.forum
        last_activity = _last_activity(details)
        days = (as_of - last_activity).days if last_activity else None
        signals = MaintenanceSignals(
            **_github_signals(details.github),
            ankiweb_update_date=details.anki_web.update_date,
            forum_last_posted_at=forum.last_posted_at if forum else None,
            forum_posts_count=forum.posts_count if forum else None,
            last_activity=last_activity,
            days_since_last_activity=days,
            forked_from=details.forked_from.id if details.forked_from else None,
            forks=list(details.forks),
        )
        label, reasons = self._label(signals)
        return label, reasons, signals

    def _forks_reason(self, forks: list[int], snapshot: date | None) -> str:
        try:
            names = [f'"{fork.anki_web.title}" ({fork.id})' for fork in self._catalog.get_many(forks, snapshot)]
        except AddonNotFound:
            names = [str(fork) for fork in forks]
        lead = "Another addon was" if len(forks) == 1 else f"{len(forks)} other addons were"
        return f"{lead} forked from this one and may still be maintained: {', '.join(names)}."

    def _label(self, signals: MaintenanceSignals) -> tuple[MaintenanceLabel, list[str]]:
        reasons = []
        if signals.github_archived:
            return MaintenanceLabel.ABANDONED, ["The GitHub repository is archived."]
        if signals.days_since_last_activity is None:
            return MaintenanceLabel.UNKNOWN, ["No update or commit dates are available."]
        days = signals.days_since_last_activity
        reasons.append(f"Last update or commit was {days} days before the snapshot ({signals.last_activity}).")
        if signals.github_tests_count:
            reasons.append(f"The repository has {signals.github_tests_count} test files.")
        if signals.github_action_count:
            reasons.append(f"The repository has {signals.github_action_count} GitHub Actions workflows.")
        reasons.extend(_responsiveness_reasons(signals))
        if days <= self._thresholds.active_days:
            return MaintenanceLabel.ACTIVE, reasons
        if days <= self._thresholds.stale_days:
            return MaintenanceLabel.STALE, reasons
        return MaintenanceLabel.ABANDONED, reasons
