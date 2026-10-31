from collections.abc import Sequence
from typing import Protocol

from classification.models import Classification, ClassifiedSection, Pending
from extraction.models import FetchResult, Page, Section


class Storage(Protocol):
    def latest(self, url: str) -> tuple[str, str] | None: ...

    def save(self, source_id: str, fetch: FetchResult, page: Page, sections: list[Section]) -> None: ...

    def classified_sections(
        self, classifier: str, taxonomy_sha256: str, max_depth: int, source_ids: list[str]
    ) -> list[ClassifiedSection]: ...

    def latest_classification(
        self, text_sha256: str, classifier: str, taxonomy_sha256: str, max_depth: int
    ) -> list[str] | None: ...

    def save_classification(self, classification: Classification) -> None: ...

    def pending(self, classifier: str, taxonomy_sha256: str, max_depth: int) -> list[Pending]: ...

    def update_pending(
        self,
        save: Sequence[Pending] = ...,
        delete: Sequence[Pending] = ...,
        classifications: Sequence[Classification] = ...,
    ) -> None: ...

    def close(self) -> None: ...
