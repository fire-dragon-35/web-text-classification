import hashlib
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    urls: list[str]
    selector: str | None = None
    exclude: list[str] = []
    allow: list[str] = []
    sitemap: str | None = None
    max_pages: int = Field(5, ge=1)


class SourcesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[Source]


class FetchResult(BaseModel):
    url: str
    final_url: str
    status: int
    content_type: str
    fetched_at: datetime
    raw_sha256: str
    body: bytes = Field(exclude=True)


class Page(BaseModel):
    title: str
    page_date: date | None = None
    text: str
    extractor: str
    metadata: dict[str, str] = {}
    warnings: list[str] = []

    @computed_field
    @property
    def text_sha256(self) -> str:
        return sha256(self.text.encode())


class Section(BaseModel):
    ordinal: int
    heading: str
    level: int
    ref: str | None = None
    text: str

    @computed_field
    @property
    def text_sha256(self) -> str:
        return sha256(self.text.encode())
