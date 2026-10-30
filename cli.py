import logging
import time
from collections import Counter
from typing import Annotated
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.text import Text

from extraction.crawl import Outcome, Result, crawl
from extraction.http import Http
from extraction.website import Website
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
MIN_URL_WIDTH = 20

console = Console()


def _relative(url: str, start: str) -> str:
    target = urlsplit(url)
    if target.netloc != urlsplit(start).netloc:
        return url
    return target.path + (f"?{target.query}" if target.query else "")


def _line(result: Result, start: str) -> Text:
    symbol, style = STYLES[result.outcome]
    prefix = f"  {symbol} {result.outcome:<10} "
    suffix = f"  {result.detail}" if result.detail else ""
    url = Text(_relative(result.url, start))
    url.truncate(max(console.width - len(prefix) - len(suffix), MIN_URL_WIDTH), overflow="ellipsis")
    return Text.assemble((prefix, style), url, (suffix, "dim"))


def _summary(counts: Counter[Outcome], db: str, seconds: float) -> None:
    table = Table(title="Crawl summary")
    table.add_column("Outcome")
    table.add_column("Pages", justify="right")
    for outcome, (symbol, style) in STYLES.items():
        if counts[outcome]:
            table.add_row(Text(f"{symbol} {outcome}", style), str(counts[outcome]))
    console.print(table)
    console.print(f"Saved to {db} · {seconds:.0f} s", style="dim")


def main(
    urls: Annotated[list[str], typer.Argument(help="URLs to crawl from.")],
    selector: Annotated[str | None, typer.Option(help="CSS selector for the main content, e.g. main.")] = None,
    exclude: Annotated[list[str] | None, typer.Option(help="CSS selector to remove before extraction. Repeatable.")] = None,
    max_pages: Annotated[int, typer.Option(min=1, help="Maximum pages to fetch per URL.")] = 5,
    db: Annotated[str, typer.Option(help="SQLite database file.")] = "documents.db",
    verbose: Annotated[bool, typer.Option(help="Log every request and error details.")] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False)],
    )
    if not verbose:
        logging.getLogger("trafilatura").setLevel(logging.CRITICAL)
    website = Website(selector, tuple(exclude or ()))
    http = Http()
    storage = SqliteStorage(db)
    counts: Counter[Outcome] = Counter()
    started = time.monotonic()
    interrupted = False
    try:
        with console.status("Crawling…") as status:
            for start in urls:
                console.print(Text.assemble(("Crawling ", "bold"), start))
                for result in crawl(http, storage, start, website, max_pages):
                    console.print(_line(result, start))
                    counts[result.outcome] += 1
                    status.update(f"Crawling {start} · {sum(counts.values())} pages")
    except KeyboardInterrupt:
        interrupted = True
        console.print("Interrupted", style="bold yellow")
    finally:
        storage.close()
    _summary(counts, db, time.monotonic() - started)
    if interrupted:
        raise typer.Exit(INTERRUPTED_EXIT_CODE)
    if counts[Outcome.FAILED]:
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
