"""Typed loaders for the RUACH registries (TOML data files).

Registries are the single source of runtime/model compatibility metadata.
Nothing outside this module parses the TOML files.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

ArchStatus = str  # "supported" | "experimental" | "unknown"


@dataclass(frozen=True)
class RuntimeEntry:
    id: str
    name: str
    interface: str
    server_binary: str
    status: str
    acquisition: str
    supported_architectures: dict[str, ArchStatus]
    pin_policy: str
    source_url: str
    notes: str


@dataclass(frozen=True)
class ModelEntry:
    id: str
    family: str
    parameters: str
    format: str
    quantization: str
    file_name: str
    download_size_bytes: int
    estimated_memory_bytes: int
    min_recommended_memory_bytes: int
    max_context_tokens: int
    quality_tier: str
    speed_expectation: str
    status: str
    source_url: str
    sha256: str


def load_runtimes(path: Path | None = None) -> dict[str, RuntimeEntry]:
    with open(path or DATA_DIR / "runtimes.toml", "rb") as handle:
        raw = tomllib.load(handle)
    entries: dict[str, RuntimeEntry] = {}
    for runtime_id, data in raw["runtimes"].items():
        entries[runtime_id] = RuntimeEntry(
            id=runtime_id,
            name=data["name"],
            interface=data["interface"],
            server_binary=data["server_binary"],
            status=data["status"],
            acquisition=data["acquisition"],
            supported_architectures=dict(data["supported_architectures"]),
            pin_policy=data["pin_policy"],
            source_url=data["source_url"],
            notes=data.get("notes", ""),
        )
    return entries


def load_models(path: Path | None = None) -> dict[str, ModelEntry]:
    """Returns models in registry declaration order (defines preference)."""
    with open(path or DATA_DIR / "models.toml", "rb") as handle:
        raw = tomllib.load(handle)
    entries: dict[str, ModelEntry] = {}
    for model_id, data in raw["models"].items():
        entries[model_id] = ModelEntry(
            id=model_id,
            family=data["family"],
            parameters=data["parameters"],
            format=data["format"],
            quantization=data["quantization"],
            file_name=data["file_name"],
            download_size_bytes=int(data["download_size_bytes"]),
            estimated_memory_bytes=int(data["estimated_memory_bytes"]),
            min_recommended_memory_bytes=int(data["min_recommended_memory_bytes"]),
            max_context_tokens=int(data["max_context_tokens"]),
            quality_tier=data["quality_tier"],
            speed_expectation=data["speed_expectation"],
            status=data["status"],
            source_url=data["source_url"],
            sha256=data.get("sha256", ""),
        )
    return entries
