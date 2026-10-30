import json
from collections import Counter
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator

from extraction.models import sha256


class Term(BaseModel):
    code: str
    name: str
    definition: str
    parent: str


class Taxonomy(BaseModel):
    terms: list[Term]
    sha256: str

    @classmethod
    def load(cls, path: Path) -> Self:
        data = path.read_bytes()
        return cls.model_validate(json.loads(data) | {"sha256": sha256(data)})

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
