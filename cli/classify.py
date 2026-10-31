import os
import time
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.text import Text

from classification.batch import BatchRun
from classification.classifier import Classifier, Outcome, Result, classify_section
from classification.claude import Claude
from classification.models import ClassifiedSection, Usage
from classification.taxonomy import Taxonomy
from cli.ui import configure_logging, console, finish, outcome_line
from db import Storage
from db.sqlite import SqliteStorage
from extraction.models import Section

STYLES = {
    Outcome.CLASSIFIED: ("✓", "green"),
    Outcome.REUSED: ("=", "dim"),
    Outcome.SKIPPED: ("–", "cyan"),
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


def _sections(storage: Storage, classifier: Classifier, only: list[str]) -> list[ClassifiedSection]:
    sections = storage.classified_sections(classifier.name, classifier.taxonomy.sha256, classifier.max_depth, only)
    unknown = set(only) - {item.source_id for item in sections}
    if unknown:
        raise typer.BadParameter(f"no stored sections for source {', '.join(sorted(unknown))}", param_hint="--only")
    return sections


def _known(item: ClassifiedSection, min_chars: int) -> Result | None:
    if len(item.section.text) < min_chars:
        return Result(Outcome.SKIPPED, [], f"{len(item.section.text)} chars")
    if item.categories is not None:
        return Result(Outcome.REUSED, item.categories)
    return None


def _print_usage(usage: Usage) -> None:
    console.print(
        f"Tokens · {usage.input_tokens} input · {usage.cache_creation_input_tokens} cache write · "
        f"{usage.cache_read_input_tokens} cache read · {usage.output_tokens} output · "
        f"cache hit ratio {usage.cache_hit_ratio:.0%}",
        style="dim",
    )


def _label(section: Section) -> str:
    return f"{section.ref} {section.heading}" if section.ref else section.heading


def main(
    taxonomy: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Taxonomy file.")] = Path("config/categories.json"),
    only: Annotated[list[str] | None, typer.Option(help="Only classify the source with this id. Repeatable.")] = None,
    max_depth: Annotated[int, typer.Option(min=1, help="Number of taxonomy levels to classify.")] = 2,
    min_chars: Annotated[int, typer.Option(min=0, help="Skip sections with shorter text.")] = 200,
    batch: Annotated[bool, typer.Option(help="Classify through the Message Batches API, one batch per level.")] = False,
    db: Annotated[str, typer.Option(help="SQLite database file.")] = ".assets/documents.db",
    verbose: Annotated[bool, typer.Option(help="Log every request and error details.")] = False,
) -> None:
    configure_logging(verbose)
    api_key, model = _environment()
    classifier = Classifier(Claude(api_key, model), _taxonomy(taxonomy), max_depth)
    storage = SqliteStorage(db)
    counts: Counter[StrEnum] = Counter()
    usage_by_text: dict[str, Usage] = {}
    started = time.monotonic()
    interrupted = False
    try:
        sections = _sections(storage, classifier, only or [])
        with console.status("Classifying…") as status:
            batch_results: dict[str, Result] = {}
            if batch:
                pending = [item for item in sections if _known(item, min_chars) is None]
                batch_results = BatchRun(storage, classifier, status.update).run(pending)
            source = None
            for item in sections:
                if item.source_id != source:
                    source = item.source_id
                    console.print(Text.assemble(("Classifying ", "bold"), item.source_id))
                result = _known(item, min_chars) or (
                    batch_results[item.section.text_sha256] if batch else classify_section(storage, classifier, item)
                )
                if result.usage:
                    usage_by_text[item.section.text_sha256] = result.usage
                detail = result.detail or ", ".join(result.categories) or "none"
                console.print(outcome_line(STYLES, result.outcome, _label(item.section), detail))
                counts[result.outcome] += 1
                status.update(f"Classifying {item.source_id} · {sum(counts.values())} sections")
    except KeyboardInterrupt:
        interrupted = True
        console.print("Interrupted", style="bold yellow")
    finally:
        storage.close()
    _print_usage(sum(usage_by_text.values(), Usage()))
    console.print(f"Classifier {classifier.name}", style="dim")
    finish("Classification summary", "Sections", STYLES, counts, Outcome.FAILED, db, time.monotonic() - started, interrupted)
