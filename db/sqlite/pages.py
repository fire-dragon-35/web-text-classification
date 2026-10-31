import json
import sqlite3

from extraction.models import FetchResult, Page, Section

INSERT_PAGE = """
INSERT INTO page (
    source_id, url, final_url, status, content_type, fetched_at, raw_sha256,
    title, page_date, text, text_sha256, extractor, metadata, warnings
) VALUES (
    :source_id, :url, :final_url, :status, :content_type, :fetched_at, :raw_sha256,
    :title, :page_date, :text, :text_sha256, :extractor, :metadata, :warnings
)
RETURNING id
"""

INSERT_SECTION = """
INSERT INTO section (page_id, ordinal, heading, level, ref, text, text_sha256)
VALUES (:page_id, :ordinal, :heading, :level, :ref, :text, :text_sha256)
"""

LATEST = "SELECT raw_sha256, text_sha256 FROM page WHERE url = ? ORDER BY fetched_at DESC LIMIT 1"

LONGEST_SECTIONS = """
SELECT source_id, heading, length(text) FROM current_section
WHERE source_id IN (SELECT value FROM json_each(?))
ORDER BY length(text) DESC
LIMIT ?
"""


def _page_row(source_id: str, fetch: FetchResult, page: Page) -> dict[str, object]:
    row = {"source_id": source_id} | fetch.model_dump(mode="json") | page.model_dump(mode="json")
    row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False)
    row["warnings"] = json.dumps(row["warnings"], ensure_ascii=False)
    return row


class SqlitePages:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def latest(self, url: str) -> tuple[str, str] | None:
        return self._connection.execute(LATEST, (url,)).fetchone()

    def save(self, source_id: str, fetch: FetchResult, page: Page, sections: list[Section]) -> None:
        with self._connection:
            (page_id,) = self._connection.execute(INSERT_PAGE, _page_row(source_id, fetch, page)).fetchone()
            self._connection.executemany(
                INSERT_SECTION,
                [section.model_dump() | {"page_id": page_id} for section in sections],
            )

    def longest_sections(self, source_ids: list[str], limit: int) -> list[tuple[str, str, int]]:
        return self._connection.execute(LONGEST_SECTIONS, (json.dumps(source_ids), limit)).fetchall()
