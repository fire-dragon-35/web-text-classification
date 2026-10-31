from collections import defaultdict
from enum import StrEnum

from db import SearchIndex
from search.embedder import Embedder
from search.models import CurrentSection, Hit

CANDIDATES = 50
RRF_K = 60


class SearchMode(StrEnum):
    HYBRID = "hybrid"
    TEXT = "text"
    VECTOR = "vector"


def _fused(rankings: list[list[Hit]], limit: int) -> list[Hit]:
    scores: defaultdict[int, float] = defaultdict(float)
    sections: dict[int, CurrentSection] = {}
    for hits in rankings:
        for rank, hit in enumerate(hits, start=1):
            scores[hit.section.id] += 1 / (RRF_K + rank)
            sections[hit.section.id] = hit.section
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [Hit(section=sections[section_id], score=score) for section_id, score in ranked]


class Searcher:
    def __init__(self, index: SearchIndex, embedder: Embedder) -> None:
        self._index = index
        self._embedder = embedder

    def search(
        self, query: str, source_ids: list[str], limit: int, mode: SearchMode, terms: str | None = None
    ) -> list[Hit]:
        match mode:
            case SearchMode.TEXT:
                return self._index.text_matches(terms or query, source_ids, limit)
            case SearchMode.VECTOR:
                return self._nearest(query, source_ids, limit)
            case SearchMode.HYBRID:
                text = self._index.text_matches(terms or query, source_ids, CANDIDATES)
                return _fused([text, self._nearest(query, source_ids, CANDIDATES)], limit)

    def _nearest(self, query: str, source_ids: list[str], limit: int) -> list[Hit]:
        return self._index.nearest(self._embedder.name, self._embedder.embed([query])[0], source_ids, limit)
