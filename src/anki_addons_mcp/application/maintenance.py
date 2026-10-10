from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel

from anki_addons_mcp.application.catalog import CatalogService
from anki_addons_mcp.application.snapshots import SnapshotService


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
    github_last_commit: str | None
    github_pushed_at: str | None
    github_archived: bool | None
    github_open_issues: int | None
    github_tests_count: int | None
    github_action_count: int | None
    forum_last_posted_at: str | None
    forum_posts_count: int | None
    last_activity: date | None
    days_since_last_activity: int | None


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


class MaintenanceService:
    def __init__(self, catalog: CatalogService, snapshots: SnapshotService, thresholds: MaintenanceThresholds):
        self._catalog = catalog
        self._snapshots = snapshots
        self._thresholds = thresholds

    def assess(self, addon_id: int, snapshot: date | None = None) -> MaintenanceReport:
        as_of = self._snapshots.resolve(snapshot)
        details = self._catalog.get(addon_id, snapshot)
        github = details.github
        forum = details.forum
        activity = [d for d in (
            _to_date(details.anki_web.update_date),
            _to_date(github.last_commit) if github else None,
            _to_date(github.pushed_at) if github else None,
        ) if d is not None]
        last_activity = max(activity) if activity else None
        days = (as_of - last_activity).days if last_activity else None
        signals = MaintenanceSignals(
            ankiweb_update_date=details.anki_web.update_date,
            github_last_commit=github.last_commit if github else None,
            github_pushed_at=github.pushed_at if github else None,
            github_archived=github.archived if github else None,
            github_open_issues=github.open_issues if github else None,
            github_tests_count=github.tests_count if github else None,
            github_action_count=github.action_count if github else None,
            forum_last_posted_at=forum.last_posted_at if forum else None,
            forum_posts_count=forum.posts_count if forum else None,
            last_activity=last_activity,
            days_since_last_activity=days,
        )
        label, reasons = self._label(signals)
        return MaintenanceReport(addon_id=addon_id, title=details.anki_web.title, as_of=as_of, label=label,
                                 reasons=reasons, signals=signals)

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
        if days <= self._thresholds.active_days:
            return MaintenanceLabel.ACTIVE, reasons
        if days <= self._thresholds.stale_days:
            return MaintenanceLabel.STALE, reasons
        return MaintenanceLabel.ABANDONED, reasons
