import json
import sqlite3
from collections.abc import Sequence

from classification.models import Classification, ClassifiedSection, Pending, Usage
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
    input_tokens INTEGER,
    cache_creation_input_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    output_tokens INTEGER,
    PRIMARY KEY (text_sha256, classifier, taxonomy_sha256, max_depth)
);

CREATE TABLE IF NOT EXISTS pending_classification (
    text_sha256 TEXT NOT NULL,
    classifier TEXT NOT NULL,
    taxonomy_sha256 TEXT NOT NULL,
    max_depth INTEGER NOT NULL,
    section_text TEXT NOT NULL,
    level INTEGER NOT NULL,
    chosen TEXT NOT NULL,
    categories TEXT NOT NULL,
    usage TEXT NOT NULL,
    batch_id TEXT,
    PRIMARY KEY (text_sha256, classifier, taxonomy_sha256, max_depth)
);

-- One row per current section and classification: a section classified with several
-- classifiers, taxonomies or depths appears once for each of them.
CREATE VIEW IF NOT EXISTS section_classification AS
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

CLASSIFIED_SECTIONS = """
SELECT current_section.source_id, current_section.page_title, current_section.ordinal, current_section.heading,
       current_section.level, current_section.ref, current_section.text, classification.categories
FROM current_section
LEFT JOIN classification
    ON classification.text_sha256 = current_section.text_sha256
    AND classification.classifier = :classifier
    AND classification.taxonomy_sha256 = :taxonomy_sha256
    AND classification.max_depth = :max_depth
WHERE :all_sources OR current_section.source_id IN (SELECT value FROM json_each(:source_ids))
ORDER BY current_section.source_id, current_section.url, current_section.ordinal
"""

INSERT_CLASSIFICATION = """
INSERT INTO classification (
    text_sha256, classifier, taxonomy_sha256, max_depth, categories, classified_at,
    input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens
) VALUES (
    :text_sha256, :classifier, :taxonomy_sha256, :max_depth, :categories, :classified_at,
    :input_tokens, :cache_creation_input_tokens, :cache_read_input_tokens, :output_tokens
)
ON CONFLICT DO NOTHING
"""

PENDING = """
SELECT text_sha256, classifier, taxonomy_sha256, max_depth, section_text, level, chosen, categories, usage, batch_id
FROM pending_classification
WHERE classifier = ? AND taxonomy_sha256 = ? AND max_depth = ?
"""

SAVE_PENDING = """
INSERT OR REPLACE INTO pending_classification (
    text_sha256, classifier, taxonomy_sha256, max_depth, section_text, level, chosen, categories, usage, batch_id
) VALUES (
    :text_sha256, :classifier, :taxonomy_sha256, :max_depth, :section_text, :level, :chosen, :categories, :usage, :batch_id
)
"""

DELETE_PENDING = """
DELETE FROM pending_classification
WHERE text_sha256 = :text_sha256 AND classifier = :classifier AND taxonomy_sha256 = :taxonomy_sha256
    AND max_depth = :max_depth
"""

PENDING_JSON_COLUMNS = ("chosen", "categories", "usage")

LATEST_CLASSIFICATION = """
SELECT categories FROM classification
WHERE text_sha256 = ? AND classifier = ? AND taxonomy_sha256 = ? AND max_depth = ?
"""


def _classification_row(classification: Classification) -> dict[str, object]:
    row = classification.model_dump(mode="json")
    row["categories"] = json.dumps(row["categories"], ensure_ascii=False)
    return row | row.pop("usage")


def _pending_row(pending: Pending) -> dict[str, object]:
    row = pending.model_dump(mode="json")
    return row | {column: json.dumps(row[column], ensure_ascii=False) for column in PENDING_JSON_COLUMNS}


def _page_row(source_id: str, fetch: FetchResult, page: Page) -> dict[str, object]:
    row = {"source_id": source_id} | fetch.model_dump(mode="json") | page.model_dump(mode="json")
    row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False)
    row["warnings"] = json.dumps(row["warnings"], ensure_ascii=False)
    return row


class SqliteStorage:
    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.executescript(SCHEMA)
        self._add_usage_columns()

    def _add_usage_columns(self) -> None:
        columns = {row[1] for row in self._connection.execute("PRAGMA table_info(classification)")}
        with self._connection:
            for column in Usage.model_fields:
                if column not in columns:
                    self._connection.execute(f"ALTER TABLE classification ADD COLUMN {column} INTEGER")

    def latest(self, url: str) -> tuple[str, str] | None:
        return self._connection.execute(LATEST, (url,)).fetchone()

    def save(self, source_id: str, fetch: FetchResult, page: Page, sections: list[Section]) -> None:
        with self._connection:
            (page_id,) = self._connection.execute(INSERT_PAGE, _page_row(source_id, fetch, page)).fetchone()
            self._connection.executemany(
                INSERT_SECTION,
                [section.model_dump() | {"page_id": page_id} for section in sections],
            )

    def classified_sections(
        self, classifier: str, taxonomy_sha256: str, max_depth: int, source_ids: list[str]
    ) -> list[ClassifiedSection]:
        rows = self._connection.execute(
            CLASSIFIED_SECTIONS,
            {
                "classifier": classifier,
                "taxonomy_sha256": taxonomy_sha256,
                "max_depth": max_depth,
                "all_sources": not source_ids,
                "source_ids": json.dumps(source_ids),
            },
        )
        return [
            ClassifiedSection(
                source_id=source_id,
                page_title=page_title,
                section=Section(ordinal=ordinal, heading=heading, level=level, ref=ref, text=text),
                categories=json.loads(categories) if categories else None,
            )
            for source_id, page_title, ordinal, heading, level, ref, text, categories in rows
        ]

    def latest_classification(
        self, text_sha256: str, classifier: str, taxonomy_sha256: str, max_depth: int
    ) -> list[str] | None:
        row = self._connection.execute(
            LATEST_CLASSIFICATION, (text_sha256, classifier, taxonomy_sha256, max_depth)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def save_classification(self, classification: Classification) -> None:
        with self._connection:
            self._connection.execute(INSERT_CLASSIFICATION, _classification_row(classification))

    def pending(self, classifier: str, taxonomy_sha256: str, max_depth: int) -> list[Pending]:
        cursor = self._connection.execute(PENDING, (classifier, taxonomy_sha256, max_depth))
        columns = [column[0] for column in cursor.description]
        rows = (dict(zip(columns, row)) for row in cursor)
        return [
            Pending.model_validate(row | {column: json.loads(row[column]) for column in PENDING_JSON_COLUMNS})
            for row in rows
        ]

    def update_pending(
        self,
        save: Sequence[Pending] = (),
        delete: Sequence[Pending] = (),
        classifications: Sequence[Classification] = (),
    ) -> None:
        with self._connection:
            self._connection.executemany(SAVE_PENDING, [_pending_row(pending) for pending in save])
            self._connection.executemany(DELETE_PENDING, [_pending_row(pending) for pending in delete])
            self._connection.executemany(
                INSERT_CLASSIFICATION, [_classification_row(classification) for classification in classifications]
            )

    def close(self) -> None:
        self._connection.close()
