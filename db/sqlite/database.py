import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Self

from db.sqlite.embeddings import SqliteEmbeddings
from db.sqlite.pages import SqlitePages
from db.sqlite.prune import SqlitePrune
from db.sqlite.search import SqliteSearch

SCHEMA = Path(__file__).with_name("schema.sql")


class SqliteDatabase:
    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.executescript(SCHEMA.read_text())
        self.pages = SqlitePages(self._connection)
        self.prune = SqlitePrune(self._connection)
        self.embeddings = SqliteEmbeddings(self._connection)
        self.search = SqliteSearch(self._connection)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, error_type: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self._connection.close()
