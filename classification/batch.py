import time
from collections.abc import Callable

from classification.classifier import Classifier, Outcome, Result
from classification.claude import ClassificationError
from classification.models import ClassifiedSection, Pending
from db import Storage

POLL_SECONDS = 30


class BatchRun:
    def __init__(self, storage: Storage, classifier: Classifier, progress: Callable[[str], object]) -> None:
        self._storage = storage
        self._classifier = classifier
        self._progress = progress
        self._states = {
            state.text_sha256: state
            for state in storage.pending(classifier.name, classifier.taxonomy.sha256, classifier.max_depth)
        }

    def run(self, items: list[ClassifiedSection]) -> dict[str, Result]:
        new = {
            item.section.text_sha256: self._classifier.pending(item)
            for item in items
            if item.section.text_sha256 not in self._states
        }
        self._storage.update_pending(save=list(new.values()))
        self._states |= new
        results: dict[str, Result] = {}
        while self._states:
            batch_id = next((state.batch_id for state in self._states.values() if state.batch_id), None) or self._submit()
            self._wait(batch_id)
            results |= self._collect(batch_id)
        return results

    def _submit(self) -> str:
        claude = self._classifier.claude
        batch_id = claude.submit(
            {
                text_sha256: claude.params(self._classifier.terms(state), state.section_text)
                for text_sha256, state in self._states.items()
            }
        )
        self._states = {
            text_sha256: state.model_copy(update={"batch_id": batch_id}) for text_sha256, state in self._states.items()
        }
        self._storage.update_pending(save=list(self._states.values()))
        return batch_id

    def _wait(self, batch_id: str) -> None:
        levels = sorted({state.level for state in self._states.values() if state.batch_id == batch_id})
        while True:
            batch = self._classifier.claude.batch(batch_id)
            counts = batch.request_counts
            self._progress(
                f"Batch {batch_id} · level {', '.join(map(str, levels))} · {counts.succeeded} succeeded · "
                f"{counts.errored + counts.expired + counts.canceled} errored · {counts.processing} processing"
            )
            if batch.processing_status == "ended":
                return
            time.sleep(POLL_SECONDS)

    def _collect(self, batch_id: str) -> dict[str, Result]:
        in_batch = {text_sha256: state for text_sha256, state in self._states.items() if state.batch_id == batch_id}
        advanced: list[Pending] = []
        removed: list[Pending] = []
        done: list[Pending] = []
        results: dict[str, Result] = {}
        for response in self._classifier.claude.results(batch_id):
            state = in_batch.pop(response.custom_id, None)
            if state is None:
                continue
            try:
                state = self._classifier.advance(
                    state, self._classifier.claude.parse_result(self._classifier.terms(state), response)
                )
            except ClassificationError as error:
                removed.append(state)
                results[state.text_sha256] = Result(Outcome.FAILED, [], f"{type(error).__name__}: {error}", state.usage)
                continue
            if self._classifier.terms(state):
                advanced.append(state)
            else:
                done.append(state)
                removed.append(state)
                results[state.text_sha256] = Result(Outcome.CLASSIFIED, state.categories, usage=state.usage)
        for state in in_batch.values():
            removed.append(state)
            results[state.text_sha256] = Result(Outcome.FAILED, [], "ClassificationError: no batch result", state.usage)
        self._storage.update_pending(
            save=advanced,
            delete=removed,
            classifications=[self._classifier.classification(state) for state in done],
        )
        for state in removed:
            del self._states[state.text_sha256]
        self._states |= {state.text_sha256: state for state in advanced}
        return results
