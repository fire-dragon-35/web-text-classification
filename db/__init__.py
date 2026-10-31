from collections.abc import Sequence
from typing import Protocol

import numpy as np

from extraction.models import FetchResult, Page, PageVersion, Section
from search.models import CurrentSection, Hit


class PageStore(Protocol):
    def latest(self, url: str) -> tuple[str, str] | None: ...

    def save(self, source_id: str, fetch: FetchResult, page: Page, sections: list[Section]) -> None: ...

    def longest_sections(self, source_ids: list[str], limit: int) -> list[tuple[str, str, int]]: ...


class PruneStore(Protocol):
    def page_versions(self) -> list[PageVersion]: ...

    def prune(self, page_ids: Sequence[int], apply: bool) -> int: ...


class EmbeddingStore(Protocol):
    def sections(self, source_ids: list[str]) -> list[CurrentSection]: ...

    def embedded(self, model: str) -> set[str]: ...

    def save(self, model: str, sections: list[CurrentSection], vectors: np.ndarray) -> None: ...


class SearchIndex(Protocol):
    def text_matches(self, query: str, source_ids: list[str], limit: int) -> list[Hit]: ...

    def nearest(self, model: str, vector: np.ndarray, source_ids: list[str], limit: int) -> list[Hit]: ...
