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

CREATE VIRTUAL TABLE IF NOT EXISTS section_fts USING fts5 (
    heading, text, content = 'section', content_rowid = 'id', tokenize = 'unicode61 remove_diacritics 0'
);

CREATE TRIGGER IF NOT EXISTS section_fts_insert AFTER INSERT ON section BEGIN
    INSERT INTO section_fts (rowid, heading, text) VALUES (new.id, new.heading, new.text);
END;

CREATE TRIGGER IF NOT EXISTS section_fts_delete AFTER DELETE ON section BEGIN
    INSERT INTO section_fts (section_fts, rowid, heading, text) VALUES ('delete', old.id, old.heading, old.text);
END;

CREATE TABLE IF NOT EXISTS embedding (
    input_sha256 TEXT NOT NULL,
    model TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (input_sha256, model)
);

CREATE INDEX IF NOT EXISTS embedding_text_sha256 ON embedding (text_sha256, model);
