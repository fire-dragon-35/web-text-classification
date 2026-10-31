from extraction.adapters.riksdagen import RiksdagenSFS
from extraction.website import Website

ADAPTERS: tuple[type[Website], ...] = (RiksdagenSFS,)
ADAPTERS_BY_NAME = {adapter.name: adapter for adapter in ADAPTERS}
