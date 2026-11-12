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


def _relations(target: AddonDetails) -> dict[int, list[tuple[str, float]]]:
    """Forks, copies and addons of the same repo, with a reason and a weight each."""
    related: dict[int, list[tuple[str, float]]] = {}

    def relate(addon_id: int, reason: str, weight: float) -> None:
        if addon_id != target.id:
            related.setdefault(addon_id, []).append((reason, weight))

    for fork in target.forks:
        relate(fork, "forked from this addon", 1.0)
    if target.forked_from is not None:
        relate(target.forked_from.id, f"this addon is a fork of it ({target.forked_from.evidence} evidence)", 1.0)
    for copy in target.duplicates:
        relate(copy, "identical package: a copy of this addon", 1.0)
    if target.duplicate_of is not None:
        relate(target.duplicate_of.id,
               f"identical package: this addon is a copy of it ({target.duplicate_of.evidence} evidence)", 1.0)
    github = target.github
    if github is not None:
        sharing = f" ({github.repo_sharing})" if github.repo_sharing else ""
        for addon_id in github.shared_with:
            relate(addon_id, f"shares the GitHub repo{sharing}", 0.5)
    return related


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
        scored = self._wording_matches(target, limit, snapshot)
        self._add_same_author(target, scored, limit, snapshot)
        self._add_relations(target, scored, snapshot)
        self._add_topic_overlap(target, scored, snapshot)
        self._add_tag_overlap(target, scored, snapshot)
        # Addons nobody has voted on yet are untested, so they go after every voted one.
        ranked = sorted(scored.values(), key=lambda s: (_unvoted(s.card), -s.score, s.card.id))[:limit]
        for entry in ranked:
            entry.score = round(entry.score, 3)
            if _unvoted(entry.card):
                entry.reasons.append("no AnkiWeb votes yet")
        return ranked

    def _wording_matches(self, target: AddonDetails, limit: int, snapshot: date | None) -> dict[int, SimilarAddon]:
        terms = _terms(target)
        if not terms:
            return {}
        pool = self._repository.find(
            AddonQuery(text=" ".join(terms), sort=SortField.RELEVANCE, limit=limit * 4), snapshot).items
        return {card.id: SimilarAddon(card=card, score=1.0 - rank / len(pool),
                                      reasons=["similar wording in title/summary/topics"])
                for rank, card in enumerate(pool) if card.id != target.id}

    def _add_same_author(self, target: AddonDetails, scored: dict[int, SimilarAddon], limit: int,
                         snapshot: date | None) -> None:
        github_user = target.github.user if target.github else None
        if target.author:
            filters, reason = AddonFilters(author_id=target.author.id), "same AnkiWeb author"
        elif github_user:
            filters, reason = AddonFilters(github_user=github_user), f"same author ({github_user})"
        else:
            return
        same_author = self._repository.find(AddonQuery(filters=filters, limit=limit), snapshot).items
        for card in same_author:
            if card.id == target.id:
                continue
            entry = scored.setdefault(card.id, SimilarAddon(card=card, score=0.0, reasons=[]))
            entry.score += 0.5
            entry.reasons.append(reason)

    def _add_relations(self, target: AddonDetails, scored: dict[int, SimilarAddon], snapshot: date | None) -> None:
        """Related addons join the result whatever their wording."""
        related = _relations(target)
        missing = [addon_id for addon_id in related if addon_id not in scored]
        if missing:
            cards = self._repository.find(
                AddonQuery(filters=AddonFilters(addon_ids=missing), limit=len(missing)), snapshot).items
            for card in cards:
                scored[card.id] = SimilarAddon(card=card, score=0.0, reasons=[])
        for addon_id, relations in related.items():
            if addon_id in scored:
                for reason, weight in relations:
                    scored[addon_id].score += weight
                    scored[addon_id].reasons.append(reason)

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
