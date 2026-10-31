import json
from collections.abc import Iterator

import anthropic
from anthropic.types import Message
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages import MessageBatch, MessageBatchIndividualResponse

from classification.models import Choice, Term, Usage

TIMEOUT_SECONDS = 60
MAX_RETRIES = 4
MAX_TOKENS = 1024
FAILED_STOP_REASONS = ("refusal", "max_tokens")
SYSTEM_PROMPT = (
    "You classify text sections against a taxonomy. Choose every category the section is actually about. "
    "Choose none if no category fits. Answer only with codes from the list."
)
TERM_LINE = "{code} {name}: {definition}"


class ClassificationError(Exception):
    pass


def schema(codes: list[str]) -> dict[str, object]:
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

    def params(self, terms: list[Term], section_text: str) -> MessageCreateParamsNonStreaming:
        candidates = "\n".join(TERM_LINE.format(code=term.code, name=term.name, definition=term.definition) for term in terms)
        return {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": candidates, "cache_control": {"type": "ephemeral"}},
                        {"type": "text", "text": section_text},
                    ],
                }
            ],
            "output_config": {"format": {"type": "json_schema", "schema": schema([term.code for term in terms])}},
        }

    def choose(self, terms: list[Term], section_text: str) -> Choice:
        return self.parse(terms, self._client.messages.create(**self.params(terms, section_text)))

    def parse(self, terms: list[Term], message: Message) -> Choice:
        if message.stop_reason in FAILED_STOP_REASONS:
            raise ClassificationError(f"stop reason: {message.stop_reason}")
        codes = {term.code.casefold(): term.code for term in terms}
        text = next(block.text for block in message.content if block.type == "text")
        chosen = json.loads(text)["categories"]
        unknown = [code for code in chosen if code.casefold() not in codes]
        if unknown:
            raise ClassificationError(f"unknown codes: {', '.join(unknown)}")
        return Choice(codes=list(dict.fromkeys(codes[code.casefold()] for code in chosen)), usage=Usage.of(message.usage))

    def parse_result(self, terms: list[Term], response: MessageBatchIndividualResponse) -> Choice:
        if response.result.type == "succeeded":
            return self.parse(terms, response.result.message)
        if response.result.type == "errored":
            raise ClassificationError(f"batch request errored: {response.result.error.error.message}")
        raise ClassificationError(f"batch request {response.result.type}")

    def submit(self, requests: dict[str, MessageCreateParamsNonStreaming]) -> str:
        batch = self._client.messages.batches.create(
            requests=[{"custom_id": custom_id, "params": params} for custom_id, params in requests.items()]
        )
        return batch.id

    def batch(self, batch_id: str) -> MessageBatch:
        return self._client.messages.batches.retrieve(batch_id)

    def results(self, batch_id: str) -> Iterator[MessageBatchIndividualResponse]:
        return iter(self._client.messages.batches.results(batch_id))
