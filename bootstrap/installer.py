"""Installation pipeline (platform-independent half of ARCH-009 §29).

Model stage is fully implemented: preflight → resumable verified download →
trust-on-first-use hash recording → state tracking.

Runtime stage builds llama.cpp from source when the toolchain is present.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ruach_setup.download import DownloadError, download, sha256_of_file
from ruach_setup.preflight import check_storage
from ruach_setup.registry import load_models, load_runtimes
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


@dataclass(frozen=True)
class RuntimeInstallResult:
    path: Path
    version_line: str


def _check_toolchain() -> tuple[bool, str]:
    """Verify cmake + a C compiler are available. Returns (ok, detail)."""
    has_cmake = shutil.which("cmake") is not None
    has_cc = shutil.which("clang") is not None or shutil.which("gcc") is not None
    has_make = shutil.which("make") is not None or shutil.which("gmake") is not None
    if not has_cmake:
        return False, "cmake not found — install it first"
    if not has_cc:
        return False, "no C compiler found (need clang or gcc)"
    if not has_make:
        return False, "make not found — install it first"
    return True, "toolchain OK"


def install_runtime(
    *,
    home: Path | None = None,
    source_url: str | None = None,
    jobs: int | None = None,
) -> RuntimeInstallResult:
    """Build llama.cpp from source and install the binary.

    Steps: check toolchain → shallow clone → cmake configure → build →
    copy llama-server to ~/.ruach/runtime/.

    Raises InstallError with a clear message at any failure point.
    """
    home = home or Path.home()
    runtime_dir = home / ".ruach" / "runtime"
    dest = runtime_dir / "llama-server"

    if dest.is_file() and os.access(dest, os.X_OK):
        return RuntimeInstallResult(dest, "already installed")

    ok, detail = _check_toolchain()
    if not ok:
        raise InstallError(f"Cannot build llama.cpp: {detail}")

    runtime_entry = load_runtimes().get("llama_cpp")
    url = source_url or (runtime_entry.source_url if runtime_entry else "https://github.com/ggml-org/llama.cpp")

    build_dir = Path(tempfile.mkdtemp(prefix="ruach-runtime-"))
    try:
        # 1) Clone
        clone_cmd = ["git", "clone", "--depth=1", url, str(build_dir / "llama.cpp")]
        try:
            result = subprocess.run(
                clone_cmd, capture_output=True, text=True, timeout=120, check=False
            )
        except FileNotFoundError:
            raise InstallError("git not found — install git first")
        except subprocess.TimeoutExpired:
            raise InstallError("git clone timed out (120s) — check network connection")
        if result.returncode != 0:
            raise InstallError(f"git clone failed: {result.stderr.strip()[:200]}")

        source_dir = build_dir / "llama.cpp"
        build_output = build_dir / "build"

        # 2) CMake configure
        cmake_cmd = [
            "cmake",
            "-S", str(source_dir),
            "-B", str(build_output),
            "-DCMAKE_BUILD_TYPE=Release",
        ]
        try:
            result = subprocess.run(
                cmake_cmd, capture_output=True, text=True, timeout=120, check=False
            )
        except subprocess.TimeoutExpired:
            raise InstallError("cmake configure timed out (120s)")
        if result.returncode != 0:
            raise InstallError(f"cmake configure failed: {result.stderr.strip()[:300]}")

        # 3) Build llama-server
        nproc = jobs or max(1, (os.cpu_count() or 2) - 1)
        build_cmd = [
            "cmake",
            "--build", str(build_output),
            "--config", "Release",
            "--target", "llama-server",
            "-j", str(nproc),
        ]
        try:
            result = subprocess.run(
                build_cmd, capture_output=True, text=True, timeout=600, check=False
            )
        except subprocess.TimeoutExpired:
            raise InstallError("build timed out (600s) — try with fewer parallel jobs")
        if result.returncode != 0:
            raise InstallError(f"build failed: {result.stderr.strip()[:300]}")

        # 4) Find and install the binary
        candidates = list(build_output.rglob("llama-server"))
        if not candidates:
            # Some cmake configurations put it in bin/
            candidates = list(build_output.rglob("bin/llama-server"))
        if not candidates:
            raise InstallError(
                "build completed but llama-server binary not found in build output"
            )
        built_binary = candidates[0]

        runtime_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(built_binary), str(dest))
        dest.chmod(0o755)

        # 5) Get version info
        version_line = ""
        try:
            ver = subprocess.run(
                [str(dest), "--version"],
                capture_output=True, text=True, timeout=10, check=False
            )
            output = ((ver.stdout or "") + (ver.stderr or "")).strip()
            version_line = output.splitlines()[0][:80] if output else "built successfully"
        except Exception:  # noqa: BLE001
            version_line = "built successfully"

        return RuntimeInstallResult(dest, version_line)

    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


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
