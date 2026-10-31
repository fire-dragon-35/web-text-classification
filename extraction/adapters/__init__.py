from extraction.adapters.riksdagen import RiksdagenSFS
from extraction.website import Website

ADAPTERS: tuple[type[Website], ...] = (RiksdagenSFS,)
ADAPTERS_BY_NAME = {adapter.name: adapter for adapter in ADAPTERS}


def website_for(url: str, default: Website, adapter: str | None = None) -> Website:
    if adapter:
        return ADAPTERS_BY_NAME[adapter]()
    return next((candidate() for candidate in ADAPTERS if candidate.matches(url)), default)
