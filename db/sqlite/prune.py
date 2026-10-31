import json
import sqlite3
from collections.abc import Sequence

from db.sqlite import current_sections, records
from extraction.models import PageVersion

PAGE_VERSIONS = """
SELECT page.id, page.source_id, page.url, page.final_url, page.fetched_at, page.text_sha256,
       count(section.id) AS sections
FROM page
LEFT JOIN section ON section.page_id = page.id
GROUP BY page.id
ORDER BY page.url, page.fetched_at
"""

DELETE_SECTIONS = "DELETE FROM section WHERE page_id IN (SELECT value FROM json_each(?))"

DELETE_PAGES = "DELETE FROM page WHERE id IN (SELECT value FROM json_each(?))"

DELETE_STALE_EMBEDDINGS = "DELETE FROM embedding WHERE input_sha256 NOT IN (SELECT value FROM json_each(?))"


class SqlitePrune:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def page_versions(self) -> list[PageVersion]:
        return [PageVersion.model_validate(row) for row in records(self._connection.execute(PAGE_VERSIONS))]

    def prune(self, page_ids: Sequence[int], apply: bool) -> int:
        ids = json.dumps(list(page_ids))
        try:
            self._connection.execute(DELETE_SECTIONS, (ids,))
            self._connection.execute(DELETE_PAGES, (ids,))
            current = json.dumps(list({section.input_sha256 for section in current_sections(self._connection, [])}))
            embeddings = self._connection.execute(DELETE_STALE_EMBEDDINGS, (current,)).rowcount
        except BaseException:
            self._connection.rollback()
            raise
        if not apply:
            self._connection.rollback()
            return embeddings
        self._connection.commit()
        self._connection.execute("VACUUM")
        return embeddings
