import re
from datetime import date

from pydantic import BaseModel

from anki_addons_mcp.application.catalog import CatalogService, check_limit
from anki_addons_mcp.application.tags import TagService
from anki_addons_mcp.domain.models import AddonCard, AddonDetails
from anki_addons_mcp.domain.ports import AddonRepository
from anki_addons_mcp.domain.query import AddonFilters, AddonQuery, SortField

_STOPWORDS = frozenset(["a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "with", "addon", "add-on", "anki", "card", "cards", "your", "you", "will", "not", "use", "using", "allows", "adds", "which", "when", "also", "more", "than"])
_MAX_TERMS = 12


class SimilarAddon(BaseModel):
    card: AddonCard
    score: float
    reasons: list[str]


def _terms(details: AddonDetails) -> list[str]:
    text = " ".join(filter(None, [
        details.anki_web.title,
        details.ai.summary if details.ai else None,
        details.github.repo_description if details.github else None,
        " ".join(details.github.topics) if details.github else None,
    ]))
    seen: dict[str, None] = {}
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower()):
        if word not in _STOPWORDS:
            seen.setdefault(word)
    return list(seen)[:_MAX_TERMS]


def _unvoted(card: AddonCard) -> bool:
    return card.likes + card.dislikes == 0


class SimilarityService:
    def __init__(self, repository: AddonRepository, catalog: CatalogService, tags: TagService):
        self._repository = repository
        self._catalog = catalog
        self._tags = tags

    def similar(self, addon_id: int, limit: int = 10, snapshot: date | None = None) -> list[SimilarAddon]:
        check_limit(limit)
        target = self._catalog.get(addon_id, snapshot)
        terms = _terms(target)
        scored: dict[int, SimilarAddon] = {}
        if terms:
            pool = self._repository.find(
                AddonQuery(text=" ".join(terms), sort=SortField.RELEVANCE, limit=limit * 4), snapshot).items
            for rank, card in enumerate(pool):
                if card.id != addon_id:
                    scored[card.id] = SimilarAddon(card=card, score=1.0 - rank / len(pool),
                                                   reasons=["similar wording in title/summary/topics"])
        author = target.github.user if target.github else None
        if author:
            same_author = self._repository.find(
                AddonQuery(filters=AddonFilters(github_user=author), limit=limit), snapshot).items
            for card in same_author:
                if card.id == addon_id:
                    continue
                entry = scored.setdefault(card.id, SimilarAddon(card=card, score=0.0, reasons=[]))
                entry.score += 0.5
                entry.reasons.append(f"same author ({author})")
        self._add_topic_overlap(target, scored, snapshot)
        self._add_tag_overlap(target, scored, snapshot)
        # Addons nobody has voted on yet are untested, so they go after every voted one.
        ranked = sorted(scored.values(), key=lambda s: (_unvoted(s.card), -s.score, s.card.id))[:limit]
        for entry in ranked:
            entry.score = round(entry.score, 3)
            if _unvoted(entry.card):
                entry.reasons.append("no AnkiWeb votes yet")
        return ranked

    def _add_topic_overlap(self, target: AddonDetails, scored: dict[int, SimilarAddon], snapshot: date | None) -> None:
        topics = set(target.github.topics) - {"anki", "anki-addon", "anki-add-on", "addon"} if target.github else set()
        if not topics or not scored:
            return
        for details in self._repository.get_addons(list(scored), snapshot):
            shared = topics & set(details.github.topics if details.github else [])
            if shared:
                scored[details.id].score += 0.25 * len(shared)
                scored[details.id].reasons.append("shared GitHub topics: " + ", ".join(sorted(shared)))

    def _add_tag_overlap(self, target: AddonDetails, scored: dict[int, SimilarAddon], snapshot: date | None) -> None:
        tags = set(target.ai.tags) & self._tags.function_tags(snapshot) if target.ai else set()
        if not tags or not scored:
            return
        for details in self._repository.get_addons(list(scored), snapshot):
            shared = tags & set(details.ai.tags if details.ai else [])
            if shared:
                scored[details.id].score += 0.25 * len(shared)
                scored[details.id].reasons.append("shared tags: " + ", ".join(sorted(shared)))
