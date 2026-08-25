"""Planner tests — all 5 profile cases."""

from __future__ import annotations

import json
from types import SimpleNamespace

from ruach_setup.fixtures import (
    ANDROID_ARMV7_LOW_MEMORY,
    ANDROID_ARM64_CAPABLE,
    LINUX_MINIMAL_NO_TOOLCHAIN,
    NATIVE_ONLY_DEVICE,
    UNSUPPORTED_DEVICE,
)
from ruach_setup.planner import build_plan, human_bytes, render_plan
from ruach_setup.profiles import PROFILE_TO_MODE, RuntimeProfile, decide

FAKE_MODEL = SimpleNamespace(
    id="qwen3-0.6b-q8", download_size_bytes=700 * 1024 * 1024
)


def _plan_for(fixture, model=FAKE_MODEL):
    decision = decide(fixture.capabilities)
    return build_plan(decision, fixture.capabilities, model)


def test_native_hybrid_plan_steps() -> None:
    """ARMV7 with BUILDABLE inference -> NATIVE_HYBRID plan."""
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    assert plan.mode == "native"
    assert plan.profile == "NATIVE_HYBRID"
    titles = [step.title for step in plan.steps]
    assert titles[0] == "Create RUACH directories"
    assert "Prepare native runtime" in titles[1]
    assert titles[-1] == "Verify installation"
    assert len(plan.steps) >= 4


def test_full_hybrid_plan_steps() -> None:
    """Capable ARM64 with healthy deps -> FULL_HYBRID plan."""
    plan = _plan_for(ANDROID_ARM64_CAPABLE)
    assert plan.mode == "hybrid"
    assert plan.profile == "FULL_HYBRID"
    titles = [step.title for step in plan.steps]
    assert titles[0] == "Create RUACH directories"
    assert "Prepare native runtime" in titles[1]
    assert "Install Python components" in titles
    assert titles[-1] == "Verify installation"


def test_native_hybrid_characteristics() -> None:
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    assert plan.inference == "llama.cpp"
    assert plan.guided_installation is True
    assert plan.dependency_profile == "native"


def test_full_hybrid_characteristics() -> None:
    plan = _plan_for(ANDROID_ARM64_CAPABLE)
    assert plan.backend == "fastapi-full"
    assert plan.inference == "llama.cpp"
    assert plan.python_strategy == "full"
    assert plan.database == "sqlite"


def test_plan_estimates_include_model_and_are_marked() -> None:
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    assert plan.estimated_bytes >= FAKE_MODEL.download_size_bytes
    rendered = render_plan(plan)
    assert "[ESTIMATE]" in rendered


def test_python_hybrid_plan_has_no_runtime_build() -> None:
    plan = _plan_for(LINUX_MINIMAL_NO_TOOLCHAIN)
    assert plan.mode == "python"
    assert plan.profile == "PYTHON_HYBRID"
    runtime_steps = [s for s in plan.steps if s.kind == "runtime"]
    assert not runtime_steps


def test_unsupported_plan_is_empty() -> None:
    plan = _plan_for(UNSUPPORTED_DEVICE)
    assert plan.mode == "none"
    assert plan.steps == ()
    assert plan.guided_installation is False
    assert "UNSUPPORTED" in render_plan(plan)


def test_plan_json_contract() -> None:
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    data = json.loads(json.dumps(plan.to_json()))
    for key in (
        "mode",
        "confidence",
        "profile",
        "backend",
        "inference",
        "python_strategy",
        "native_extensions",
        "database",
        "guided_installation",
        "steps",
        "estimated_storage_bytes",
        "risk",
    ):
        assert key in data, key
    assert data["model"] == FAKE_MODEL.id
    assert isinstance(data["steps"], list) and data["steps"]


def test_profile_to_mode_mapping() -> None:
    assert PROFILE_TO_MODE[RuntimeProfile.FULL_HYBRID] == "hybrid"
    assert PROFILE_TO_MODE[RuntimeProfile.NATIVE_HYBRID] == "native"
    assert PROFILE_TO_MODE[RuntimeProfile.PYTHON_HYBRID] == "python"
    assert PROFILE_TO_MODE[RuntimeProfile.COMPATIBILITY] == "compatibility"
    assert PROFILE_TO_MODE[RuntimeProfile.DEVELOPMENT_STUB] == "stub"
    assert PROFILE_TO_MODE[RuntimeProfile.UNSUPPORTED] == "none"


def test_human_bytes_formatting() -> None:
    assert human_bytes(512 * 1024 * 1024) == "512 MB"
    assert human_bytes(int(1.5 * 1024**3)) == "1.5 GB"


def test_plan_risk_level() -> None:
    plan = _plan_for(ANDROID_ARM64_CAPABLE)
    assert plan.risk == "LOW"
