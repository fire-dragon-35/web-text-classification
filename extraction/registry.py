from extraction.adapters import ADAPTERS, ADAPTERS_BY_NAME
from extraction.extractor import Adapter, Extractor
from extraction.html import Html
from extraction.pdf import Pdf
from extraction.sources import Source


class Extractors:
    def __init__(self, source: Source) -> None:
        self._adapter = ADAPTERS_BY_NAME[source.adapter]() if source.adapter else None
        self._adapters = tuple(adapter() for adapter in ADAPTERS)
        self._by_content_type: tuple[Extractor, ...] = (Html(source.selector, tuple(source.exclude)), Pdf())

    def adapter_for(self, url: str) -> Adapter | None:
        if self._adapter:
            return self._adapter
        return next((adapter for adapter in self._adapters if adapter.matches(url)), None)

    def fetch_url(self, url: str) -> str:
        adapter = self.adapter_for(url)
        return adapter.fetch_url(url) if adapter else url

    def content_types(self, url: str) -> tuple[str, ...]:
        return tuple(content_type for extractor in self._candidates(url) for content_type in extractor.content_types)

    def select(self, url: str, content_type: str) -> Extractor | None:
        return next((extractor for extractor in self._candidates(url) if extractor.accepts(content_type)), None)

    def _candidates(self, url: str) -> tuple[Extractor, ...]:
        adapter = self.adapter_for(url)
        return (adapter, *self._by_content_type) if adapter else self._by_content_type
