from datetime import datetime
from typing import Self

import anthropic.types
from pydantic import BaseModel

from extraction.models import Section


class Term(BaseModel):
    code: str
    name: str
    definition: str
    parent: str


class Usage(BaseModel):
    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0

    @classmethod
    def of(cls, usage: anthropic.types.Usage) -> Self:
        return cls(
            input_tokens=usage.input_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
            output_tokens=usage.output_tokens,
        )

    def __add__(self, other: Self) -> Self:
        return type(self)(**{name: getattr(self, name) + getattr(other, name) for name in type(self).model_fields})

    @property
    def cache_hit_ratio(self) -> float:
        prompt = self.cache_read_input_tokens + self.cache_creation_input_tokens + self.input_tokens
        return self.cache_read_input_tokens / prompt if prompt else 0.0


class Choice(BaseModel):
    codes: list[str]
    usage: Usage


class Classification(BaseModel):
    text_sha256: str
    classifier: str
    taxonomy_sha256: str
    max_depth: int
    categories: list[str]
    classified_at: datetime
    usage: Usage


class Pending(BaseModel):
    text_sha256: str
    classifier: str
    taxonomy_sha256: str
    max_depth: int
    section_text: str
    level: int = 1
    chosen: list[str] = []
    categories: list[str] = []
    usage: Usage = Usage()
    batch_id: str | None = None


class ClassifiedSection(BaseModel):
    source_id: str
    page_title: str
    section: Section
    categories: list[str] | None
