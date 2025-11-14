"""Embedding client with pluggable providers and graceful fallbacks."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests
from loguru import logger

try:  # Optional dependency for numerical ops
    import numpy as np
except Exception:  # pragma: no cover - fallback if numpy unavailable
    np = None  # type: ignore


@dataclass
class EmbeddingConfig:
    provider: str = "hash"
    model: str = "text-embedding-v1"
    dimension: int = 768
    batch_size: int = 16
    timeout: int = 45
    base_url: Optional[str] = None


class EmbeddingClient:
    """Lightweight embedding client supporting DashScope/OpenAI style APIs.

    Falls back to deterministic hash-based embeddings when remote providers
    are unavailable to keep the pipeline functional in offline environments.
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None, *, api_key: Optional[str] = None) -> None:
        self.config = config or EmbeddingConfig()
        self.provider = (self.config.provider or "hash").lower()
        self.model = self.config.model
        self.dimension = max(32, int(self.config.dimension or 768))
        self.batch_size = max(1, int(self.config.batch_size or 16))
        self.timeout = int(self.config.timeout or 45)
        self.base_url = self.config.base_url

        # Resolve API key from env/config when needed
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY") or os.getenv("OPENAI_API_KEY")

        if self.provider in {"dashscope", "openai"} and not self.api_key:
            logger.warning(
                "Embedding provider '%s' requires API key but none was found. Falling back to hash embeddings.",
                self.provider,
            )
            self.provider = "hash"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        """Embed a collection of texts using configured provider.

        Returns a list of float vectors (unit-normalized when possible).
        """

        texts_list = [t or "" for t in texts]
        if not texts_list:
            return []

        if self.provider == "dashscope":
            try:
                return self._embed_dashscope(texts_list)
            except Exception as exc:  # pragma: no cover - network fallback
                logger.error("DashScope embedding call failed: %s", exc)
                logger.warning("Falling back to hash embeddings for this batch.")
                return [self._hash_embed(text) for text in texts_list]

        if self.provider == "openai":
            try:
                return self._embed_openai(texts_list)
            except Exception as exc:  # pragma: no cover - network fallback
                logger.error("OpenAI embedding call failed: %s", exc)
                logger.warning("Falling back to hash embeddings for this batch.")
                return [self._hash_embed(text) for text in texts_list]

        # Default deterministic hash embedding (offline friendly)
        return [self._hash_embed(text) for text in texts_list]

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------
    def _embed_dashscope(self, texts: List[str]) -> List[List[float]]:
        """Call DashScope compatible embedding endpoint (OpenAI style)."""

        base_url = self.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        url = base_url.rstrip("/") + "/embeddings"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {"model": self.model, "input": texts}
        response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        embeddings = []
        for item in data.get("data", []):
            vec = item.get("embedding") or []
            embeddings.append(self._normalize(vec))

        if not embeddings:
            raise ValueError("DashScope embedding response contained no vectors")

        return embeddings

    def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """Call OpenAI embeddings API (used for Azure/OpenAI compatible providers)."""

        base_url = self.base_url or "https://api.openai.com/v1"
        url = base_url.rstrip("/") + "/embeddings"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {"model": self.model, "input": texts}
        response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        embeddings = []
        for item in data.get("data", []):
            vec = item.get("embedding") or []
            embeddings.append(self._normalize(vec))

        if not embeddings:
            raise ValueError("OpenAI embedding response contained no vectors")

        return embeddings

    # ------------------------------------------------------------------
    # Fallback implementation
    # ------------------------------------------------------------------
    def _hash_embed(self, text: str) -> List[float]:
        """Generate deterministic hash-based embedding as an offline fallback."""

        tokens = text.split()
        dim = self.dimension
        vector = [0.0] * dim

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(0, len(digest), 4):
                idx = (digest[i] << 24 | digest[i + 1] << 16 | digest[i + 2] << 8 | digest[i + 3]) % dim
                vector[idx] += 1.0

        return self._normalize(vector)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _normalize(self, vector: Iterable[float]) -> List[float]:
        """Return L2-normalized vector."""

        if np is not None:  # pragma: no branch - depends on numpy availability
            np_vec = np.asarray(list(vector), dtype=float)
            norm = np.linalg.norm(np_vec)
            if norm == 0:
                return np_vec.tolist()
            return (np_vec / norm).tolist()

        vec_list = [float(x) for x in vector]
        norm = sum(x * x for x in vec_list) ** 0.5
        if norm == 0:
            return vec_list
        return [x / norm for x in vec_list]

    # ------------------------------------------------------------------
    # Serialization helpers (used by vector store)
    # ------------------------------------------------------------------
    def serialize_vector(self, vector: Iterable[float]) -> bytes:
        """Serialize a vector to bytes (JSON) for storage when NumPy is unavailable."""

        if np is not None:  # Use binary representation for efficiency
            arr = np.asarray(list(vector), dtype="float32")
            return arr.tobytes()
        return json.dumps(list(vector)).encode("utf-8")

    def deserialize_vector(self, payload: bytes) -> List[float]:
        """Deserialize bytes payload back into a vector."""

        if np is not None:  # Use NumPy for binary payloads
            arr = np.frombuffer(payload, dtype="float32")
            return arr.astype(float).tolist()
        return [float(x) for x in json.loads(payload.decode("utf-8"))]











