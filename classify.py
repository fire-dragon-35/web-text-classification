import os
import time
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.text import Text

from classification.claude import Claude
from classification.classifier import Classifier, Outcome, classify_section
from classification.taxonomy import Taxonomy
from cli import configure_logging, console, finish, outcome_line
from extraction.models import Section
from storage import Storage
from storage.sqlite import SqliteStorage

STYLES = {
    Outcome.CLASSIFIED: ("✓", "green"),
    Outcome.REUSED: ("=", "dim"),
    Outcome.FAILED: ("✗", "red"),
}
ENVIRONMENT_VARIABLES = ("ANTHROPIC_API_KEY", "CLASSIFICATION_MODEL")


def _environment() -> tuple[str, str]:
    missing = [name for name in ENVIRONMENT_VARIABLES if not os.environ.get(name)]
    if missing:
        raise typer.BadParameter(f"set {', '.join(missing)} in the environment", param_hint="environment")
    return os.environ["ANTHROPIC_API_KEY"], os.environ["CLASSIFICATION_MODEL"]


def _taxonomy(path: Path) -> Taxonomy:
    try:
        return Taxonomy.load(path)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--taxonomy") from None


def _sections(storage: Storage, only: list[str]) -> list[tuple[str, str, Section]]:
    sections = storage.current_sections(only)
    unknown = set(only) - {source_id for source_id, _, _ in sections}
    if unknown:
        raise typer.BadParameter(f"no stored sections for source {', '.join(sorted(unknown))}", param_hint="--only")
    return sections


def _label(section: Section) -> str:
    return f"{section.ref} {section.heading}" if section.ref else section.heading


def main(
    taxonomy: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Taxonomy file, e.g. LIST_taxonomy.json.")],
    only: Annotated[list[str] | None, typer.Option(help="Only classify the source with this id. Repeatable.")] = None,
    max_depth: Annotated[int, typer.Option(min=1, help="Number of taxonomy levels to classify.")] = 2,
    db: Annotated[str, typer.Option(help="SQLite database file.")] = "documents.db",
    verbose: Annotated[bool, typer.Option(help="Log every request and error details.")] = False,
) -> None:
    configure_logging(verbose)
    api_key, model = _environment()
    classifier = Classifier(Claude(api_key, model), _taxonomy(taxonomy), max_depth)
    storage = SqliteStorage(db)
    counts: Counter[StrEnum] = Counter()
    started = time.monotonic()
    interrupted = False
    try:
        sections = _sections(storage, only or [])
        with console.status("Classifying…") as status:
            source = None
            for source_id, title, section in sections:
                if source_id != source:
                    source = source_id
                    console.print(Text.assemble(("Classifying ", "bold"), source_id))
                result = classify_section(storage, classifier, title, section)
                detail = result.detail or ", ".join(result.categories) or "none"
                console.print(outcome_line(STYLES, result.outcome, _label(section), detail))
                counts[result.outcome] += 1
                status.update(f"Classifying {source_id} · {sum(counts.values())} sections")
    except KeyboardInterrupt:
        interrupted = True
        console.print("Interrupted", style="bold yellow")
    finally:
        storage.close()
    finish(f"Classification summary · {classifier.name}", "Sections", STYLES, counts, Outcome.FAILED, db, time.monotonic() - started, interrupted)


if __name__ == "__main__":
    typer.run(main)
