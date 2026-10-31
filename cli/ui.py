import logging
from collections import Counter
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console, RenderableType
from rich.logging import RichHandler
from rich.table import Table
from rich.text import Text

from extraction.sources import Source, SourcesFile

INTERRUPTED_EXIT_CODE = 130
MIN_LABEL_WIDTH = 20
SOURCES_FILE = Path("config/sources.yaml")
DB = ".assets/documents.db"

SourcesFileArgument = Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Sources file.")]
DbOption = Annotated[str, typer.Option(help="SQLite database file.")]

console = Console()


def outcome_line(styles: Mapping[StrEnum, tuple[str, str]], outcome: StrEnum, label: str, detail: str) -> Text:
    symbol, style = styles[outcome]
    prefix = f"  {symbol} {outcome:<10} "
    suffix = f"  {detail}" if detail else ""
    text = Text(label)
    text.truncate(max(console.width - len(prefix) - len(suffix), MIN_LABEL_WIDTH), overflow="ellipsis")
    return Text.assemble((prefix, style), text, (suffix, "dim"))


def load_sources(path: Path) -> list[Source]:
    try:
        return SourcesFile.model_validate(yaml.safe_load(path.read_text())).sources
    except (yaml.YAMLError, ValidationError) as error:
        raise typer.BadParameter(str(error), param_hint="SOURCES_FILE") from None


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
    failed: StrEnum | None,
    db: str,
    seconds: float,
    interrupted: bool,
    footer: RenderableType | None = None,
) -> None:
    table = Table(title=title)
    table.add_column("Outcome")
    table.add_column(unit, justify="right")
    for outcome, (symbol, style) in styles.items():
        if counts[outcome]:
            table.add_row(Text(f"{symbol} {outcome}", style), str(counts[outcome]))
    console.print(table)
    console.print(f"Saved to {db} · {seconds:.0f} s", style="dim")
    if footer is not None:
        console.print(footer)
    if interrupted:
        raise typer.Exit(INTERRUPTED_EXIT_CODE)
    if failed and counts[failed]:
        raise typer.Exit(1)
