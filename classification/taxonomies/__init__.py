from classification.taxonomies.generic import GenericTaxonomy
from classification.taxonomies.list import ListTaxonomy

TAXONOMY_ADAPTERS: tuple[type[GenericTaxonomy], ...] = (ListTaxonomy,)
