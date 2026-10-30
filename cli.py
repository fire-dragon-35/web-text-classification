import logging
import time
from collections import Counter
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.text import Text

from extraction.crawl import Outcome, crawl
from extraction.http import Http
from extraction.models import Source, SourcesFile
from storage.sqlite import SqliteStorage

STYLES = {
    Outcome.STORED: ("✓", "green"),
    Outcome.UNCHANGED: ("=", "dim"),
    Outcome.FLAGGED: ("⚠", "yellow"),
    Outcome.SKIPPED: ("–", "cyan"),
    Outcome.FAILED: ("✗", "red"),
    Outcome.DISALLOWED: ("⊘", "magenta"),
}
INTERRUPTED_EXIT_CODE = 130
MIN_LABEL_WIDTH = 20

console = Console()


def _relative(url: str, start: str) -> str:
    target = urlsplit(url)
    if target.netloc != urlsplit(start).netloc:
        return url
    return target.path + (f"?{target.query}" if target.query else "")


def outcome_line(styles: Mapping[StrEnum, tuple[str, str]], outcome: StrEnum, label: str, detail: str) -> Text:
    symbol, style = styles[outcome]
    prefix = f"  {symbol} {outcome:<10} "
    suffix = f"  {detail}" if detail else ""
    text = Text(label)
    text.truncate(max(console.width - len(prefix) - len(suffix), MIN_LABEL_WIDTH), overflow="ellipsis")
    return Text.assemble((prefix, style), text, (suffix, "dim"))


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


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False)],
    )
    if not verbose:
        logging.getLogger("trafilatura").setLevel(logging.CRITICAL)


def finish(
    title: str,
    unit: str,
    styles: Mapping[StrEnum, tuple[str, str]],
    counts: Counter[StrEnum],
    failed: StrEnum,
    db: str,
    seconds: float,
    interrupted: bool,
) -> None:
    table = Table(title=title)
    table.add_column("Outcome")
    table.add_column(unit, justify="right")
    for outcome, (symbol, style) in styles.items():
        if counts[outcome]:
            table.add_row(Text(f"{symbol} {outcome}", style), str(counts[outcome]))
    console.print(table)
    console.print(f"Saved to {db} · {seconds:.0f} s", style="dim")
    if interrupted:
        raise typer.Exit(INTERRUPTED_EXIT_CODE)
    if counts[failed]:
        raise typer.Exit(1)


def main(
    sources_file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Sources file, e.g. sources.yaml.")],
    only: Annotated[list[str] | None, typer.Option(help="Only crawl the source with this id. Repeatable.")] = None,
    db: Annotated[str, typer.Option(help="SQLite database file.")] = "documents.db",
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


if __name__ == "__main__":
    typer.run(main)
