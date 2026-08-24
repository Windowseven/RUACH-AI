"""Installation pipeline (platform-independent half of ARCH-009 §29).

Model stage is fully implemented: preflight → resumable verified download →
trust-on-first-use hash recording → state tracking.

Runtime stage (llama.cpp build) is deliberately BLOCKED until the Termux
spike provides target-device evidence (docs/11). It fails loudly instead
of pretending.
"""

from dataclasses import dataclass
from pathlib import Path

from ruach_setup.download import DownloadError, download, sha256_of_file
from ruach_setup.preflight import check_storage
from ruach_setup.registry import load_models
from ruach_setup.state import STAGES, SetupState, save_state

_STAGE_INDEX = {name: index for index, name in enumerate(STAGES)}


class InstallError(Exception):
    """Installation cannot proceed."""


def _mark_forward(state: SetupState, stage: str, **fields: str | None) -> None:
    """Advance the pipeline without ever moving backwards on resume."""
    if _STAGE_INDEX.get(state.stage, -1) < _STAGE_INDEX[stage]:
        state.mark(stage, **fields)
        return
    for key, value in fields.items():
        setattr(state, key, value)


@dataclass(frozen=True)
class ModelInstallResult:
    path: Path
    sha256: str
    resumed: bool
    already_present: bool


def install_runtime() -> None:
    raise InstallError(
        "Runtime installation is BLOCKED: llama.cpp acquisition on "
        "Android/Termux awaits spike validation (docs/11_TERMUX_SPIKE.md)."
    )


def model_dest_path(models_root: Path, model_id: str, registry_path: Path | None = None) -> Path:
    entry = load_models(registry_path).get(model_id)
    if entry is None:
        raise InstallError(f"Unknown model id: {model_id}")
    file_name = Path(entry.file_name).name
    return Path(models_root) / model_id / file_name


def _record_sha256(registry_path: Path, model_id: str, sha256: str) -> bool:
    """Write a measured hash back into the model registry block (TOFU).

    Returns True when the registry was updated. Only fills EMPTY fields —
    an existing recorded hash is never silently overwritten.
    """
    text = registry_path.read_text(encoding="utf-8")
    marker = f'[models."{model_id}"]'
    start = text.find(marker)
    if start == -1:
        return False
    block_end = text.find("\n[models.", start + 1)
    block = text[start:] if block_end == -1 else text[start:block_end]
    if 'sha256 = ""' not in block:
        return False
    updated_block = block.replace('sha256 = ""', f'sha256 = "{sha256}"', 1)
    tail = text[block_end:] if block_end != -1 else ""
    registry_path.write_text(text[:start] + updated_block + tail, encoding="utf-8")
    return True


def install_model(
    model_id: str,
    models_root: Path,
    state: SetupState,
    state_path: Path,
    source_url_override: str | None = None,
    registry_path: Path | None = None,
    progress=None,
) -> ModelInstallResult:
    entry = load_models(registry_path).get(model_id)
    if entry is None:
        raise InstallError(f"Unknown model id: {model_id}")

    dest = model_dest_path(models_root, model_id, registry_path)

    if dest.is_file():
        expected = entry.sha256 or None
        actual = sha256_of_file(dest)
        if expected is None:
            return ModelInstallResult(dest, actual, resumed=False, already_present=True)
        if actual == expected.lower():
            return ModelInstallResult(dest, actual, resumed=False, already_present=True)
        raise InstallError(
            f"Existing file at {dest} does not match the registry checksum; "
            "delete it and rerun to redownload."
        )

    check = check_storage(dest.parent, entry.download_size_bytes)
    if not check.ok:
        raise InstallError(
            f"INSUFFICIENT_STORAGE: need ~{check.required_bytes // (1024**2)} MB, "
            f"have {check.available_bytes // (1024**2)} MB free."
        )

    url = source_url_override or entry.source_url
    try:
        result = download(
            url,
            dest,
            expected_sha256=entry.sha256 or None,
            timeout_seconds=180.0,
            progress=progress,
        )
    except DownloadError as error:
        raise InstallError(str(error)) from error

    if not entry.sha256:
        active_registry = (
            registry_path
            or Path(__file__).resolve().parent.parent / "ruach_setup" / "data" / "models.toml"
        )
        _record_sha256(active_registry, model_id, result.sha256)

    _mark_forward(state, "environment_ready")
    _mark_forward(
        state, "model_installed", model_id=model_id, model_sha256=result.sha256
    )
    save_state(state, state_path)
    return ModelInstallResult(dest, result.sha256, result.resumed, False)


def resolve_model_id(requested: str | None, registry_path: Path | None = None):
    models = load_models(registry_path)
    if requested and requested != "auto":
        return models.get(requested)
    from ruach_setup.capability import analyze, build_profile
    from ruach_setup.device import SystemEnvironmentReader
    from ruach_setup.recommend import recommend
    from ruach_setup.registry import load_runtimes

    assessment = analyze(build_profile(SystemEnvironmentReader().read()))
    rec = recommend(
        assessment, load_runtimes(), models,
        storage_free_bytes=assessment.profile.storage_available_bytes,
    )
    return models.get(rec.model_id) if rec.model_id else None
