from datetime import date

from anki_addons_mcp.domain.errors import InvalidQuery
from anki_addons_mcp.domain.models import GroupField, Tag
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.domain.query import AddonFilters

FUNCTION_GROUP = "function"


class TagUsage(Tag):
    addon_count: int


class TagService:
    def __init__(self, repository: AddonRepository):
        self._repository = repository

    def vocabulary(self, snapshot: date | None = None) -> list[TagUsage]:
        counts = self._repository.group_counts(GroupField.AI_TAG, snapshot)
        usages = [TagUsage(**tag.model_dump(), addon_count=counts.get(tag.name, 0))
                  for tag in self._repository.list_tags(snapshot)]
        return sorted(usages, key=lambda t: (t.group != FUNCTION_GROUP, t.group, -t.addon_count, t.name))

    def function_tags(self, snapshot: date | None = None) -> set[str]:
        return {tag.name for tag in self._repository.list_tags(snapshot) if tag.group == FUNCTION_GROUP}

    def validate(self, names: list[str], snapshot: date | None = None) -> None:
        if not names:
            return
        known = {tag.name.lower() for tag in self._repository.list_tags(snapshot)}
        unknown = [name for name in names if name.lower() not in known]
        if unknown:
            raise InvalidQuery(f"Unknown tag '{unknown[0]}'. Valid tags (see list_tags): {', '.join(sorted(known))}")

    def validate_filters(self, filters: AddonFilters, snapshot: date | None = None) -> None:
        self.validate([*(filters.tags or []), *(filters.exclude_tags or [])], snapshot)
