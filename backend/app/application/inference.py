from typing import Literal, Protocol


class InferenceRuntimeUnavailable(Exception):
    """The local inference runtime could not be reached."""


class ModelNotFound(Exception):
    """The configured model file or identifier does not exist."""


class ModelLoadFailed(Exception):
    """The runtime failed while loading the model."""


class InferenceTimeout(Exception):
    """The inference request exceeded the allowed time."""


class InferenceFailed(Exception):
    """The runtime produced no valid output for the request."""


InferenceHealth = Literal[
    "ready",
    "loading",
    "runtime_unavailable",
    "model_not_found",
    "model_load_failed",
    "error",
]


class InferencePort(Protocol):
    def complete(self, prompt: str) -> str: ...

    def health(self) -> InferenceHealth: ...
