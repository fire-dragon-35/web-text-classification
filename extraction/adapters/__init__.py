from extraction.adapters.riksdagen import RiksdagenSFS
from extraction.website import Website

ADAPTERS: tuple[type[Website], ...] = (RiksdagenSFS,)
