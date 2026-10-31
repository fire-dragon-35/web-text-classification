from typing import Annotated

import typer
from rich.text import Text

from cli.ui import DB, DbOption, console
from db.sqlite.database import SqliteDatabase
from search.embedder import Embedder
from search.models import Hit
from search.searcher import Searcher, SearchMode

SNIPPET_CHARS = 200


def _snippet(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= SNIPPET_CHARS else f"{flat[:SNIPPET_CHARS]}…"


def _print(rank: int, hit: Hit) -> None:
    section = hit.section
    label = " › ".join(part for part in (section.source_id, section.ref, section.heading) if part)
    console.print(Text.assemble((f"{rank:>2}. ", "bold"), (label, "bold"), (f"  {hit.score:.4f}", "dim")))
    console.print(Text(f"    {section.page_title} · {section.url}", "dim"))
    console.print(f"    {_snippet(section.text)}", highlight=False)


def main(
    query: Annotated[str, typer.Argument(help="Search query.")],
    only: Annotated[list[str] | None, typer.Option(help="Only search the source with this id. Repeatable.")] = None,
    limit: Annotated[int, typer.Option(min=1, help="Number of sections to return.")] = 10,
    mode: Annotated[SearchMode, typer.Option(help="Ranking to use.")] = SearchMode.HYBRID,
    terms: Annotated[str | None, typer.Option(help="Full-text terms to use instead of the query.")] = None,
    db: DbOption = DB,
) -> None:
    with SqliteDatabase(db) as database:
        hits = Searcher(database.search, Embedder()).search(query, only or [], limit, mode, terms)
    if not hits:
        console.print("No matches")
    for rank, hit in enumerate(hits, start=1):
        _print(rank, hit)
