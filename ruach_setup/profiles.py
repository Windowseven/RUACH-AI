"""Runtime profiles and the decision engine (v2).

Capability-driven profile selection. RUACH must NEVER assume a single
fixed architecture. The device's actual capabilities determine which
profile is selected.

Profiles:
  FULL_HYBRID     — Python backend + native inference (best experience)
  NATIVE_HYBRID   — native inference + lightweight orchestration
  PYTHON_HYBRID   — Python backend + alternative inference provider
  COMPATIBILITY   — constrained device, no full inference, still useful
  DEVELOPMENT_STUB — development/testing only, no real inference

Central rule: never confuse failure of one implementation with failure
of the platform. A single dependency failure redirects strategy;
UNSUPPORTED is selected only when every viable execution path fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ruach_setup.diagnostics import InferenceLevel, inference_rank

Confidence = str  # "HIGH" | "MEDIUM" | "LOW"
NL = chr(10)


class RuntimeProfile(str, Enum):
    """Runtime architecture profiles — capability-driven."""

    FULL_HYBRID = "FULL_HYBRID"
    NATIVE_HYBRID = "NATIVE_HYBRID"
    PYTHON_HYBRID = "PYTHON_HYBRID"
    COMPATIBILITY = "COMPATIBILITY"
    DEVELOPMENT_STUB = "DEVELOPMENT_STUB"
    UNSUPPORTED = "UNSUPPORTED"


# Backward-compatible aliases for existing code that references old names
HYBRID_NATIVE = RuntimeProfile.FULL_HYBRID
HYBRID_PYTHON = RuntimeProfile.FULL_HYBRID
NATIVE = RuntimeProfile.NATIVE_HYBRID
PYTHON = RuntimeProfile.PYTHON_HYBRID
MINIMAL = RuntimeProfile.COMPATIBILITY

PROFILE_TO_MODE: dict[RuntimeProfile, str] = {
    RuntimeProfile.FULL_HYBRID: "hybrid",
    RuntimeProfile.NATIVE_HYBRID: "native",
    RuntimeProfile.PYTHON_HYBRID: "python",
    RuntimeProfile.COMPATIBILITY: "compatibility",
    RuntimeProfile.DEVELOPMENT_STUB: "stub",
    RuntimeProfile.UNSUPPORTED: "none",
}

ALL_MODES: tuple[str, ...] = ("hybrid", "native", "python", "compatibility", "stub")


@dataclass(frozen=True)
class DecisionInput:
    """Normalized capability snapshot consumed by decide()."""

    architecture_supported: bool
    abi: str
    ram_total_bytes: int | None
    ram_available_bytes: int | None
    storage_free_bytes: int | None
    python_ok: bool
    python_version: str
    compilers_present: frozenset[str] = frozenset()
    rust_available: bool = False
    native_binary_found: bool = False
    inference_level: InferenceLevel = InferenceLevel.NOT_TESTED
    python_deps_healthy: bool | None = None  # True/False measured; None unknown
    native_build_previously_failed: bool = False
    resource_tier: str = "unknown"  # light | balanced | performance | unknown
    environment_status: str = "unknown"  # target_device | development_host | unknown

    @property
    def native_build_viable(self) -> bool:
        has_cc = bool({"clang", "gcc"} & self.compilers_present)
        has_build = bool({"make", "cmake"} & self.compilers_present)
        return has_cc and has_build and self.architecture_supported

    @property
    def native_viable(self) -> bool:
        """Inference runtime exists or can plausibly be built on-device."""
        if self.native_binary_found:
            return True
        if self.native_build_previously_failed:
            return False
        if inference_rank(self.inference_level) >= inference_rank(InferenceLevel.BUILDABLE):
            return True
        return self.inference_level is not InferenceLevel.INFERENCE_FAILED and (
            self.native_build_viable
        )

    @property
    def python_full_stack_viable(self) -> bool:
        """Python backend + all dependencies can be installed."""
        return self.python_ok and self.python_deps_healthy is True

    @property
    def has_any_inference(self) -> bool:
        """At least one inference path is available."""
        return self.native_viable or self.python_deps_healthy is not False


@dataclass(frozen=True)
class RuntimeDecision:
    """Explainable selection result."""

    profile: RuntimeProfile
    confidence: Confidence
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    scores: dict[str, int] = field(default_factory=dict)
    hard_blocks: tuple[str, ...] = ()

    def to_json(self) -> dict:
        return {
            "profile": self.profile.value,
            "confidence": self.confidence,
            "reason": list(self.reasons),
            "warnings": list(self.warnings),
            "scores": dict(self.scores),
            "hard_blocks": list(self.hard_blocks),
        }


def _resource_constrained(d: DecisionInput) -> bool:
    return d.resource_tier == "light"


def _severely_constrained(d: DecisionInput) -> bool:
    if d.ram_available_bytes is None:
        return False
    return d.ram_available_bytes < 768 * 1024 * 1024


def _compute_scores(d: DecisionInput) -> dict[str, int]:
    scores: dict[str, int] = {}
    level = d.inference_level
    if d.native_binary_found:
        scores["native_runtime"] = 35
    elif level in {InferenceLevel.MODEL_LOADABLE, InferenceLevel.INFERENCE_FUNCTIONAL}:
        scores["native_inference_functional"] = 40
    elif d.native_build_viable and not d.native_build_previously_failed:
        scores["native_compilation"] = 15
    if d.python_ok:
        scores["python_compatible"] = 15 if d.python_deps_healthy is not False else 0
    if d.python_full_stack_viable:
        scores["python_full_stack"] = 20
    scores["http_capability"] = 10
    if d.ram_available_bytes is not None:
        scores["ram_sufficient"] = 10
    if d.storage_free_bytes is not None and d.storage_free_bytes >= 1024**3:
        scores["storage_sufficient"] = 10
    return scores


def decide(d: DecisionInput) -> RuntimeDecision:
    """Deterministic, explainable profile selection.

    Priority cascade:
      1. FULL_HYBRID — Python full stack + native inference
      2. NATIVE_HYBRID — native inference + lightweight orchestration
      3. PYTHON_HYBRID — Python stack + alternative inference (rare)
      4. COMPATIBILITY — constrained device, still useful
      5. DEVELOPMENT_STUB — dev/testing only
      6. UNSUPPORTED — nothing works
    """
    reasons: list[str] = []
    warnings: list[str] = []
    hard_blocks: list[str] = []

    native_viable = d.native_viable
    python_viable = d.python_ok
    deps_healthy = d.python_deps_healthy is True
    deps_bad = d.python_deps_healthy is False
    constrained = _resource_constrained(d)

    if not python_viable:
        hard_blocks.append("Python control plane unavailable")
    if not native_viable:
        hard_blocks.append("No viable native inference path")

    # ---- UNSUPPORTED gate -------------------------------------------------
    if not python_viable and not native_viable:
        reasons.append(
            "No supported Python runtime AND no possible inference runtime; "
            "no execution path remains."
        )
        return RuntimeDecision(
            profile=RuntimeProfile.UNSUPPORTED,
            confidence="HIGH" if not d.architecture_supported else "MEDIUM",
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            scores=_compute_scores(d),
            hard_blocks=tuple(hard_blocks),
        )

    # ---- Strategy cascade -------------------------------------------------

    # PROFILE 1: FULL_HYBRID — best experience, needs both Python + native
    if python_viable and native_viable and deps_healthy and not constrained:
        reasons.append("Native inference path is viable.")
        reasons.append("Python API dependencies are installable.")
        reasons.append("Device resources are sufficient for the full stack.")
        return RuntimeDecision(
            profile=RuntimeProfile.FULL_HYBRID,
            confidence=_confidence(d),
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            scores=_compute_scores(d),
            hard_blocks=tuple(hard_blocks),
        )

    # PROFILE 2: NATIVE_HYBRID — native inference works, Python may be limited
    if native_viable:
        if constrained or deps_bad:
            reasons.append("Native inference is available; device resources or "
                           "Python dependencies limit the full stack.")
        else:
            reasons.append("Native inference is the preferred execution path.")
        if deps_bad:
            reasons.append("Some Python native dependencies are unavailable "
                           "on this device.")
        if d.native_binary_found:
            reasons.append(f"Native runtime binary found: verified.")
        elif d.native_build_viable and not d.native_build_previously_failed:
            reasons.append("Native compilation toolchain is present.")
        return RuntimeDecision(
            profile=RuntimeProfile.NATIVE_HYBRID,
            confidence=_confidence(d),
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            scores=_compute_scores(d),
            hard_blocks=tuple(hard_blocks),
        )

    # PROFILE 3: PYTHON_HYBRID — Python works but no native inference
    if python_viable and deps_healthy:
        reasons.append("Python ecosystem is usable but no native inference "
                       "runtime is available.")
        reasons.append("An alternative inference provider would be needed.")
        return RuntimeDecision(
            profile=RuntimeProfile.PYTHON_HYBRID,
            confidence=_confidence(d),
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            scores=_compute_scores(d),
            hard_blocks=tuple(hard_blocks),
        )

    # PROFILE 4: COMPATIBILITY — something works, but not everything
    if python_viable or native_viable:
        if python_viable and deps_bad:
            reasons.append("Python is available but required native wheels "
                           "cannot be installed (source build blocked).")
        if d.native_build_previously_failed:
            reasons.append("Native runtime build was previously attempted "
                           "and failed on this device.")
        if constrained:
            reasons.append("Device resources are severely constrained.")
        reasons.append("RUACH can still provide CLI, workspace, configuration, "
                       "and diagnostics in compatibility mode.")
        return RuntimeDecision(
            profile=RuntimeProfile.COMPATIBILITY,
            confidence=_confidence(d),
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            scores=_compute_scores(d),
            hard_blocks=tuple(hard_blocks),
        )

    # PROFILE 5: DEVELOPMENT_STUB
    if d.environment_status == "development_host":
        reasons.append("Development host detected; no inference runtime "
                       "is installed but the stub can substitute.")
        return RuntimeDecision(
            profile=RuntimeProfile.DEVELOPMENT_STUB,
            confidence="HIGH",
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            scores=_compute_scores(d),
            hard_blocks=tuple(hard_blocks),
        )

    # Should not reach here given UNSUPPORTED gate above, but safety net
    return RuntimeDecision(
        profile=RuntimeProfile.UNSUPPORTED,
        confidence="LOW",
        reasons=("No profile matched; this is unexpected."),
        warnings=tuple(warnings),
        scores=_compute_scores(d),
        hard_blocks=tuple(hard_blocks),
    )


def _confidence(d: DecisionInput) -> Confidence:
    if not d.architecture_supported:
        return "LOW"
    unknowns = 0
    if d.inference_level is InferenceLevel.NOT_TESTED and not d.native_binary_found:
        unknowns += 1
    if d.python_deps_healthy is None:
        unknowns += 1
    if d.ram_available_bytes is None:
        unknowns += 1
    if unknowns >= 2:
        return "LOW"
    if unknowns == 1:
        return "MEDIUM"
    return "HIGH"


# --------------------------------------------------------------------------
# Mode validation


def mode_requirements(mode: str) -> tuple[str, ...]:
    """Human-readable mandatory requirements of an installation mode."""
    return {
        "hybrid": ("a viable native inference runtime",),
        "native": ("a full Python dependency stack", "a viable native inference runtime"),
        "python": ("a full Python dependency stack",),
        "compatibility": (),
        "stub": (),
    }.get(mode, ())


def validate_mode(d: DecisionInput, requested: str) -> tuple[bool, str, tuple[str, ...]]:
    """Validate a user-requested mode against capabilities."""
    requested = requested.strip().lower()
    if requested not in ALL_MODES:
        return False, f"Unknown mode '{requested}'.", ALL_MODES

    available: list[str] = []
    if d.python_full_stack_viable and d.native_viable:
        available.append("hybrid")
    if d.native_viable:
        available.append("native")
    if d.python_full_stack_viable:
        available.append("python")
    available.extend(["compatibility", "stub"])

    if not available:
        return False, "No installation mode is viable on this device.", ()

    if requested in available:
        return True, "", tuple(available)

    requirement_text = "; ".join(mode_requirements(requested)) or "unmet capabilities"
    message = NL.join(
        (
            f"{requested.capitalize()} mode is unavailable on this device.",
            "",
            "Why:",
            f"  requires {requirement_text}.",
        )
    )
    return False, message, tuple(available)


__all__ = [
    "ALL_MODES",
    "PROFILE_TO_MODE",
    "DecisionInput",
    "RuntimeDecision",
    "RuntimeProfile",
    "decide",
    "mode_requirements",
    "validate_mode",
]
