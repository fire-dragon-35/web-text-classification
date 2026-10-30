from datetime import datetime

from pydantic import BaseModel


class Classification(BaseModel):
    text_sha256: str
    classifier: str
    taxonomy_sha256: str
    max_depth: int
    categories: list[str]
    classified_at: datetime
