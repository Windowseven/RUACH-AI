"""Decision engine + fixture tests.

Tests all 5 profile cases + UNSUPPORTED:
  FULL_HYBRID, NATIVE_HYBRID, PYTHON_HYBRID, COMPATIBILITY,
  DEVELOPMENT_STUB, UNSUPPORTED
"""

from __future__ import annotations

import pytest

from ruach_setup.diagnostics import InferenceLevel
from ruach_setup.fixtures import (
    ALL_FIXTURES,
    ANDROID_ARM64_CAPABLE,
    ANDROID_ARMV7_LOW_MEMORY,
    BUILD_FAILED_DEVICE,
    LINUX_MINIMAL_NO_TOOLCHAIN,
    NATIVE_ONLY_DEVICE,
    SEVERELY_CONSTRAINED_NATIVE,
    UNSUPPORTED_DEVICE,
)
from ruach_setup.profiles import (
    ALL_MODES,
    DecisionInput,
    RuntimeProfile,
    decide,
    validate_mode,
)


@pytest.mark.parametrize("fixture", ALL_FIXTURES, ids=lambda f: f.name)
def test_fixture_selects_expected_profile(fixture) -> None:
    decision = decide(fixture.capabilities)
    assert decision.profile is fixture.expected_profile
    assert decision.reasons, "every selection must be explainable"


def test_reference_armv7_is_native_hybrid_with_explanation() -> None:
    """Reference device selects NATIVE_HYBRID (deps unavailable)."""
    decision = decide(ANDROID_ARMV7_LOW_MEMORY.capabilities)
    assert decision.profile is RuntimeProfile.NATIVE_HYBRID
    joined = " ".join(decision.reasons).lower()
    assert "native" in joined


def test_capable_android_selects_full_hybrid() -> None:
    """Capable Android ARM64 with healthy deps -> FULL_HYBRID."""
    decision = decide(ANDROID_ARM64_CAPABLE.capabilities)
    assert decision.profile is RuntimeProfile.FULL_HYBRID


def test_single_dependency_failure_never_rejects_device() -> None:
    """One failed implementation is not a failed platform."""
    capabilities = ANDROID_ARMV7_LOW_MEMORY.capabilities
    assert capabilities.rust_available is False
    assert capabilities.python_deps_healthy is False
    decision = decide(capabilities)
    assert decision.profile is not RuntimeProfile.UNSUPPORTED


def test_unsupported_only_when_every_path_fails() -> None:
    capabilities = DecisionInput(
        architecture_supported=False,
        abi="unknown",
        ram_total_bytes=None,
        ram_available_bytes=None,
        storage_free_bytes=None,
        python_ok=False,
        python_version="3.9.0",
        compilers_present=frozenset(),
        rust_available=False,
        native_binary_found=False,
        inference_level=InferenceLevel.NOT_TESTED,
    )
    decision = decide(capabilities)
    assert decision.profile is RuntimeProfile.UNSUPPORTED
    assert any("no execution path" in reason or "no supported" in reason
               for reason in decision.reasons)


def test_python_hybrid_when_no_native_path() -> None:
    decision = decide(LINUX_MINIMAL_NO_TOOLCHAIN.capabilities)
    assert decision.profile is RuntimeProfile.PYTHON_HYBRID


def test_native_hybrid_without_python() -> None:
    decision = decide(NATIVE_ONLY_DEVICE.capabilities)
    assert decision.profile is RuntimeProfile.NATIVE_HYBRID


def test_compatibility_for_severely_constrained() -> None:
    """Severely constrained device with native toolchain -> NATIVE_HYBRID."""
    decision = decide(SEVERELY_CONSTRAINED_NATIVE.capabilities)
    assert decision.profile is RuntimeProfile.NATIVE_HYBRID


def test_hard_constraints_override_scores() -> None:
    """Scores must never hide mandatory requirements."""
    capabilities = DecisionInput(
        architecture_supported=True,
        abi="x86_64",
        ram_total_bytes=8 * 1024**3,
        ram_available_bytes=6 * 1024**3,
        storage_free_bytes=100 * 1024**3,
        python_ok=True,
        python_version="3.12.0",
        compilers_present=frozenset(),
        rust_available=False,
        native_binary_found=False,
        inference_level=InferenceLevel.INFERENCE_FAILED,
        python_deps_healthy=True,
        resource_tier="performance",
    )
    decision = decide(capabilities)
    assert "No viable native inference path" in decision.hard_blocks
    assert decision.profile is RuntimeProfile.PYTHON_HYBRID


def test_confidence_downgrades_with_unknowns() -> None:
    base = dict(ANDROID_ARM64_CAPABLE.capabilities.__dict__)
    high = DecisionInput(**base)
    assert decide(high).confidence == "HIGH"

    one_unknown = DecisionInput(**{**base, "python_deps_healthy": None})
    assert decide(one_unknown).confidence == "MEDIUM"

    two_unknowns = DecisionInput(
        **{
            **base,
            "python_deps_healthy": None,
            "ram_available_bytes": None,
        }
    )
    assert decide(two_unknowns).confidence == "LOW"


def test_build_failed_device_selects_compatibility() -> None:
    """Previously failed build -> engine honestly reports COMPATIBILITY."""
    decision = decide(BUILD_FAILED_DEVICE.capabilities)
    assert decision.profile is RuntimeProfile.COMPATIBILITY
    assert any("previously failed" in r.lower() or "failed" in r.lower()
               for r in decision.reasons)


def test_unsupported_fixture() -> None:
    decision = decide(UNSUPPORTED_DEVICE.capabilities)
    assert decision.profile is RuntimeProfile.UNSUPPORTED


# ------------------------------------------------------- mode validation


def test_mode_validation_accepts_native_on_armv7() -> None:
    """ARMV7 with compilers + BUILDABLE inference -> native is viable."""
    ok, message, available = validate_mode(
        ANDROID_ARMV7_LOW_MEMORY.capabilities, "native"
    )
    assert ok is True
    assert "native" in available


def test_mode_validation_accepts_viable_modes() -> None:
    ok, message, available = validate_mode(
        ANDROID_ARM64_CAPABLE.capabilities, "hybrid"
    )
    assert ok is True and message == ""
    assert "hybrid" in available


def test_mode_validation_rejects_everything_without_inference() -> None:
    ok, _message, available = validate_mode(
        DecisionInput(
            architecture_supported=False,
            abi="unknown",
            ram_total_bytes=None,
            ram_available_bytes=None,
            storage_free_bytes=None,
            python_ok=False,
            python_version="3.7.0",
        ),
        "hybrid",
    )
    assert ok is False


def test_mode_validation_unknown_mode_lists_all() -> None:
    ok, message, _available = validate_mode(
        ANDROID_ARM64_CAPABLE.capabilities, "quantum"
    )
    assert ok is False
    assert "Unknown mode" in message
    assert set(ALL_MODES) == {"hybrid", "native", "python", "compatibility", "stub"}
