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
from app.application.output_normalizer import STOP_SEQUENCES, normalize


class LlamaCppAdapter:
    """InferencePort implementation backed by a local llama-server process.

    All llama.cpp specifics live here. The application layer only ever
    sees InferencePort and the typed inference errors. Output passes
    through the central output normalizer: control tokens stop at this
    boundary and never reach the application or the frontend.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
        model_path: str | None = None,
        max_tokens: int = 256,
        temperature: float = 0.2,
        opener: Any = None,
        stop_sequences: list[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._model_path = Path(model_path) if model_path else None
        self._opener = opener if opener is not None else urllib.request.urlopen
        self._stop = list(stop_sequences) if stop_sequences is not None else list(STOP_SEQUENCES)

    def _strip_reasoning(self, text: str) -> str:
        """Kept for compatibility; real logic lives in output_normalizer."""
        return normalize(text).text

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
        # Chat-completions endpoint ON PURPOSE (P17 §10/§11): it applies the
        # model's own chat template, which restores correct EOS handling
        # (this GGUF ships </s> as a non-control token) and keeps reasoning
        # inside <think> where the server separates it from the answer.
        # The whole rendered context travels as one user message because
        # ContextBuilder owns assembly; the template must not re-split it.
        status, raw = self._request(
            "POST",
            "/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self._max_tokens,
                "temperature": self._temperature,
                # Single measured anti-ramble knob (P17 §11).
                "repeat_penalty": 1.15,
                # Structured stop information first (§10): the runtime
                # halts generation at control tokens instead of emitting
                # them; the normalizer catches whatever still slips out.
                "stop": self._stop,
                # RUACH answers directly; hidden chains stay out of the
                # latency budget as well as out of the UI.
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        if status == 404:
            raise ModelNotFound(self._model_name)
        if status == 503:
            raise ModelLoadFailed("llama.cpp is still loading the model.")
        if status != 200:
            raise InferenceFailed(f"llama.cpp returned HTTP {status}.")
        try:
            result = json.loads(raw)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise InferenceFailed("llama.cpp returned malformed output.") from error
        return normalize(str(result)).text

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
