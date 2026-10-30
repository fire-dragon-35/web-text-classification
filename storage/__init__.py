from typing import Protocol

from classification.models import Classification
from extraction.models import FetchResult, Page, Section


class Storage(Protocol):
    def latest(self, url: str) -> tuple[str, str] | None: ...

    def save(self, source_id: str, fetch: FetchResult, page: Page, sections: list[Section]) -> None: ...

    def current_sections(self, source_ids: list[str]) -> list[tuple[str, str, Section]]: ...

    def latest_classification(
        self, text_sha256: str, classifier: str, taxonomy_sha256: str, max_depth: int
    ) -> list[str] | None: ...

    def save_classification(self, classification: Classification) -> None: ...

    def close(self) -> None: ...
