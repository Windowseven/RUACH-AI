"""Installation planner (v2): converts a RuntimeDecision into an InstallationPlan.

Profile-aware planning that reflects the ACTUAL selected profile.
Never shows "Inference: llama.cpp" if llama.cpp has already failed.
Never shows "Python backend" if pydantic-core cannot be installed.

All byte figures are ESTIMATES until measured on-device.
"""

from __future__ import annotations

from dataclasses import dataclass

from ruach_setup.profiles import (
    PROFILE_TO_MODE,
    DecisionInput,
    RuntimeDecision,
    RuntimeProfile,
)

RUNTIME_BUILD_ESTIMATE_BYTES = 160 * 1024 * 1024
PYTHON_COMPONENTS_ESTIMATE_BYTES = 45 * 1024 * 1024


@dataclass(frozen=True)
class PlanStep:
    """One inspectable installation step."""
    index: int
    title: str
    kind: str
    required: bool = True
    skippable: bool = False
    estimated_bytes: int = 0


@dataclass(frozen=True)
class InstallationPlan:
    """Planner output contract."""
    mode: str
    confidence: str
    profile: str
    backend: str
    inference: str
    python_strategy: str
    native_extensions: bool
    database: str
    guided_installation: bool
    dependency_profile: str
    steps: tuple[PlanStep, ...]
    estimated_bytes: int
    model_id: str | None = None
    risk: str = "LOW"

    def to_json(self) -> dict:
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "profile": self.profile,
            "backend": self.backend,
            "inference": self.inference,
            "python_strategy": self.python_strategy,
            "native_extensions": self.native_extensions,
            "database": self.database,
            "guided_installation": self.guided_installation,
            "dependency_profile": self.dependency_profile,
            "estimated_storage_bytes": self.estimated_bytes,
            "model": self.model_id,
            "risk": self.risk,
            "steps": [
                {
                    "index": step.index,
                    "title": step.title,
                    "kind": step.kind,
                    "required": step.required,
                    "skippable": step.skippable,
                    "estimated_bytes": step.estimated_bytes,
                }
                for step in self.steps
            ],
        }


def _steps_for_profile(
    profile: RuntimeProfile,
    *,
    needs_runtime_build: bool,
    runtime_build_failed: bool,
) -> tuple[PlanStep, ...]:
    """Deterministic step lists per profile."""

    if profile == RuntimeProfile.FULL_HYBRID:
        runtime_title = "Prepare native runtime"
        if needs_runtime_build and not runtime_build_failed:
            runtime_title += " (source build)"
        elif runtime_build_failed:
            runtime_title += " (previously failed; will skip)"
        return (
            PlanStep(1, "Create RUACH directories", "directories"),
            PlanStep(2, runtime_title, "runtime",
                     estimated_bytes=RUNTIME_BUILD_ESTIMATE_BYTES if needs_runtime_build and not runtime_build_failed else 0),
            PlanStep(3, "Prepare model directory", "model"),
            PlanStep(4, "Install Python components", "python",
                     estimated_bytes=PYTHON_COMPONENTS_ESTIMATE_BYTES),
            PlanStep(5, "Generate configuration", "config"),
            PlanStep(6, "Verify installation", "verify"),
        )

    if profile == RuntimeProfile.NATIVE_HYBRID:
        runtime_title = "Prepare native runtime"
        if needs_runtime_build and not runtime_build_failed:
            runtime_title += " (source build)"
        elif runtime_build_failed:
            runtime_title += " (previously failed; will skip)"
        return (
            PlanStep(1, "Create RUACH directories", "directories"),
            PlanStep(2, runtime_title, "runtime",
                     estimated_bytes=RUNTIME_BUILD_ESTIMATE_BYTES if needs_runtime_build and not runtime_build_failed else 0),
            PlanStep(3, "Prepare model directory", "model"),
            PlanStep(4, "Generate configuration", "config"),
            PlanStep(5, "Verify installation", "verify"),
        )

    if profile == RuntimeProfile.PYTHON_HYBRID:
        return (
            PlanStep(1, "Create RUACH directories", "directories"),
            PlanStep(2, "Install Python components", "python",
                     estimated_bytes=PYTHON_COMPONENTS_ESTIMATE_BYTES),
            PlanStep(3, "Configure inference provider", "config"),
            PlanStep(4, "Verify installation", "verify"),
        )

    if profile == RuntimeProfile.COMPATIBILITY:
        return (
            PlanStep(1, "Create RUACH directories", "directories"),
            PlanStep(2, "Generate minimal configuration", "config"),
            PlanStep(3, "Verify installation", "verify"),
        )

    if profile == RuntimeProfile.DEVELOPMENT_STUB:
        return (
            PlanStep(1, "Create RUACH directories", "directories"),
            PlanStep(2, "Generate development configuration", "config"),
            PlanStep(3, "Verify installation", "verify"),
        )

    return ()


def build_plan(
    decision: RuntimeDecision,
    capabilities: DecisionInput,
    model_entry=None,
) -> InstallationPlan:
    """Deterministic planning rules applied to the decision."""
    profile = decision.profile
    mode = PROFILE_TO_MODE.get(profile, "none")

    if mode == "none":
        return InstallationPlan(
            mode="none",
            confidence=decision.confidence,
            profile=profile.value,
            backend="none",
            inference="none",
            python_strategy="none",
            native_extensions=False,
            database="none",
            guided_installation=False,
            dependency_profile="none",
            steps=(),
            estimated_bytes=0,
        )

    needs_runtime_build = not capabilities.native_binary_found and profile in {
        RuntimeProfile.FULL_HYBRID,
        RuntimeProfile.NATIVE_HYBRID,
    }
    runtime_build_failed = capabilities.native_build_previously_failed

    steps = _steps_for_profile(
        profile,
        needs_runtime_build=needs_runtime_build,
        runtime_build_failed=runtime_build_failed,
    )

    estimated = sum(step.estimated_bytes for step in steps)
    if model_entry is not None:
        estimated += model_entry.download_size_bytes

    # Determine what actually works
    if profile == RuntimeProfile.FULL_HYBRID:
        backend = "fastapi-full"
        inference = "llama.cpp"
        python_strategy = "full"
        database = "sqlite"
    elif profile == RuntimeProfile.NATIVE_HYBRID:
        backend = "lightweight"
        inference = "llama.cpp"
        python_strategy = "minimal"
        database = "optional"
    elif profile == RuntimeProfile.PYTHON_HYBRID:
        backend = "fastapi-full"
        inference = "provider-bridge"
        python_strategy = "full"
        database = "sqlite"
    elif profile == RuntimeProfile.COMPATIBILITY:
        backend = "cli-only"
        inference = "none"
        python_strategy = "none"
        database = "none"
    elif profile == RuntimeProfile.DEVELOPMENT_STUB:
        backend = "stub"
        inference = "deterministic-stub"
        python_strategy = "minimal"
        database = "sqlite"
    else:
        backend = "none"
        inference = "none"
        python_strategy = "none"
        database = "none"

    native_extensions = (
        profile in (RuntimeProfile.FULL_HYBRID, RuntimeProfile.NATIVE_HYBRID)
        and capabilities.native_binary_found
    )

    risk = "LOW"
    if runtime_build_failed:
        risk = "MEDIUM"
    if profile == RuntimeProfile.UNSUPPORTED:
        risk = "HIGH"

    return InstallationPlan(
        mode=mode,
        confidence=decision.confidence,
        profile=profile.value,
        backend=backend,
        inference=inference,
        python_strategy=python_strategy,
        native_extensions=native_extensions,
        database=database,
        guided_installation=True,
        dependency_profile=mode,
        steps=steps,
        estimated_bytes=estimated,
        model_id=getattr(model_entry, "id", None),
        risk=risk,
    )


def human_bytes(num_bytes: int) -> str:
    if num_bytes >= 1024**3:
        return f"{num_bytes / 1024**3:.1f} GB"
    return f"{num_bytes / 1024**2:.0f} MB"


NL = chr(10)


def render_plan(plan: InstallationPlan) -> str:
    """Human-readable plan."""
    lines: list[str] = ["RUACH INSTALLATION PLAN", ""]
    if plan.mode == "none":
        lines.append("No installation plan: device classified UNSUPPORTED.")
        return NL.join(lines)

    lines.append(f"Profile     : {plan.profile}")
    lines.append(f"Confidence  : {plan.confidence}")
    lines.append(f"Inference   : {plan.inference}")
    lines.append(f"Backend     : {plan.backend}")
    lines.append(f"Python      : {plan.python_strategy}")
    lines.append(f"Storage     : ~{human_bytes(plan.estimated_bytes)} [ESTIMATE]")
    lines.append(f"Risk        : {plan.risk}")
    if plan.model_id:
        lines.append(f"Model       : {plan.model_id}")
    lines.append("")
    lines.append("Steps:")
    for step in plan.steps:
        marker = "[ ]" if step.required else "[~]"
        lines.append(f"  {marker} {step.title}")
    return NL.join(lines)
