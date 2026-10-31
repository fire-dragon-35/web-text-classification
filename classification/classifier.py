import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import NamedTuple

import anthropic

from classification.claude import ClassificationError, Claude
from classification.models import (
    Choice,
    Classification,
    ClassifiedSection,
    Pending,
    Term,
    Usage,
)
from classification.taxonomy import Taxonomy
from db import Storage
from extraction.models import sha256

SECTION = "Page title: {title}\nSection heading: {heading}\nRef: {ref}\n\n{text}"
PROMPT_HASH_LENGTH = 8
PLACEHOLDER_TERM = Term(code="{code}", name="{name}", definition="{definition}", parent="")


class Outcome(StrEnum):
    CLASSIFIED = "classified"
    REUSED = "reused"
    SKIPPED = "skipped"
    FAILED = "failed"


class Result(NamedTuple):
    outcome: Outcome
    categories: list[str]
    detail: str = ""
    usage: Usage | None = None


class Classifier:
    def __init__(self, claude: Claude, taxonomy: Taxonomy, max_depth: int) -> None:
        self.claude = claude
        self.taxonomy = taxonomy
        self.max_depth = max_depth

    @property
    def name(self) -> str:
        params = {key: value for key, value in self.claude.params([PLACEHOLDER_TERM], "").items() if key != "model"}
        request = json.dumps(params, sort_keys=True) + SECTION
        return f"{self.claude.model}#{sha256(request.encode())[:PROMPT_HASH_LENGTH]}"

    def pending(self, item: ClassifiedSection) -> Pending:
        section = item.section
        return Pending(
            text_sha256=section.text_sha256,
            classifier=self.name,
            taxonomy_sha256=self.taxonomy.sha256,
            max_depth=self.max_depth,
            section_text=SECTION.format(
                title=item.page_title, heading=section.heading, ref=section.ref or "", text=section.text
            ),
        )

    def terms(self, pending: Pending) -> list[Term]:
        if pending.level > self.max_depth:
            return []
        if pending.level == 1:
            return self.taxonomy.roots()
        return [child for code in pending.chosen for child in self.taxonomy.children(code)]

    def advance(self, pending: Pending, choice: Choice) -> Pending:
        return pending.model_copy(
            update={
                "level": pending.level + 1,
                "chosen": choice.codes,
                "categories": pending.categories + choice.codes,
                "usage": pending.usage + choice.usage,
                "batch_id": None,
            }
        )

    def classification(self, pending: Pending) -> Classification:
        return Classification(
            text_sha256=pending.text_sha256,
            classifier=pending.classifier,
            taxonomy_sha256=pending.taxonomy_sha256,
            max_depth=pending.max_depth,
            categories=pending.categories,
            classified_at=datetime.now(UTC),
            usage=pending.usage,
        )


def classify_section(storage: Storage, classifier: Classifier, item: ClassifiedSection) -> Result:
    pending = classifier.pending(item)
    try:
        while terms := classifier.terms(pending):
            pending = classifier.advance(pending, classifier.claude.choose(terms, pending.section_text))
    except (ClassificationError, anthropic.APIError) as error:
        return Result(Outcome.FAILED, [], f"{type(error).__name__}: {error}", pending.usage)
    storage.save_classification(classifier.classification(pending))
    return Result(Outcome.CLASSIFIED, pending.categories, usage=pending.usage)
