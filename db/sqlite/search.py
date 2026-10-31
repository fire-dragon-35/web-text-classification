import re
import sqlite3
from pathlib import Path

import numpy as np

from db.sqlite import records, source_filter
from search.models import CurrentSection, Hit

WORD = re.compile(r"\w+")
STOPWORDS = frozenset(Path(__file__).with_name("stopwords_sv.txt").read_text().split())

TEXT_MATCHES = """
SELECT current_section.id, current_section.source_id, current_section.url, current_section.page_title,
       current_section.heading, current_section.ref, current_section.text, current_section.text_sha256,
       -bm25(section_fts) AS score
FROM section_fts
JOIN current_section ON current_section.id = section_fts.rowid
WHERE section_fts MATCH :query
    AND (:all_sources OR current_section.source_id IN (SELECT value FROM json_each(:source_ids)))
ORDER BY bm25(section_fts)
LIMIT :limit
"""

EMBEDDED_SECTIONS = """
SELECT current_section.id, current_section.source_id, current_section.url, current_section.page_title,
       current_section.heading, current_section.ref, current_section.text, current_section.text_sha256,
       embedding.input_sha256, embedding.vector
FROM current_section
JOIN embedding ON embedding.text_sha256 = current_section.text_sha256 AND embedding.model = :model
WHERE :all_sources OR current_section.source_id IN (SELECT value FROM json_each(:source_ids))
"""


def _match_query(query: str) -> str:
    return " OR ".join(f'"{word}"' for word in WORD.findall(query) if word.lower() not in STOPWORDS)


class SqliteSearch:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def text_matches(self, query: str, source_ids: list[str], limit: int) -> list[Hit]:
        match_query = _match_query(query)
        if not match_query:
            return []
        rows = self._connection.execute(TEXT_MATCHES, {"query": match_query, "limit": limit} | source_filter(source_ids))
        return [Hit(section=CurrentSection.model_validate(row), score=row["score"]) for row in records(rows)]

    def nearest(self, model: str, vector: np.ndarray, source_ids: list[str], limit: int) -> list[Hit]:
        rows = self._connection.execute(EMBEDDED_SECTIONS, {"model": model} | source_filter(source_ids))
        sections: list[CurrentSection] = []
        vectors: list[bytes] = []
        for row in records(rows):
            section = CurrentSection.model_validate(row)
            if section.input_sha256 == row["input_sha256"]:
                sections.append(section)
                vectors.append(row["vector"])
        if not sections:
            return []
        scores = np.frombuffer(b"".join(vectors), dtype=np.float32).reshape(len(sections), -1) @ vector
        return [Hit(section=sections[index], score=float(scores[index])) for index in np.argsort(-scores)[:limit]]
