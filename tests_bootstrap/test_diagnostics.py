"""Diagnostics model tests (docs/16 §5-§6, docs/17 §27)."""

from __future__ import annotations

from ruach_setup.diagnostics import (
    CAPABILITY_STATES,
    DependencyState,
    InferenceLevel,
    Severity,
    Status,
    failures,
    inference_rank,
    result,
    warnings,
    worst,
)


def test_result_to_json_shape() -> None:
    item = result("python.runtime", Status.PASS, message="ok", version="3.12")
    data = item.to_json()
    assert data["capability"] == "python.runtime"
    assert data["status"] == "PASS"
    assert data["severity"] == "INFO"
    assert data["message"] == "ok"
    assert data["details"]["version"] == "3.12"
    assert data["recommended_actions"] == []


def test_worst_aggregation_order() -> None:
    assert worst([result("a", Status.PASS)]) is Status.PASS
    assert worst([result("a", Status.PASS), result("b", Status.WARN)]) is Status.WARN
    assert worst([result("b", Status.WARN), result("c", Status.FAIL)]) is Status.FAIL
    assert worst([result("d", Status.UNKNOWN)]) is Status.UNKNOWN
    assert worst([]) is Status.PASS


def test_failures_and_warnings_filters() -> None:
    items = [
        result("a", Status.PASS),
        result("b", Status.WARN),
        result("c", Status.FAIL),
    ]
    assert [item.capability for item in failures(items)] == ["c"]
    assert [item.capability for item in warnings(items)] == ["b"]


def test_inference_levels_are_ordered_claims() -> None:
    """docs/15 §13: each level is a distinct claim; compile != inference."""
    ladder = [
        InferenceLevel.NOT_TESTED,
        InferenceLevel.SOURCE_AVAILABLE,
        InferenceLevel.BUILDABLE,
        InferenceLevel.EXECUTABLE,
        InferenceLevel.MODEL_LOADABLE,
        InferenceLevel.INFERENCE_FUNCTIONAL,
    ]
    ranks = [inference_rank(level) for level in ladder]
    assert ranks == sorted(ranks), "capability levels must be monotonic"
    # A successful compilation must NOT be interpreted as inference success.
    assert inference_rank(InferenceLevel.BUILDABLE) < inference_rank(
        InferenceLevel.INFERENCE_FUNCTIONAL
    )
    assert inference_rank(InferenceLevel.INFERENCE_DEGRADED) >= inference_rank(
        InferenceLevel.MODEL_LOADABLE
    )
    assert inference_rank(InferenceLevel.INFERENCE_FAILED) <= inference_rank(
        InferenceLevel.NOT_TESTED
    )


def test_capability_states_match_docs() -> None:
    assert set(CAPABILITY_STATES) == {
        "AVAILABLE",
        "UNAVAILABLE",
        "UNKNOWN",
        "RESTRICTED",
        "NOT_REQUIRED",
    }


def test_dependency_states_match_docs() -> None:
    assert {state.value for state in DependencyState} == {
        "AVAILABLE_WHEEL",
        "SOURCE_BUILD_REQUIRED",
        "SOURCE_BUILDABLE",
        "SOURCE_BUILD_BLOCKED",
        "UNAVAILABLE",
        "UNKNOWN",
    }


def test_severity_ladder_complete() -> None:
    assert {severity.value for severity in Severity} == {
        "INFO",
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }