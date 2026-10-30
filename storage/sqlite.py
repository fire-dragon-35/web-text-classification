import json
import sqlite3

from classification.models import Classification
from extraction.models import FetchResult, Page, Section

SCHEMA = """
CREATE TABLE IF NOT EXISTS page (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
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
SELECT section.*, current_page.source_id, current_page.url, current_page.title AS page_title, current_page.fetched_at
FROM section
JOIN current_page ON current_page.id = section.page_id;

CREATE TABLE IF NOT EXISTS classification (
    text_sha256 TEXT NOT NULL,
    classifier TEXT NOT NULL,
    taxonomy_sha256 TEXT NOT NULL,
    max_depth INTEGER NOT NULL,
    categories TEXT NOT NULL,
    classified_at TEXT NOT NULL,
    PRIMARY KEY (text_sha256, classifier, taxonomy_sha256, max_depth)
);

CREATE VIEW IF NOT EXISTS classified_section AS
SELECT current_section.*, classification.classifier, classification.taxonomy_sha256,
       classification.max_depth, classification.categories, classification.classified_at
FROM current_section
JOIN classification ON classification.text_sha256 = current_section.text_sha256;
"""

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

CURRENT_SECTIONS = """
SELECT source_id, page_title, ordinal, heading, level, ref, text FROM current_section
WHERE ? OR source_id IN (SELECT value FROM json_each(?))
ORDER BY source_id, url, ordinal
"""

INSERT_CLASSIFICATION = """
INSERT INTO classification (text_sha256, classifier, taxonomy_sha256, max_depth, categories, classified_at)
VALUES (:text_sha256, :classifier, :taxonomy_sha256, :max_depth, :categories, :classified_at)
"""

LATEST_CLASSIFICATION = """
SELECT categories FROM classification
WHERE text_sha256 = ? AND classifier = ? AND taxonomy_sha256 = ? AND max_depth = ?
"""


def _page_row(source_id: str, fetch: FetchResult, page: Page) -> dict[str, object]:
    row = {"source_id": source_id} | fetch.model_dump(mode="json") | page.model_dump(mode="json")
    row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False)
    row["warnings"] = json.dumps(row["warnings"], ensure_ascii=False)
    return row


class SqliteStorage:
    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.executescript(SCHEMA)

    def latest(self, url: str) -> tuple[str, str] | None:
        return self._connection.execute(LATEST, (url,)).fetchone()

    def save(self, source_id: str, fetch: FetchResult, page: Page, sections: list[Section]) -> None:
        with self._connection:
            (page_id,) = self._connection.execute(INSERT_PAGE, _page_row(source_id, fetch, page)).fetchone()
            self._connection.executemany(
                INSERT_SECTION,
                [section.model_dump() | {"page_id": page_id} for section in sections],
            )

    def current_sections(self, source_ids: list[str]) -> list[tuple[str, str, Section]]:
        rows = self._connection.execute(CURRENT_SECTIONS, (not source_ids, json.dumps(source_ids)))
        return [
            (source_id, title, Section(ordinal=ordinal, heading=heading, level=level, ref=ref, text=text))
            for source_id, title, ordinal, heading, level, ref, text in rows
        ]

    def latest_classification(
        self, text_sha256: str, classifier: str, taxonomy_sha256: str, max_depth: int
    ) -> list[str] | None:
        row = self._connection.execute(
            LATEST_CLASSIFICATION, (text_sha256, classifier, taxonomy_sha256, max_depth)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def save_classification(self, classification: Classification) -> None:
        row = classification.model_dump(mode="json")
        row["categories"] = json.dumps(row["categories"], ensure_ascii=False)
        with self._connection:
            self._connection.execute(INSERT_CLASSIFICATION, row)

    def close(self) -> None:
        self._connection.close()
