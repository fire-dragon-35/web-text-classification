import typer

from cli import crawl, embed, prune, search

app = typer.Typer(no_args_is_help=True, add_completion=False)
app.command("crawl", help="Crawl the sources and store their pages and sections.")(crawl.main)
app.command("prune", help="Delete stored pages that no longer match the sources file.")(prune.main)
app.command("embed", help="Embed the stored sections for vector search.")(embed.main)
app.command("search", help="Search the stored sections.")(search.main)

app()
