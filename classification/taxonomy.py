import json
from collections import Counter
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator

from classification.models import Term
from classification.taxonomies import TAXONOMY_ADAPTERS, GenericTaxonomy
from extraction.models import sha256


class Taxonomy(BaseModel):
    terms: list[Term]
    sha256: str

    @classmethod
    def load(cls, path: Path) -> Self:
        data = json.loads(path.read_bytes())
        if not isinstance(data, dict):
            raise ValueError("a taxonomy file must hold a JSON object")
        adapter = next((adapter for adapter in TAXONOMY_ADAPTERS if adapter.matches(data)), GenericTaxonomy)
        terms = adapter.terms(data)
        canonical = {"adapter": adapter.name, "terms": [term.model_dump() for term in sorted(terms, key=lambda term: term.code)]}
        return cls(terms=terms, sha256=sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode()))

    @model_validator(mode="after")
    def _check_codes(self) -> Self:
        counts = Counter(term.code for term in self.terms)
        duplicates = sorted(code for code, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate codes: {', '.join(duplicates)}")
        unknown = sorted({term.parent for term in self.terms if term.parent} - counts.keys())
        if unknown:
            raise ValueError(f"unknown parent codes: {', '.join(unknown)}")
        return self

    def roots(self) -> list[Term]:
        return self.children("")

    def children(self, code: str) -> list[Term]:
        return [term for term in self.terms if term.parent == code]
