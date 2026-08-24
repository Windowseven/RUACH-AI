"""Installation planner: converts a RuntimeDecision into an InstallationPlan.

Implements docs/15 §25 (plan before modification, inspectable via
--plan), docs/16 §8-§9 (planner IO contract, deterministic rules),
§26 (dependency profiles) and docs/17 §13 (plan presentation).

All byte figures are ESTIMATES until measured on-device; every render
marks them as such, following the project evidence discipline.
"""

from __future__ import annotations

from dataclasses import dataclass

from ruach_setup.profiles import (
    PROFILE_TO_MODE,
    DecisionInput,
    RuntimeDecision,
    RuntimeProfile,
)

# Provisional component size estimates. Replaced by measured values as
# real installs accumulate; always displayed with an ESTIMATE marker.
RUNTIME_BUILD_ESTIMATE_BYTES = 160 * 1024 * 1024
PYTHON_COMPONENTS_ESTIMATE_BYTES = 45 * 1024 * 1024


@dataclass(frozen=True)
class PlanStep:
    """One inspectable installation step (docs/15 §25)."""

    index: int
    title: str
    kind: str  # directories | runtime | model | python | bridge | config | verify
    required: bool = True
    skippable: bool = False
    estimated_bytes: int = 0


@dataclass(frozen=True)
class InstallationPlan:
    """Planner output contract (docs/16 §8)."""

    mode: str  # native | hybrid | lightweight | cli | none
    confidence: str
    backend: str
    inference: str
    python_strategy: str  # full | minimal | none
    native_extensions: bool
    database: str  # sqlite | optional | none
    guided_installation: bool
    dependency_profile: str  # docs/16 §26: native|hybrid|lightweight|cli
    steps: tuple[PlanStep, ...]
    estimated_bytes: int
    model_id: str | None = None

    def to_json(self) -> dict:
        return {
            "mode": self.mode,
            "confidence": self.confidence,
            "backend": self.backend,
            "inference": self.inference,
            "python_strategy": self.python_strategy,
            "native_extensions": self.native_extensions,
            "database": self.database,
            "guided_installation": self.guided_installation,
            "dependency_profile": self.dependency_profile,
            "estimated_storage_bytes": self.estimated_bytes,
            "model": self.model_id,
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


_MODE_CHARACTERISTICS: dict[str, dict[str, str]] = {
    "hybrid": {
        "backend": "lightweight-python",
        "python_strategy": "minimal",
        "database": "optional",
    },
    "native": {
        "backend": "fastapi-full",
        "python_strategy": "full",
        "database": "sqlite",
    },
    "lightweight": {
        "backend": "minimal-python",
        "python_strategy": "minimal",
        "database": "optional",
    },
    "cli": {
        "backend": "cli-only",
        "python_strategy": "none",
        "database": "none",
    },
}


def _steps_for_mode(mode: str, *, needs_runtime_build: bool) -> tuple[PlanStep, ...]:
    """Deterministic step lists (docs/15 §25 example is the hybrid case)."""
    common_start = [
        PlanStep(1, "Create RUACH directories", "directories"),
        PlanStep(
            2,
            "Prepare native runtime"
            + (" (source build)" if needs_runtime_build else ""),
            "runtime",
            estimated_bytes=RUNTIME_BUILD_ESTIMATE_BYTES if needs_runtime_build else 0,
        ),
        PlanStep(3, "Prepare model directory", "model"),
    ]
    if mode == "hybrid":
        return tuple(
            common_start
            + [
                PlanStep(4, "Install compatible Python components", "python"),
                PlanStep(5, "Configure hybrid bridge", "bridge"),
                PlanStep(6, "Generate runtime configuration", "config"),
                PlanStep(7, "Run health checks", "verify"),
            ]
        )
    if mode == "native":
        return tuple(
            common_start
            + [
                PlanStep(4, "Install Python application layer", "python"),
                PlanStep(5, "Generate runtime configuration", "config"),
                PlanStep(6, "Run health checks", "verify"),
            ]
        )
    if mode == "lightweight":
        return tuple(
            common_start
            + [
                PlanStep(4, "Install minimal Python components", "python"),
                PlanStep(5, "Generate minimal configuration", "config"),
                PlanStep(6, "Run health checks", "verify"),
            ]
        )
    if mode == "cli":
        return tuple(
            common_start
            + [
                PlanStep(4, "Write basic configuration", "config"),
                PlanStep(5, "Run health checks", "verify"),
            ]
        )
    return ()


def build_plan(
    decision: RuntimeDecision,
    capabilities: DecisionInput,
    model_entry=None,
) -> InstallationPlan:
    """Deterministic planning rules (docs/16 §9) applied to the decision."""
    profile = decision.profile
    mode = PROFILE_TO_MODE[profile]

    if mode == "none":
        return InstallationPlan(
            mode="none",
            confidence=decision.confidence,
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

    characteristics = _MODE_CHARACTERISTICS[mode]
    needs_runtime_build = not capabilities.native_binary_found and profile in {
        RuntimeProfile.HYBRID_NATIVE,
        RuntimeProfile.HYBRID_PYTHON,
        RuntimeProfile.NATIVE,
        RuntimeProfile.MINIMAL,
    }
    steps = _steps_for_mode(mode, needs_runtime_build=needs_runtime_build)

    estimated = sum(step.estimated_bytes for step in steps)
    if model_entry is not None:
        estimated += model_entry.download_size_bytes
    if characteristics["python_strategy"] != "none":
        estimated += PYTHON_COMPONENTS_ESTIMATE_BYTES

    # Native extensions only enter through the full-stack path and only
    # when the dependency matrix proves them installable (docs/16 §10-§12).
    native_extensions = (
        mode == "native" and capabilities.python_deps_healthy is True
    )

    return InstallationPlan(
        mode=mode,
        confidence=decision.confidence,
        backend=characteristics["backend"],
        inference="llama.cpp" if capabilities.native_viable else "none",
        python_strategy=characteristics["python_strategy"],
        native_extensions=native_extensions,
        database=characteristics["database"],
        guided_installation=True,
        dependency_profile=mode,
        steps=steps,
        estimated_bytes=estimated,
        model_id=getattr(model_entry, "id", None),
    )


def human_bytes(num_bytes: int) -> str:
    if num_bytes >= 1024**3:
        return f"{num_bytes / 1024**3:.1f} GB"
    return f"{num_bytes / 1024**2:.0f} MB"


def render_plan(plan: InstallationPlan) -> str:
    """Human-readable plan (docs/15 §25 / docs/17 §13)."""
    lines: list[str] = ["Installation Plan", ""]
    if plan.mode == "none":
        lines.append("No installation plan: device classified UNSUPPORTED.")
        return NL.join(lines)

    lines.append(f"Mode      : {plan.mode} (confidence {plan.confidence})")
    lines.append(f"Backend   : {plan.backend}")
    lines.append(f"Inference : {plan.inference}")
    if plan.model_id:
        lines.append(f"Model     : {plan.model_id}")
    lines.append(f"Storage   : ~{human_bytes(plan.estimated_bytes)} [ESTIMATE]")
    lines.append("")
    for step in plan.steps:
        marker = "" if step.required else " (optional)"
        lines.append(f"[{step.index}] {step.title}{marker}")
    return NL.join(lines)


NL = chr(10)  # newline without embedding escape sequences in source


__all__ = [
    "PYTHON_COMPONENTS_ESTIMATE_BYTES",
    "RUNTIME_BUILD_ESTIMATE_BYTES",
    "InstallationPlan",
    "PlanStep",
    "build_plan",
    "human_bytes",
    "render_plan",
]