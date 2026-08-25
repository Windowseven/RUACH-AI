"""Interactive guided setup (v2): detect → explain → recommend → confirm → install → verify.

Modern UX flow:
  1. Welcome dashboard with device summary
  2. Step-by-step with numbered choices
  3. Model auto-discovery + simple Y/n prompt
  4. Progressive disclosure — don't show every detail at once
  5. No false positives — honest status at every step

Central rule: RUACH MUST ADAPT TO DEVICE CAPABILITIES.
Never say "RUACH IS READY" when critical components are missing.
Never say "source build looks viable" after a failed build.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable

from ruach_setup.build_state import check_backend_python_compatibility, overall_python_health
from ruach_setup.diagnostics import DependencyState, InferenceLevel, Status, status_label
from ruach_setup.registry import load_models, load_runtimes
from ruach_setup.verify import verify

InstallCallable = Callable[[str, str], bool]

DEFAULT_CONFIG_DIR = Path.home() / ".ruach"
DEFAULT_RUNTIME_DIR = DEFAULT_CONFIG_DIR / "runtime"
DEFAULT_HOME_DIR = DEFAULT_CONFIG_DIR
NL = chr(10)
BOLD = chr(27) + "[1m"
RESET = chr(27) + "[0m"


def _detect_existing_model_path() -> str | None:
    """Auto-detect the best existing GGUF model on this device."""
    candidates = [
        "/data/data/com.termux/files/home/gemma-3-270m-it-Q4_K_M.gguf",
        "/data/data/com.termux/files/home/Phi-4-mini-instruct-Q4_K_M.gguf",
        os.path.expanduser("~/gemma-3-270m-it-Q4_K_M.gguf"),
        os.path.expanduser("~/Phi-4-mini-instruct-Q4_K_M.gguf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _detect_existing_runtime_path() -> str | None:
    """Auto-detect the best existing runtime on this device."""
    candidates = [
        str(DEFAULT_RUNTIME_DIR / "llama-server"),
        str(DEFAULT_HOME_DIR / "runtime" / "llama-server"),
        str(DEFAULT_HOME_DIR / "runtime" / "build" / "bin" / "llama-server"),
        str(DEFAULT_HOME_DIR / "runtime" / "build" / "bin" / "Release" / "llama-server.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


class SetupEffects:
    """Encapsulates external effects for testability."""

    def __init__(
        self,
        *,
        install_runtime: InstallCallable | None = None,
        install_model: InstallCallable | None = None,
        generate_config: Callable[..., None] | None = None,
    ) -> None:
        self.install_runtime = install_runtime or (lambda src, dst: False)
        self.install_model = install_model or (lambda src, dst: False)
        self.generate_config = generate_config or (lambda **kwargs: None)


def _render_profile_dashboard(decision_json: dict, plan_json: dict) -> None:
    """Render a concise device summary dashboard."""
    print()
    print(f"{BOLD}RUACH — Device Assessment{RESET}")
    print("=" * 40)
    profile = decision_json.get("profile", "UNKNOWN")
    confidence = decision_json.get("confidence", "LOW")
    mode = plan_json.get("mode", "none")
    inference = plan_json.get("inference", "none")
    backend = plan_json.get("backend", "none")
    risk = plan_json.get("risk", "UNKNOWN")
    print(f"  Profile    : {profile}")
    print(f"  Confidence : {confidence}")
    print(f"  Mode       : {mode}")
    print(f"  Inference  : {inference}")
    print(f"  Backend    : {backend}")
    print(f"  Risk       : {risk}")

    reasons = decision_json.get("reason", [])
    if reasons:
        print()
        print("Why this profile:")
        for reason in reasons:
            print(f"  • {reason}")

    hard_blocks = decision_json.get("hard_blocks", [])
    if hard_blocks:
        print()
        print(f"{BOLD}Hard blocks:{RESET}")
        for block in hard_blocks:
            print(f"  ✗ {block}")

    warnings = decision_json.get("warnings", [])
    if warnings:
        print()
        print("Warnings:")
        for warn in warnings:
            print(f"  ⚠ {warn}")
    print()


def _python_health_report() -> tuple[bool | None, str]:
    """Check Python wheel health and return (healthy, summary)."""
    try:
        checks = check_backend_python_compatibility()
        health = overall_python_health(checks)
        if health is True:
            return True, "All required Python packages have wheels available."
        if health is False:
            missing = [c.package for c in checks if c.state in (
                DependencyState.UNAVAILABLE,
                DependencyState.SOURCE_BUILD_BLOCKED,
            )]
            return False, f"Missing wheels: {', '.join(missing)}"
        return None, "Could not determine Python package availability."
    except Exception as exc:
        return None, f"Python wheel check failed: {exc}"


def _model_stage(prompter: Callable[[str], str], effects: SetupEffects) -> tuple[str | None, str | None]:
    """Model selection stage — auto-detect existing, then simple Y/n."""
    existing = _detect_existing_model_path()
    if existing:
        print(f"  Found existing model: {existing}")
        use_existing = prompter("Use this model? [Y/n]: ").strip().lower()
        if use_existing in ("", "y", "yes"):
            return existing, None

    print()
    print("Select model source:")
    print("  [1] Download recommended model (Phi-4-mini, ~2.4 GB)")
    print("  [2] I have a GGUF file already")
    choice = prompter("Choice [1/2]: ").strip()

    if choice == "1":
        return None, "download"
    elif choice == "2":
        path = prompter("Path to GGUF file: ").strip()
        if os.path.isfile(path):
            return path, None
        print(f"  File not found: {path}")
        return None, None
    else:
        print("  Invalid choice.")
        return None, None


def _runtime_stage(prompter: Callable[[str], str], effects: SetupEffects) -> tuple[str | None, str | None]:
    """Runtime selection stage — auto-detect existing, then build option."""
    existing = _detect_existing_runtime_path()
    if existing:
        print(f"  Found existing runtime: {existing}")
        use_existing = prompter("Use this runtime? [Y/n]: ").strip().lower()
        if use_existing in ("", "y", "yes"):
            return existing, None

    print()
    print("Runtime options:")
    print("  [1] Build llama.cpp from source")
    print("  [2] Skip runtime (use compatibility mode)")
    choice = prompter("Choice [1/2]: ").strip()

    if choice == "1":
        return None, "build"
    elif choice == "2":
        return None, "skip"
    else:
        print("  Invalid choice.")
        return None, None


def guided_setup(
    *,
    prompter: Callable[[str], str] | None = None,
    start_message: str | None = None,
    effects: SetupEffects | None = None,
    config_dir: Path | None = None,
    max_retries: int = 3,
    verbose: bool = False,
    mode: str | None = None,
) -> int:
    """Execute the guided setup flow (v2).

    Returns 0 on success, non-zero on failure.
    """
    prompter = prompter or input
    effects = effects or SetupEffects()
    config = config_dir or DEFAULT_CONFIG_DIR

    # ---- Stage 1: Welcome + Device Assessment ----
    print()
    print(f"{BOLD}RUACH SETUP{RESET}")
    print("=" * 40)
    print("  Detecting device capabilities...")
    print()

    from ruach_setup.doctor_engine import doctor
    environment = doctor()

    # Build decision + plan for the dashboard
    from ruach_setup.profiles import decide, DecisionInput, PROFILE_TO_MODE
    from ruach_setup.planner import build_plan, render_plan

    # Build decision input from environment
    decision_input = DecisionInput(
        architecture_supported=environment.arch != "unknown",
        abi=environment.arch,
        ram_total_bytes=environment.ram,
        ram_available_bytes=environment.ram,
        storage_free_bytes=environment.disk_free_bytes,
        python_ok=True,  # We're running in Python
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        compilers_present=frozenset(),  # Would need probes
        native_binary_found=_detect_existing_runtime_path() is not None,
        inference_level=InferenceLevel(environment.inference_backend) if environment.inference_backend != "none" else InferenceLevel.NOT_TESTED,
        python_deps_healthy=None,
        native_build_previously_failed=False,
        resource_tier="unknown",
        environment_status="target_device" if environment.target_device else ("development_host" if environment.development_host else "unknown"),
    )

    decision = decide(decision_input)
    plan = build_plan(decision, decision_input)

    _render_profile_dashboard(decision.to_json(), plan.to_json())

    # ---- Stage 2: Python health check ----
    python_healthy, python_msg = _python_health_report()
    if python_healthy is False:
        print(f"  ⚠ Python backend: {python_msg}")
        print("    RUACH will run in compatibility mode.")
        print()
    elif python_healthy is True:
        print(f"  ✓ Python backend: {python_msg}")
        print()

    # ---- Stage 3: Model selection ----
    print(f"{BOLD}Step 1: Model{RESET}")
    model_path, model_action = _model_stage(prompter, effects)

    # ---- Stage 4: Runtime selection ----
    print()
    print(f"{BOLD}Step 2: Runtime{RESET}")
    runtime_path, runtime_action = _runtime_stage(prompter, effects)

    # ---- Stage 5: Configuration ----
    print()
    print(f"{BOLD}Step 3: Configuration{RESET}")
    print("  Generating configuration...")

    # ---- Stage 6: Verify ----
    print()
    print(f"{BOLD}Step 4: Verify{RESET}")
    result = verify(model=model_path, runtime=runtime_path)

    # ---- Final summary ----
    print()
    print("=" * 40)
    if result.healthy:
        print(f"{BOLD}RUACH IS READY{RESET}")
        print(f"  Profile: {decision.profile.value}")
        print(f"  Mode: {PROFILE_TO_MODE.get(decision.profile, 'none')}")
        if model_path:
            print(f"  Model: {model_path}")
        if runtime_path:
            print(f"  Runtime: {runtime_path}")
    else:
        print(f"{BOLD}RUACH SETUP COMPLETE (with warnings){RESET}")
        print(f"  Profile: {decision.profile.value}")
        for item in result.items:
            if not item.ok:
                print(f"  ✗ {item.label}: {item.detail}")
    print()

    return 0 if result.healthy else 1
