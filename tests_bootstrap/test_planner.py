"""Planner tests (docs/15 §25, docs/16 §8-§9/§26, docs/17 §13)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from ruach_setup.fixtures import (
    ANDROID_ARMV7_LOW_MEMORY,
    LINUX_MINIMAL_NO_TOOLCHAIN,
)
from ruach_setup.planner import build_plan, human_bytes, render_plan
from ruach_setup.profiles import PROFILE_TO_MODE, RuntimeProfile, decide

FAKE_MODEL = SimpleNamespace(
    id="qwen3-0.6b-q8", download_size_bytes=700 * 1024 * 1024
)


def _plan_for(fixture, model=FAKE_MODEL):
    decision = decide(fixture.capabilities)
    return build_plan(decision, fixture.capabilities, model)


def test_hybrid_plan_matches_docs_step_list() -> None:
    """docs/15 §25 example: the hybrid plan has seven inspectable steps."""
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    assert plan.mode == "hybrid"
    titles = [step.title for step in plan.steps]
    assert titles[0] == "Create RUACH directories"
    assert "Prepare native runtime" in titles[1]
    assert titles[-1] == "Run health checks"
    assert len(plan.steps) == 7
    assert [step.index for step in plan.steps] == list(range(1, 8))


def test_hybrid_plan_characteristics() -> None:
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    assert plan.backend == "lightweight-python"
    assert plan.inference == "llama.cpp"
    assert plan.python_strategy == "minimal"
    assert plan.native_extensions is False  # docs/16 §11/§12 avoidance
    assert plan.database == "optional"
    assert plan.guided_installation is True
    assert plan.dependency_profile == "hybrid"  # docs/16 §26


def test_plan_estimates_include_model_and_are_marked() -> None:
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    assert plan.estimated_bytes >= FAKE_MODEL.download_size_bytes
    rendered = render_plan(plan)
    assert "[ESTIMATE]" in rendered
    assert f"[{len(plan.steps)}]" in rendered


def test_python_only_plan_has_no_runtime_build_estimate() -> None:
    plan = _plan_for(LINUX_MINIMAL_NO_TOOLCHAIN)
    assert plan.mode == "native"  # PYTHON profile maps to full-stack mode
    runtime_step = next(step for step in plan.steps if step.kind == "runtime")
    assert runtime_step.estimated_bytes == 0  # nothing to build locally
    assert plan.native_extensions is True  # deps healthy on this fixture


def test_unsupported_plan_is_empty_and_non_executable() -> None:
    from ruach_setup.profiles import DecisionInput

    capabilities = DecisionInput(
        architecture_supported=False,
        abi="unknown",
        ram_total_bytes=None,
        ram_available_bytes=None,
        storage_free_bytes=None,
        python_ok=False,
        python_version="3.9.0",
    )
    from ruach_setup.diagnostics import InferenceLevel

    capabilities = DecisionInput(
        **{
            **{
                field_name: getattr(capabilities, field_name)
                for field_name in capabilities.__dataclass_fields__
            },
            "inference_level": InferenceLevel.NOT_TESTED,
        }
    )
    decision = decide(capabilities)
    plan = build_plan(decision, capabilities)
    assert plan.mode == "none"
    assert plan.steps == ()
    assert plan.guided_installation is False
    assert "UNSUPPORTED" in render_plan(plan)


def test_plan_json_contract_matches_docs() -> None:
    """docs/16 §8 output contract keys."""
    plan = _plan_for(ANDROID_ARMV7_LOW_MEMORY)
    data = json.loads(json.dumps(plan.to_json()))
    for key in (
        "mode",
        "confidence",
        "backend",
        "inference",
        "python_strategy",
        "native_extensions",
        "database",
        "guided_installation",
        "steps",
        "estimated_storage_bytes",
    ):
        assert key in data, key
    assert data["model"] == FAKE_MODEL.id
    assert isinstance(data["steps"], list) and data["steps"]


def test_profile_to_mode_mapping() -> None:
    assert PROFILE_TO_MODE[RuntimeProfile.HYBRID_NATIVE] == "hybrid"
    assert PROFILE_TO_MODE[RuntimeProfile.HYBRID_PYTHON] == "hybrid"
    assert PROFILE_TO_MODE[RuntimeProfile.PYTHON] == "native"
    assert PROFILE_TO_MODE[RuntimeProfile.NATIVE] == "cli"
    assert PROFILE_TO_MODE[RuntimeProfile.MINIMAL] == "lightweight"
    assert PROFILE_TO_MODE[RuntimeProfile.UNSUPPORTED] == "none"


def test_human_bytes_formatting() -> None:
    assert human_bytes(512 * 1024 * 1024) == "512 MB"
    assert human_bytes(int(1.5 * 1024**3)) == "1.5 GB"