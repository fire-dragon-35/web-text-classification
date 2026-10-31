import sqlite3

import numpy as np

from db.sqlite import current_sections
from search.models import CurrentSection

EMBEDDED = "SELECT input_sha256 FROM embedding WHERE model = ?"

INSERT_EMBEDDING = """
INSERT INTO embedding (input_sha256, model, text_sha256, vector)
VALUES (?, ?, ?, ?)
ON CONFLICT DO NOTHING
"""


class SqliteEmbeddings:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def sections(self, source_ids: list[str]) -> list[CurrentSection]:
        return current_sections(self._connection, source_ids)

    def embedded(self, model: str) -> set[str]:
        return {input_sha256 for (input_sha256,) in self._connection.execute(EMBEDDED, (model,))}

    def save(self, model: str, sections: list[CurrentSection], vectors: np.ndarray) -> None:
        with self._connection:
            self._connection.executemany(
                INSERT_EMBEDDING,
                [
                    (section.input_sha256, model, section.text_sha256, vector.astype(np.float32).tobytes())
                    for section, vector in zip(sections, vectors, strict=True)
                ],
            )
