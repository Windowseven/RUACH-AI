"""Runtime profiles and the decision engine.

Implements docs/15 §14-§23 (profiles, scoring with hard-constraint
override, CapabilityReport/RuntimeDecision), docs/16 §9 (deterministic
planning rules) and docs/17 §28-§30 (decision engine, strategy priority,
ARM32 handling).

The central rule (docs/15 §44): never confuse failure of one
implementation with failure of the platform. A single dependency failure
is a soft failure that redirects strategy; UNSUPPORTED is selected only
when every viable execution path fails.

The engine is pure: it consumes a DecisionInput snapshot and never
touches the device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ruach_setup.diagnostics import InferenceLevel, inference_rank

Confidence = str  # "HIGH" | "MEDIUM" | "LOW"
NL = chr(10)  # newline without embedding escape sequences in source


class RuntimeProfile(str, Enum):
    """Runtime architecture profiles (docs/15 §14)."""

    HYBRID_NATIVE = "HYBRID-NATIVE"
    HYBRID_PYTHON = "HYBRID-PYTHON"
    NATIVE = "NATIVE"
    PYTHON = "PYTHON"
    MINIMAL = "MINIMAL"
    UNSUPPORTED = "UNSUPPORTED"


# Installation modes (docs/16 §7). Mapping from profiles is documented in
# planner.build_plan; kept here as the single source of the relationship.
PROFILE_TO_MODE: dict[RuntimeProfile, str] = {
    RuntimeProfile.HYBRID_NATIVE: "hybrid",
    RuntimeProfile.HYBRID_PYTHON: "hybrid",
    RuntimeProfile.PYTHON: "native",
    RuntimeProfile.NATIVE: "cli",
    RuntimeProfile.MINIMAL: "lightweight",
    RuntimeProfile.UNSUPPORTED: "none",
}

ALL_MODES: tuple[str, ...] = ("native", "hybrid", "lightweight", "cli")


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
        if inference_rank(self.inference_level) >= inference_rank(InferenceLevel.BUILDABLE):
            return True
        return self.inference_level is not InferenceLevel.INFERENCE_FAILED and (
            self.native_build_viable
        )


@dataclass(frozen=True)
class RuntimeDecision:
    """Explainable selection result (docs/15 §23)."""

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
    """Conceptual scoring per docs/15 §21. Hard constraints override these;
    they exist to make trade-offs inspectable, never to hide requirements."""
    scores: dict[str, int] = {}
    level = d.inference_level
    if d.native_binary_found:
        scores["native_runtime"] = 35
    elif level in {InferenceLevel.MODEL_LOADABLE, InferenceLevel.INFERENCE_FUNCTIONAL}:
        scores["native_inference_functional"] = 40
    elif d.native_build_viable:
        scores["native_compilation"] = 15
    if d.python_ok:
        scores["python_compatible"] = 15 if d.python_deps_healthy is not False else 0
    scores["http_capability"] = 10  # stdlib HTTP layer is always present
    if d.ram_available_bytes is not None:
        scores["ram_sufficient"] = 10
    if d.storage_free_bytes is not None and d.storage_free_bytes >= 1024**3:
        scores["storage_sufficient"] = 10
    return scores


def decide(d: DecisionInput) -> RuntimeDecision:
    """Deterministic, explainable profile selection.

    Priority follows docs/17 §29 adapted by hard capability gates; the
    first profile whose mandatory requirements are satisfied wins.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    hard_blocks: list[str] = []

    python_viable = d.python_ok
    native_viable = d.native_viable
    deps_healthy = d.python_deps_healthy is True
    deps_bad = d.python_deps_healthy is False
    constrained = _resource_constrained(d)

    # ---- Hard constraint bookkeeping (why NOT each higher profile) -------
    if not python_viable:
        hard_blocks.append("Python control plane unavailable")
    if not native_viable:
        hard_blocks.append("No viable native inference path")

    # ---- UNSUPPORTED gate -------------------------------------------------
    if not python_viable and not native_viable:
        reasons.append(
            "No supported Python runtime AND no possible inference runtime "
            "(no binary, no compiler toolchain); no execution path remains."
        )
        return RuntimeDecision(
            profile=RuntimeProfile.UNSUPPORTED,
            confidence="HIGH" if not d.architecture_supported else "MEDIUM",
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            scores=_compute_scores(d),
            hard_blocks=tuple(hard_blocks),
        )

    # ---- Strategy cascade (docs/16 §9 planning rules) ---------------------
    if not python_viable:
        # Native-only devices: smallest viable install first (docs/15 §19).
        if _severely_constrained(d):
            profile = RuntimeProfile.MINIMAL
            reasons.append(
                "Python is unavailable and memory is severely constrained; "
                "selecting the smallest viable native installation."
            )
        else:
            profile = RuntimeProfile.NATIVE
            reasons.append(
                "Native runtime is viable while Python is not; "
                "a CLI-first native installation fits this device."
            )
    elif not native_viable:
        # Python healthy world without local inference (e.g. dev host/stub).
        if deps_bad:
            profile = RuntimeProfile.UNSUPPORTED
            reasons.append(
                "Neither native inference nor the Python dependency path is "
                "viable; every known execution strategy failed."
            )
        else:
            profile = RuntimeProfile.PYTHON
            reasons.append(
                "Python ecosystem is usable but no native inference runtime "
                "is available yet; Python-first profile with adapter slot."
            )
            if d.environment_status == "development_host":
                reasons.append(
                    "Development host detected: the deterministic stub may "
                    "substitute for inference during development."
                )
    elif deps_healthy and not constrained:
        profile = RuntimeProfile.HYBRID_PYTHON
        reasons.append("Native inference path is viable.")
        reasons.append("Python API dependencies are installable.")
        reasons.append("Device resources are sufficient for the full stack.")
    else:
        profile = RuntimeProfile.HYBRID_NATIVE
        reasons.append("Native inference is the preferred execution path.")
        reasons.append("Python remains available for orchestration.")
        if deps_bad:
            reasons.append(
                "Some Python native dependencies cannot currently be "
                "satisfied on this device."
            )
        elif d.python_deps_healthy is None:
            warnings.append("PYTHON_DEPENDENCY_HEALTH_UNKNOWN")
        if constrained:
            reasons.append("Device resources favor native execution.")

    # ---- Soft-failure notes (never fatal alone) ---------------------------
    if d.rust_available is False and python_viable:
        warnings.append("RUST_UNAVAILABLE")
    if not d.architecture_supported:
        warnings.append("ARCHITECTURE_UNSUPPORTED")

    confidence = _confidence(d)
    return RuntimeDecision(
        profile=profile,
        confidence=confidence,
        reasons=tuple(reasons),
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
# Mode validation (docs/16 §18)


def mode_requirements(mode: str) -> tuple[str, ...]:
    """Human-readable mandatory requirements of an installation mode."""
    return {
        "native": (
            "a full Python dependency stack",
            "a viable native inference runtime",
        ),
        "hybrid": ("a viable native inference runtime",),
        "lightweight": ("a viable native inference runtime",),
        "cli": ("a viable native inference runtime",),
    }.get(mode, ())


def validate_mode(d: DecisionInput, requested: str) -> tuple[bool, str, tuple[str, ...]]:
    """Validate a user-requested mode against capabilities (docs/16 §18).

    Returns (ok, failure_message_or_empty, available_modes).
    """
    requested = requested.strip().lower()
    if requested not in ALL_MODES:
        return False, f"Unknown mode '{requested}'.", ALL_MODES

    available: list[str] = []
    if d.python_ok and d.python_deps_healthy is not False and d.native_viable:
        available.append("native")
    if d.native_viable:
        available.extend(["hybrid", "lightweight", "cli"])
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