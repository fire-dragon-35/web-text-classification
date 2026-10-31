from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from extraction.adapters import ADAPTERS_BY_NAME


class Follow(StrEnum):
    NONE = "none"
    PDF = "pdf"
    ALL = "all"


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    urls: list[str]
    adapter: str | None = None
    selector: str | None = None
    exclude: list[str] = []
    allow: list[str] = []
    sitemap: str | None = None
    follow: Follow | None = None
    max_pages: int = Field(5, ge=1)

    @field_validator("adapter")
    @classmethod
    def _known_adapter(cls, name: str | None) -> str | None:
        if name is not None and name not in ADAPTERS_BY_NAME:
            raise ValueError(f"unknown adapter {name!r}, known: {', '.join(sorted(ADAPTERS_BY_NAME))}")
        return name

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.adapter:
            adapter = ADAPTERS_BY_NAME[self.adapter]()
            for url in self.urls:
                adapter.fetch_url(url)
        if self.follow is None:
            self.follow = Follow.PDF if self.sitemap else Follow.ALL
        return self


class SourcesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[Source]
