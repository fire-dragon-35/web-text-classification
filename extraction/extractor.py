from abc import ABC, abstractmethod

from extraction.models import FetchResult, Page, Section

MIN_CHARS = 200


class Extractor(ABC):
    content_types: tuple[str, ...]

    def accepts(self, content_type: str) -> bool:
        return content_type.startswith(self.content_types)

    def links(self, fetch: FetchResult) -> list[str]:
        return []

    @abstractmethod
    def extract(self, fetch: FetchResult) -> Page: ...

    @abstractmethod
    def sections(self, page: Page) -> list[Section]: ...


class Adapter(Extractor):
    name: str

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool: ...

    @abstractmethod
    def fetch_url(self, url: str) -> str: ...
