from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

MODEL = "BAAI/bge-m3"
MAX_SEQ_LENGTH = 1024
BATCH_SIZE = 8
DEVICE = "cpu"


class Embedder:
    name = f"{MODEL} max_seq_length={MAX_SEQ_LENGTH} batch_size={BATCH_SIZE}"

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._loaded().encode(texts, batch_size=BATCH_SIZE, normalize_embeddings=True, convert_to_numpy=True)

    def _loaded(self) -> "SentenceTransformer":
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(MODEL, device=DEVICE)
            self._model.max_seq_length = MAX_SEQ_LENGTH
        return self._model
