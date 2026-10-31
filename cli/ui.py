import logging
from collections import Counter
from collections.abc import Mapping
from enum import StrEnum

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.text import Text

INTERRUPTED_EXIT_CODE = 130
MIN_LABEL_WIDTH = 20

console = Console()


def outcome_line(styles: Mapping[StrEnum, tuple[str, str]], outcome: StrEnum, label: str, detail: str) -> Text:
    symbol, style = styles[outcome]
    prefix = f"  {symbol} {outcome:<10} "
    suffix = f"  {detail}" if detail else ""
    text = Text(label)
    text.truncate(max(console.width - len(prefix) - len(suffix), MIN_LABEL_WIDTH), overflow="ellipsis")
    return Text.assemble((prefix, style), text, (suffix, "dim"))


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
