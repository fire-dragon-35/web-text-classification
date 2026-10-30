import json
import sqlite3

from extraction.models import FetchResult, Page, Section

SCHEMA = """
CREATE TABLE IF NOT EXISTS page (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    final_url TEXT NOT NULL,
    status INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    title TEXT NOT NULL,
    page_date TEXT,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    extractor TEXT NOT NULL,
    metadata TEXT NOT NULL,
    warnings TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS page_url_latest ON page (url, fetched_at DESC);

CREATE TABLE IF NOT EXISTS section (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES page (id),
    ordinal INTEGER NOT NULL,
    heading TEXT NOT NULL,
    level INTEGER NOT NULL,
    ref TEXT,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    UNIQUE (page_id, ordinal)
);

CREATE INDEX IF NOT EXISTS section_text_sha256 ON section (text_sha256);

CREATE VIEW IF NOT EXISTS current_page AS
SELECT * FROM (
    SELECT page.*, row_number() OVER (PARTITION BY url ORDER BY fetched_at DESC) AS version
    FROM page
) AS ranked
WHERE version = 1;

CREATE VIEW IF NOT EXISTS current_section AS
SELECT section.*, current_page.url, current_page.title AS page_title, current_page.fetched_at
FROM section
JOIN current_page ON current_page.id = section.page_id;
"""

INSERT_PAGE = """
INSERT INTO page (
    url, final_url, status, content_type, fetched_at, raw_sha256,
    title, page_date, text, text_sha256, extractor, metadata, warnings
) VALUES (
    :url, :final_url, :status, :content_type, :fetched_at, :raw_sha256,
    :title, :page_date, :text, :text_sha256, :extractor, :metadata, :warnings
)
RETURNING id
"""

INSERT_SECTION = """
INSERT INTO section (page_id, ordinal, heading, level, ref, text, text_sha256)
VALUES (:page_id, :ordinal, :heading, :level, :ref, :text, :text_sha256)
"""

LATEST = "SELECT raw_sha256, text_sha256 FROM page WHERE url = ? ORDER BY fetched_at DESC LIMIT 1"


def _page_row(fetch: FetchResult, page: Page) -> dict[str, object]:
    row = fetch.model_dump(mode="json") | page.model_dump(mode="json")
    row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False)
    row["warnings"] = json.dumps(row["warnings"], ensure_ascii=False)
    return row


class SqliteStorage:
    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.executescript(SCHEMA)

    def latest(self, url: str) -> tuple[str, str] | None:
        return self._connection.execute(LATEST, (url,)).fetchone()

    def save(self, fetch: FetchResult, page: Page, sections: list[Section]) -> None:
        with self._connection:
            (page_id,) = self._connection.execute(INSERT_PAGE, _page_row(fetch, page)).fetchone()
            self._connection.executemany(
                INSERT_SECTION,
                [section.model_dump() | {"page_id": page_id} for section in sections],
            )

    def close(self) -> None:
        self._connection.close()
