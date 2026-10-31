import time
from collections import Counter
from enum import StrEnum
from typing import Annotated

import typer
from rich.progress import Progress

from cli.ui import DB, DbOption, console, finish
from db import EmbeddingStore
from db.sqlite.database import SqliteDatabase
from search.embedder import Embedder
from search.embedding import EmbeddingRun, EmbedOutcome
from search.models import CurrentSection

STYLES = {
    EmbedOutcome.EMBEDDED: ("✓", "green"),
    EmbedOutcome.UNCHANGED: ("=", "dim"),
    EmbedOutcome.SKIPPED: ("–", "cyan"),
}


def _sections(store: EmbeddingStore, only: list[str]) -> list[CurrentSection]:
    sections = store.sections(only)
    unknown = set(only) - {section.source_id for section in sections}
    if unknown:
        raise typer.BadParameter(f"no stored sections for source {', '.join(sorted(unknown))}", param_hint="--only")
    return sections


def main(
    only: Annotated[list[str] | None, typer.Option(help="Only embed the source with this id. Repeatable.")] = None,
    min_chars: Annotated[int, typer.Option(min=0, help="Skip sections with shorter text.")] = 100,
    db: DbOption = DB,
) -> None:
    embedder = Embedder()
    counts: Counter[StrEnum] = Counter()
    started = time.monotonic()
    interrupted = False
    with SqliteDatabase(db) as database:
        store = database.embeddings
        run = EmbeddingRun(store, embedder, _sections(store, only or []), min_chars)
        counts[EmbedOutcome.SKIPPED] = run.skipped
        counts[EmbedOutcome.UNCHANGED] = run.unchanged
        try:
            with Progress(console=console) as progress:
                task = progress.add_task("Embedding", total=run.pending)
                for embedded in run.run():
                    counts[EmbedOutcome.EMBEDDED] += embedded
                    progress.advance(task, embedded)
        except KeyboardInterrupt:
            interrupted = True
            console.print("Interrupted", style="bold yellow")
    console.print(f"Model {embedder.name}", style="dim")
    finish("Embedding summary", "Sections", STYLES, counts, None, db, time.monotonic() - started, interrupted)
