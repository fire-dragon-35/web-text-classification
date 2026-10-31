from collections.abc import Sequence
from typing import NamedTuple, Protocol

from classification.models import Classification, ClassifiedSection, Pending
from extraction.models import FetchResult, Page, PageVersion, Section


class PruneResult(NamedTuple):
    classifications: int
    pending: int


class Storage(Protocol):
    def latest(self, url: str) -> tuple[str, str] | None: ...

    def save(self, source_id: str, fetch: FetchResult, page: Page, sections: list[Section]) -> None: ...

    def page_versions(self) -> list[PageVersion]: ...

    def longest_sections(self, source_ids: list[str], limit: int) -> list[tuple[str, str, int]]: ...

    def prune(self, page_ids: Sequence[int], apply: bool) -> PruneResult: ...

    def classified_sections(
        self, classifier: str, taxonomy_sha256: str, max_depth: int, source_ids: list[str]
    ) -> list[ClassifiedSection]: ...

    def save_classification(self, classification: Classification) -> None: ...

    def pending(self, classifier: str, taxonomy_sha256: str, max_depth: int) -> list[Pending]: ...

    def update_pending(
        self,
        save: Sequence[Pending] = ...,
        delete: Sequence[Pending] = ...,
        classifications: Sequence[Classification] = ...,
    ) -> None: ...

    def close(self) -> None: ...
