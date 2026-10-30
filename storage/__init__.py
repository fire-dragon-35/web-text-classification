from typing import Protocol

from extraction.models import FetchResult, Page, Section


class Storage(Protocol):
    def latest(self, url: str) -> tuple[str, str] | None: ...

    def save(self, fetch: FetchResult, page: Page, sections: list[Section]) -> None: ...

    def close(self) -> None: ...
