import time
from collections import Counter
from enum import StrEnum
from typing import Annotated
from urllib.parse import urlsplit

import typer
from rich.table import Table
from rich.text import Text

from cli.ui import (
    DB,
    SOURCES_FILE,
    DbOption,
    SourcesFileArgument,
    configure_logging,
    console,
    finish,
    load_sources,
    outcome_line,
)
from db import PageStore
from db.sqlite.database import SqliteDatabase
from extraction.crawl import Crawler, CrawlOutcome, Robots
from extraction.http import Http
from extraction.sources import Source

STYLES = {
    CrawlOutcome.STORED: ("✓", "green"),
    CrawlOutcome.UNCHANGED: ("=", "dim"),
    CrawlOutcome.FLAGGED: ("⚠", "yellow"),
    CrawlOutcome.SKIPPED: ("–", "cyan"),
    CrawlOutcome.FAILED: ("✗", "red"),
    CrawlOutcome.DISALLOWED: ("⊘", "magenta"),
}
LONGEST_SECTIONS = 10


def _relative(url: str, start: str) -> str:
    target = urlsplit(url)
    if target.netloc != urlsplit(start).netloc:
        return url
    return target.path + (f"?{target.query}" if target.query else "")


def _selected(sources: list[Source], only: list[str] | None) -> list[Source]:
    if not only:
        return sources
    unknown = set(only) - {source.id for source in sources}
    if unknown:
        raise typer.BadParameter(f"no source with id {', '.join(sorted(unknown))}", param_hint="--only")
    return [source for source in sources if source.id in only]


def _longest(pages: PageStore, sources: list[Source]) -> Table:
    table = Table(title=f"{LONGEST_SECTIONS} longest sections")
    table.add_column("Source")
    table.add_column("Heading")
    table.add_column("Characters", justify="right")
    for source_id, heading, characters in pages.longest_sections([source.id for source in sources], LONGEST_SECTIONS):
        table.add_row(source_id, heading, f"{characters:,}")
    return table


def main(
    sources_file: SourcesFileArgument = SOURCES_FILE,
    only: Annotated[list[str] | None, typer.Option(help="Only crawl the source with this id. Repeatable.")] = None,
    db: DbOption = DB,
    verbose: Annotated[bool, typer.Option(help="Log every request and error details.")] = False,
) -> None:
    configure_logging(verbose)
    sources = _selected(load_sources(sources_file), only)
    http = Http()
    robots = Robots(http)
    counts: Counter[StrEnum] = Counter()
    started = time.monotonic()
    interrupted = False
    longest = None
    with SqliteDatabase(db) as database:
        try:
            with console.status("Crawling…") as status:
                for source in sources:
                    console.print(Text.assemble(("Crawling ", "bold"), source.id))
                    for result in Crawler(http, robots, database.pages, source).crawl():
                        label = _relative(result.url, source.urls[0])
                        console.print(outcome_line(STYLES, result.outcome, label, result.detail))
                        counts[result.outcome] += 1
                        status.update(f"Crawling {source.id} · {sum(counts.values())} pages")
            longest = _longest(database.pages, sources)
        except KeyboardInterrupt:
            interrupted = True
            console.print("Interrupted", style="bold yellow")
    finish("Crawl summary", "Pages", STYLES, counts, CrawlOutcome.FAILED, db, time.monotonic() - started, interrupted, longest)
