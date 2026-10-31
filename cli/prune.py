from collections import Counter
from enum import StrEnum
from typing import Annotated

import typer
from rich.table import Table

from cli.ui import (
    DB,
    SOURCES_FILE,
    DbOption,
    SourcesFileArgument,
    console,
    load_sources,
)
from db.sqlite import SqliteStorage
from extraction.models import PageVersion
from extraction.scope import includes, start_scopes
from extraction.sources import Source


class Reason(StrEnum):
    REMOVED_SOURCE = "removed source"
    OUT_OF_SCOPE = "out of scope"
    DUPLICATE = "duplicate version"


def _scopes(source: Source, versions: list[PageVersion]) -> list[str]:
    starts = start_scopes(source)
    redirects = [version.final_url for version in versions if version.source_id == source.id and version.url in starts]
    return starts + redirects


def _reasons(versions: list[PageVersion], sources: list[Source]) -> dict[int, Reason]:
    by_id = {source.id: source for source in sources}
    scopes = {source.id: _scopes(source, versions) for source in sources}
    reasons: dict[int, Reason] = {}
    previous: dict[str, str] = {}
    for version in versions:
        source = by_id.get(version.source_id)
        if source is None:
            reasons[version.id] = Reason.REMOVED_SOURCE
        elif not includes(source, version.url, scopes[source.id]):
            reasons[version.id] = Reason.OUT_OF_SCOPE
        elif previous.get(version.url) == version.text_sha256:
            reasons[version.id] = Reason.DUPLICATE
        previous[version.url] = version.text_sha256
    return reasons


def _table(versions: list[PageVersion], reasons: dict[int, Reason]) -> Table:
    pages: Counter[tuple[str, Reason]] = Counter()
    sections: Counter[tuple[str, Reason]] = Counter()
    for version in versions:
        if version.id in reasons:
            key = (version.source_id, reasons[version.id])
            pages[key] += 1
            sections[key] += version.sections
    table = Table(title="Prune")
    table.add_column("Source")
    table.add_column("Reason")
    table.add_column("Pages", justify="right")
    table.add_column("Sections", justify="right")
    for source_id, reason in sorted(pages):
        table.add_row(source_id, reason, str(pages[source_id, reason]), str(sections[source_id, reason]))
    return table


def main(
    sources_file: SourcesFileArgument = SOURCES_FILE,
    db: DbOption = DB,
    apply: Annotated[bool, typer.Option(help="Delete the pages instead of only listing them.")] = False,
) -> None:
    sources = load_sources(sources_file)
    storage = SqliteStorage(db)
    try:
        versions = storage.page_versions()
        reasons = _reasons(versions, sources)
        result = storage.prune(list(reasons), apply)
    finally:
        storage.close()
    if not reasons and not result.classifications and not result.pending:
        console.print("Nothing to prune")
        return
    console.print(_table(versions, reasons))
    duplicates = sum(reason == Reason.DUPLICATE for reason in reasons.values())
    console.print(
        f"Duplicate versions {duplicates} · classifications {result.classifications} · pending {result.pending}"
    )
    console.print(f"Deleted from {db}" if apply else "Dry run, nothing changed. Run with --apply to delete.", style="dim")
