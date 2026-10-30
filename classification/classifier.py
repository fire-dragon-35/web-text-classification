from datetime import datetime, timezone
from enum import StrEnum
from typing import NamedTuple

import anthropic

from classification.claude import SYSTEM_PROMPT, USER_MESSAGE, ClassificationError, Claude
from classification.models import Classification
from classification.taxonomy import Taxonomy
from extraction.models import Section, sha256
from storage import Storage

SECTION = "Page title: {title}\nSection heading: {heading}\nRef: {ref}\n\n{text}"
PROMPT_HASH_LENGTH = 8


class Outcome(StrEnum):
    CLASSIFIED = "classified"
    REUSED = "reused"
    FAILED = "failed"


class Result(NamedTuple):
    outcome: Outcome
    categories: list[str]
    detail: str = ""


class Classifier:
    def __init__(self, claude: Claude, taxonomy: Taxonomy, max_depth: int) -> None:
        self._claude = claude
        self.taxonomy = taxonomy
        self.max_depth = max_depth

    @property
    def name(self) -> str:
        prompt = "\n".join((SYSTEM_PROMPT, USER_MESSAGE, SECTION))
        return f"{self._claude.model}#{sha256(prompt.encode())[:PROMPT_HASH_LENGTH]}"

    def classify(self, title: str, section: Section) -> list[str]:
        section_text = SECTION.format(title=title, heading=section.heading, ref=section.ref or "", text=section.text)
        categories: list[str] = []
        terms = self.taxonomy.roots()
        for _ in range(self.max_depth):
            chosen = self._claude.choose(terms, section_text)
            categories += chosen
            terms = [child for code in chosen for child in self.taxonomy.children(code)]
            if not terms:
                break
        return categories


def classify_section(storage: Storage, classifier: Classifier, title: str, section: Section) -> Result:
    name = classifier.name
    stored = storage.latest_classification(section.text_sha256, name, classifier.taxonomy.sha256, classifier.max_depth)
    if stored is not None:
        return Result(Outcome.REUSED, stored)
    try:
        categories = classifier.classify(title, section)
    except (ClassificationError, anthropic.APIError) as error:
        return Result(Outcome.FAILED, [], f"{type(error).__name__}: {error}")
    storage.save_classification(
        Classification(
            text_sha256=section.text_sha256,
            classifier=name,
            taxonomy_sha256=classifier.taxonomy.sha256,
            max_depth=classifier.max_depth,
            categories=categories,
            classified_at=datetime.now(timezone.utc),
        )
    )
    return Result(Outcome.CLASSIFIED, categories)
