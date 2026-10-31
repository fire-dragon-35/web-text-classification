import time
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import typer
import yaml
from pydantic import ValidationError
from rich.text import Text

from cli.ui import configure_logging, console, finish, outcome_line
from db.sqlite import SqliteStorage
from extraction.crawl import Outcome, crawl
from extraction.http import Http
from extraction.sources import Source, SourcesFile

STYLES = {
    Outcome.STORED: ("✓", "green"),
    Outcome.UNCHANGED: ("=", "dim"),
    Outcome.FLAGGED: ("⚠", "yellow"),
    Outcome.SKIPPED: ("–", "cyan"),
    Outcome.FAILED: ("✗", "red"),
    Outcome.DISALLOWED: ("⊘", "magenta"),
}


def _relative(url: str, start: str) -> str:
    target = urlsplit(url)
    if target.netloc != urlsplit(start).netloc:
        return url
    return target.path + (f"?{target.query}" if target.query else "")


def _load(path: Path) -> list[Source]:
    try:
        return SourcesFile.model_validate(yaml.safe_load(path.read_text())).sources
    except (yaml.YAMLError, ValidationError) as error:
        raise typer.BadParameter(str(error), param_hint="SOURCES_FILE") from None


def _selected(sources: list[Source], only: list[str] | None) -> list[Source]:
    if not only:
        return sources
    unknown = set(only) - {source.id for source in sources}
    if unknown:
        raise typer.BadParameter(f"no source with id {', '.join(sorted(unknown))}", param_hint="--only")
    return [source for source in sources if source.id in only]


def main(
    sources_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Sources file.")] = Path("config/sources.yaml"),
    only: Annotated[list[str] | None, typer.Option(help="Only crawl the source with this id. Repeatable.")] = None,
    db: Annotated[str, typer.Option(help="SQLite database file.")] = ".assets/documents.db",
    verbose: Annotated[bool, typer.Option(help="Log every request and error details.")] = False,
) -> None:
    configure_logging(verbose)
    sources = _selected(_load(sources_file), only)
    http = Http()
    storage = SqliteStorage(db)
    counts: Counter[StrEnum] = Counter()
    started = time.monotonic()
    interrupted = False
    try:
        with console.status("Crawling…") as status:
            for source in sources:
                console.print(Text.assemble(("Crawling ", "bold"), source.id))
                for result in crawl(http, storage, source):
                    console.print(outcome_line(STYLES, result.outcome, _relative(result.url, source.urls[0]), result.detail))
                    counts[result.outcome] += 1
                    status.update(f"Crawling {source.id} · {sum(counts.values())} pages")
    except KeyboardInterrupt:
        interrupted = True
        console.print("Interrupted", style="bold yellow")
    finally:
        storage.close()
    finish("Crawl summary", "Pages", STYLES, counts, Outcome.FAILED, db, time.monotonic() - started, interrupted)
