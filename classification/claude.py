import json

import anthropic

from classification.taxonomy import Term

TIMEOUT_SECONDS = 60
MAX_RETRIES = 4
MAX_TOKENS = 1024
FAILED_STOP_REASONS = ("refusal", "max_tokens")
SYSTEM_PROMPT = (
    "You classify text sections against a taxonomy. Choose every category the section is actually about. "
    "Choose none if no category fits. Answer only with codes from the list."
)
USER_MESSAGE = "{terms}\n\n{section}"


class ClassificationError(Exception):
    pass


def _schema(codes: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"categories": {"type": "array", "items": {"type": "string", "enum": codes}}},
        "required": ["categories"],
        "additionalProperties": False,
    }


class Claude:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
        self.model = model

    def choose(self, terms: list[Term], section_text: str) -> list[str]:
        codes = {term.code.casefold(): term.code for term in terms}
        candidates = "\n".join(f"{term.code} {term.name}: {term.definition}" for term in terms)
        response = self._client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": USER_MESSAGE.format(terms=candidates, section=section_text)}],
            output_config={"format": {"type": "json_schema", "schema": _schema(list(codes.values()))}},
        )
        if response.stop_reason in FAILED_STOP_REASONS:
            raise ClassificationError(f"stop reason: {response.stop_reason}")
        text = next(block.text for block in response.content if block.type == "text")
        chosen = json.loads(text)["categories"]
        unknown = [code for code in chosen if code.casefold() not in codes]
        if unknown:
            raise ClassificationError(f"unknown codes: {', '.join(unknown)}")
        return list(dict.fromkeys(codes[code.casefold()] for code in chosen))
