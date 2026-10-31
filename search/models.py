from pydantic import BaseModel

from extraction.models import sha256


class CurrentSection(BaseModel):
    id: int
    source_id: str
    url: str
    page_title: str
    heading: str
    ref: str | None
    text: str
    text_sha256: str

    @property
    def embedding_input(self) -> str:
        context = " › ".join(part for part in (self.source_id, self.page_title, self.heading, self.ref) if part)
        return f"{context}\n\n{self.text}"

    @property
    def input_sha256(self) -> str:
        return sha256(self.embedding_input.encode())


class Hit(BaseModel):
    section: CurrentSection
    score: float
