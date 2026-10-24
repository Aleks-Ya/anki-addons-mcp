from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field

from anki_addons_mcp.application.maintenance import MaintenanceLabel, MaintenanceService
from anki_addons_mcp.application.snapshots import SnapshotService
from anki_addons_mcp.domain.compatibility import Support, addon_support, manifest_support, require_point
from anki_addons_mcp.domain.errors import AddonNotFound, InvalidQuery
from anki_addons_mcp.domain.models import (
    APPROVAL_DESCRIPTION,
    FORK_DESCRIPTION,
    AddonDetails,
    ForkEvidence,
    VersionKind,
    approval_score,
)
from anki_addons_mcp.domain.ports import AddonRepository

MAX_FAMILY = 100
AI_FLAG = "From the LLM-picked AI tags; may be inaccurate."


class ForkRole(StrEnum):
    ORIGINAL = "original"
    FORK = "fork"


class ForkFamilyMember(BaseModel):
    id: int
    title: str
    url: str
    role: ForkRole = Field(description="'original' (forked from no known addon) or 'fork'")
    forked_from: int | None = Field(default=None, description="Addon this one was forked from")
    evidence: ForkEvidence | None = Field(
        default=None, description="How the link to forked_from was found: 'github_fork', 'ai' (an LLM read the "
                                  "description; may be inaccurate) or 'override' (set by hand)")
    depth: int = Field(description="Fork generations below the first member: 0 for it, 1 for its forks, ...")
    forks: list[int] = Field(default_factory=list, description="Listed members forked from this one")
    anki_version: str | None = Field(default=None, description="Newest supported Anki version as AnkiWeb lists it")
    anki_version_kind: VersionKind = VersionKind.UNKNOWN
    compatibility: Support | None = Field(
        default=None, description="AnkiWeb verdict for the family's anki_version, as in check_compatibility")
    manifest_compatibility: Support | None = Field(
        default=None, description="GitHub manifest verdict for the family's anki_version")
    maintenance: MaintenanceLabel = Field(description="Label of assess_maintenance")
    last_activity: date | None = Field(default=None, description="Latest AnkiWeb update, commit or push")
    days_since_last_activity: int | None = None
    rating: int = Field(description="AnkiWeb votes (likes + dislikes), not a quality score")
    likes: int
    dislikes: int
    github_stars: int | None = None
    github_archived: bool | None = None
    obsolete: bool = Field(description="Tagged obsolete. " + AI_FLAG)
    beta: bool = Field(description="Tagged beta. " + AI_FLAG)
    paid: bool = Field(description="Tagged paid. " + AI_FLAG)

    @computed_field(description=APPROVAL_DESCRIPTION)
    def approval(self) -> float:
        return round(approval_score(self.likes, self.dislikes), 4)


class ForkFamily(BaseModel):
    addon_id: int = Field(description="The requested addon")
    original_id: int | None = Field(
        default=None, description="The member forked from no known addon; null when it is not listed")
    as_of: date
    anki_version: str | None = Field(
        default=None, description="Anki version of the compatibility verdicts: the requested one or the latest")
    anki_point_version: int | None = None
    members: list[ForkFamilyMember] = Field(
        description="The original first, then each version followed by its forks (depth-first); forks of the "
                    "same addon by approval, highest first. The order is not a ranking.")
    truncated: bool = Field(description="The family has more members than the limit")
    notes: list[str] = Field(default_factory=list)

    @computed_field
    def caveat(self) -> str:
        return FORK_DESCRIPTION


def _neighbours(details: AddonDetails) -> list[int]:
    parent = [details.forked_from.id] if details.forked_from else []
    return parent + list(details.forks)


class ForkService:
    def __init__(self, repository: AddonRepository, snapshots: SnapshotService, maintenance: MaintenanceService):
        self._repository = repository
        self._snapshots = snapshots
        self._maintenance = maintenance

    def family(self, addon_id: int, anki_version: str | None = None, limit: int = 50,
               snapshot: date | None = None) -> ForkFamily:
        if limit < 1 or limit > MAX_FAMILY:
            raise InvalidQuery(f"limit must be between 1 and {MAX_FAMILY}")
        as_of = self._snapshots.resolve(snapshot)
        start = self._repository.get_addon(addon_id, snapshot)
        if start is None:
            raise AddonNotFound(addon_id, snapshot)
        found, truncated = self._component(start, limit, snapshot)
        notes = []
        if truncated:
            notes.append(f"The family has more than {limit} members; the ones closest to {addon_id} are listed.")
        for details in found.values():
            parent = details.forked_from
            if parent and parent.id not in found and not truncated:
                notes.append(f"{details.id} was forked from {parent.id}, which is not in this snapshot.")
        top = self._top(start, found)
        if top.forked_from and top.forked_from.id in found:
            notes.append(f"The fork links form a loop; the list starts at its smallest id, {top.id}.")
        point, version = self._target(anki_version, snapshot, notes)
        ordered = self._tree(top, found)
        members = [self._member(details, depth, found, point, as_of) for details, depth in ordered]
        original = next((m.id for m in members if m.role == ForkRole.ORIGINAL), None)
        return ForkFamily(addon_id=addon_id, original_id=original, as_of=as_of, anki_version=version,
                          anki_point_version=point, members=members, truncated=truncated, notes=notes)

    def _component(self, start: AddonDetails, limit: int,
                   snapshot: date | None) -> tuple[dict[int, AddonDetails], bool]:
        """Members linked to `start` by fork relations, nearest first, at most `limit` of them."""
        found = {start.id: start}
        frontier = [start]
        while frontier:
            pending = sorted({n for details in frontier for n in _neighbours(details)} - found.keys())
            if not pending:
                break
            room = limit - len(found)
            loaded = self._repository.get_addons(pending, snapshot)
            if len(loaded) > room:
                found.update((details.id, details) for details in loaded[:room])
                return found, True
            found.update((details.id, details) for details in loaded)
            frontier = loaded
        return found, False

    @staticmethod
    def _top(start: AddonDetails, found: dict[int, AddonDetails]) -> AddonDetails:
        """The member whose parent is not listed, or the smallest id of a loop of fork links."""
        current, path = start, [start.id]
        while current.forked_from and current.forked_from.id in found:
            current = found[current.forked_from.id]
            if current.id in path:
                return found[min(path[path.index(current.id):])]
            path.append(current.id)
        return current

    @staticmethod
    def _tree(top: AddonDetails, found: dict[int, AddonDetails]) -> list[tuple[AddonDetails, int]]:
        def order(details: AddonDetails) -> tuple[float, int]:
            return -approval_score(details.anki_web.likes, details.anki_web.dislikes), details.id

        ordered: list[tuple[AddonDetails, int]] = []
        seen: set[int] = set()
        stack = [(top, 0)]
        while stack:
            details, depth = stack.pop()
            if details.id in seen:
                continue
            seen.add(details.id)
            ordered.append((details, depth))
            # Pushed last-first, so the stack pops the forks in order.
            children = sorted((found[f] for f in details.forks if f in found and f not in seen), key=order,
                              reverse=True)
            stack.extend((child, depth + 1) for child in children)
        return ordered

    def _target(self, anki_version: str | None, snapshot: date | None,
                notes: list[str]) -> tuple[int | None, str | None]:
        if anki_version:
            return require_point(anki_version), anki_version
        releases = self._repository.list_anki_versions(snapshot)
        if not releases:
            notes.append("This snapshot has no list of Anki releases; pass anki_version for compatibility verdicts.")
            return None, None
        return releases[0].point_version, releases[0].version

    def _member(self, details: AddonDetails, depth: int, found: dict[int, AddonDetails], point: int | None,
                as_of: date) -> ForkFamilyMember:
        anki_web, github = details.anki_web, details.github
        label, _, signals = self._maintenance.classify(details, as_of)
        tags = set(details.ai.tags) if details.ai else set()
        parent = details.forked_from
        manifest = github.manifest if github else None
        return ForkFamilyMember(
            id=details.id,
            title=anki_web.title,
            url=anki_web.addon_page_url,
            role=ForkRole.FORK if parent else ForkRole.ORIGINAL,
            forked_from=parent.id if parent else None,
            evidence=parent.evidence if parent else None,
            depth=depth,
            forks=[f for f in details.forks if f in found],
            anki_version=anki_web.anki_version,
            anki_version_kind=anki_web.anki_version_kind,
            compatibility=addon_support(anki_web.branches, point)[0] if point is not None else None,
            manifest_compatibility=manifest_support(manifest, point) if point is not None else None,
            maintenance=label,
            last_activity=signals.last_activity,
            days_since_last_activity=signals.days_since_last_activity,
            rating=anki_web.rating,
            likes=anki_web.likes,
            dislikes=anki_web.dislikes,
            github_stars=github.stars if github else None,
            github_archived=github.archived if github else None,
            obsolete="obsolete" in tags,
            beta="beta" in tags,
            paid="paid" in tags,
        )
