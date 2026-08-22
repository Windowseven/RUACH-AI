import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.application.inference import (
    InferenceFailed,
    InferenceHealth,
    InferenceRuntimeUnavailable,
    InferenceTimeout,
    ModelLoadFailed,
    ModelNotFound,
)


class LlamaCppAdapter:
    """InferencePort implementation backed by a local llama-server process.

    All llama.cpp specifics live here. The application layer only ever
    sees InferencePort and the typed inference errors.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
        model_path: str | None = None,
        opener: Any = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout = timeout_seconds
        self._model_path = Path(model_path) if model_path else None
        self._opener = opener if opener is not None else urllib.request.urlopen

    def _ensure_model_file(self) -> None:
        if self._model_path is not None and not self._model_path.is_file():
            raise ModelNotFound(f"Model file not found: {self._model_path}")

    def _request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> tuple[int, bytes]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self._base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", None)
            if isinstance(reason, TimeoutError):
                raise InferenceTimeout("Inference request timed out.") from error
            raise InferenceRuntimeUnavailable("llama.cpp runtime is not reachable.") from error
        except TimeoutError as error:
            raise InferenceTimeout("Inference request timed out.") from error

    def complete(self, prompt: str) -> str:
        self._ensure_model_file()
        status, raw = self._request("POST", "/completion", {"prompt": prompt})
        if status == 404:
            raise ModelNotFound(self._model_name)
        if status == 503:
            raise ModelLoadFailed("llama.cpp is still loading the model.")
        if status != 200:
            raise InferenceFailed(f"llama.cpp returned HTTP {status}.")
        try:
            result = json.loads(raw)["content"]
        except (ValueError, KeyError) as error:
            raise InferenceFailed("llama.cpp returned malformed output.") from error
        return str(result)

    def health(self) -> InferenceHealth:
        try:
            self._ensure_model_file()
        except ModelNotFound:
            return "model_not_found"
        status, _raw = self._request("GET", "/health")
        if status == 200:
            return "ready"
        if status == 503:
            return "loading"
        return "error"
