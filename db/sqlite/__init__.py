import json
import sqlite3
from typing import Any

from search.models import CurrentSection

CURRENT_SECTIONS = """
SELECT id, source_id, url, page_title, heading, ref, text, text_sha256
FROM current_section
WHERE :all_sources OR source_id IN (SELECT value FROM json_each(:source_ids))
ORDER BY source_id, url, ordinal
"""


def records(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor]


def source_filter(source_ids: list[str]) -> dict[str, object]:
    return {"all_sources": not source_ids, "source_ids": json.dumps(source_ids)}


def current_sections(connection: sqlite3.Connection, source_ids: list[str]) -> list[CurrentSection]:
    return [
        CurrentSection.model_validate(row)
        for row in records(connection.execute(CURRENT_SECTIONS, source_filter(source_ids)))
    ]
