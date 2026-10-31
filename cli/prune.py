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
from db.sqlite.database import SqliteDatabase
from extraction.models import PageVersion
from extraction.registry import Extractors
from extraction.scope import Scope
from extraction.sources import Source


class PruneReason(StrEnum):
    REMOVED_SOURCE = "removed source"
    OUT_OF_SCOPE = "out of scope"
    DUPLICATE = "duplicate version"


def _scopes(sources: list[Source], versions: list[PageVersion]) -> dict[str, Scope]:
    scopes = {source.id: Scope(source, Extractors(source)) for source in sources}
    for version in versions:
        if version.source_id in scopes:
            scopes[version.source_id].redirected(version.url, version.final_url)
    return scopes


def _reasons(versions: list[PageVersion], sources: list[Source]) -> dict[int, PruneReason]:
    scopes = _scopes(sources, versions)
    reasons: dict[int, PruneReason] = {}
    previous: dict[str, str] = {}
    for version in versions:
        scope = scopes.get(version.source_id)
        if scope is None:
            reasons[version.id] = PruneReason.REMOVED_SOURCE
        elif not scope.includes(version.url):
            reasons[version.id] = PruneReason.OUT_OF_SCOPE
        elif previous.get(version.url) == version.text_sha256:
            reasons[version.id] = PruneReason.DUPLICATE
        previous[version.url] = version.text_sha256
    return reasons


def _table(versions: list[PageVersion], reasons: dict[int, PruneReason]) -> Table:
    pages: Counter[tuple[str, PruneReason]] = Counter()
    sections: Counter[tuple[str, PruneReason]] = Counter()
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
    with SqliteDatabase(db) as database:
        versions = database.prune.page_versions()
        reasons = _reasons(versions, sources)
        embeddings = database.prune.prune(list(reasons), apply)
    if not reasons and not embeddings:
        console.print("Nothing to prune")
        return
    console.print(_table(versions, reasons))
    console.print(f"Embeddings {embeddings}")
    console.print(f"Deleted from {db}" if apply else "Dry run, nothing changed. Run with --apply to delete.", style="dim")
