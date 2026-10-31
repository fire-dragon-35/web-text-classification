import typer

from cli import classify, crawl

app = typer.Typer(no_args_is_help=True, add_completion=False)
app.command("crawl", help="Crawl the sources and store their pages and sections.")(crawl.main)
app.command("classify", help="Classify the stored sections against a taxonomy.")(classify.main)

app()
