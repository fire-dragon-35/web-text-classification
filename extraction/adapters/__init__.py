from extraction.adapters.riksdagen import RiksdagenSFS
from extraction.extractor import Adapter

ADAPTERS: tuple[type[Adapter], ...] = (RiksdagenSFS,)
ADAPTERS_BY_NAME = {adapter.name: adapter for adapter in ADAPTERS}
