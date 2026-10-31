from collections.abc import Iterator
from enum import StrEnum

from db import EmbeddingStore
from search.embedder import Embedder
from search.models import CurrentSection

CHUNK_SIZE = 64


class EmbedOutcome(StrEnum):
    EMBEDDED = "embedded"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"


class EmbeddingRun:
    def __init__(self, store: EmbeddingStore, embedder: Embedder, sections: list[CurrentSection], min_chars: int) -> None:
        self._store = store
        self._embedder = embedder
        embedded = store.embedded(embedder.name)
        kept = [section for section in sections if len(section.text) >= min_chars]
        self.skipped = len(sections) - len(kept)
        self.unchanged = sum(section.input_sha256 in embedded for section in kept)
        self._pending: dict[str, list[CurrentSection]] = {}
        for section in kept:
            if section.input_sha256 not in embedded:
                self._pending.setdefault(section.input_sha256, []).append(section)

    @property
    def pending(self) -> int:
        return sum(len(same) for same in self._pending.values())

    def run(self) -> Iterator[int]:
        groups = list(self._pending.values())
        for start in range(0, len(groups), CHUNK_SIZE):
            chunk = groups[start : start + CHUNK_SIZE]
            sections = [same[0] for same in chunk]
            self._store.save(
                self._embedder.name, sections, self._embedder.embed([section.embedding_input for section in sections])
            )
            yield sum(len(same) for same in chunk)
