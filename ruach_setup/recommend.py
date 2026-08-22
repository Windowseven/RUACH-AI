"""Explainable recommendation engine.

Consumes a CapabilityAssessment plus the registries and produces a fully
reasoned recommendation. No RAM thresholds live here — every judgment is a
comparison against registry metadata (Amendment 1).

The engine is pure: it never touches the network, the filesystem outside
registry loading, or the device.
"""

from dataclasses import dataclass

from ruach_setup.capability import CapabilityAssessment
from ruach_setup.registry import ModelEntry, RuntimeEntry


@dataclass(frozen=True)
class Recommendation:
    runtime_id: str | None
    model_id: str | None
    ok: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    alternatives: tuple[tuple[str, str], ...]  # (model_id, why-not-chosen)


def _runtime_compatibility(runtime: RuntimeEntry, architecture: str) -> str:
    return runtime.supported_architectures.get(architecture, "unknown")


def _model_fits_memory(model: ModelEntry, budget_bytes: int) -> bool:
    return 0 < budget_bytes >= model.estimated_memory_bytes


def recommend(
    assessment: CapabilityAssessment,
    runtimes: dict[str, RuntimeEntry],
    models: dict[str, ModelEntry],
    storage_free_bytes: int | None = None,
) -> Recommendation:
    profile = assessment.profile
    reasons: list[str] = []
    warnings: list[str] = list(assessment.warnings)
    alternatives: list[tuple[str, str]] = []

    # --- Runtime selection -------------------------------------------------
    primary = next((r for r in runtimes.values() if r.status == "primary"), None)
    runtime_id: str | None = None
    if primary is None:
        warnings.append("NO_PRIMARY_RUNTIME")
        reasons.append("No primary runtime is defined in the runtime registry.")
    elif not profile.architecture_supported:
        warnings.append("ARCHITECTURE_UNSUPPORTED")
        reasons.append(
            f"Architecture '{profile.machine_raw}' is not recognized; "
            f"{primary.name} cannot be evaluated."
        )
    else:
        arch_status = _runtime_compatibility(primary, profile.architecture)
        if arch_status == "supported":
            runtime_id = primary.id
            reasons.append(f"{primary.name} officially supports {profile.architecture}.")
        elif arch_status == "experimental":
            runtime_id = primary.id
            warnings.append("RUNTIME_ARCH_EXPERIMENTAL")
            reasons.append(
                f"{primary.name} on {profile.architecture} is experimental; "
                "on-device validation is still pending."
            )
        else:
            warnings.append("RUNTIME_ARCH_UNAVAILABLE")
            reasons.append(
                f"{primary.name} has no verified compatibility with " f"{profile.architecture}."
            )

    # --- Model selection ---------------------------------------------------
    model_id: str | None = None
    budget = assessment.safe_memory_budget_bytes

    if budget is None:
        warnings.append("CAPABILITY_UNKNOWN")
        reasons.append(
            "Memory could not be determined; no model is recommended "
            "without reliable memory information."
        )
        for candidate in models.values():
            alternatives.append(
                (
                    candidate.id,
                    f"needs ~{candidate.estimated_memory_bytes // (1024 * 1024)} MiB",
                )
            )
    elif budget == 0:
        warnings.append("MEMORY_BUDGET_INSUFFICIENT")
        reasons.append("Safe memory budget is zero on this device; no model can be " "recommended.")
        for candidate in models.values():
            alternatives.append(
                (
                    candidate.id,
                    f"needs ~{candidate.estimated_memory_bytes // (1024 * 1024)} MiB, "
                    + "exceeds available budget",
                )
            )
    else:
        for candidate in models.values():
            if not _model_fits_memory(candidate, budget):
                alternatives.append(
                    (
                        candidate.id,
                        "estimated memory exceeds safe budget "
                        + f"({candidate.estimated_memory_bytes // (1024 * 1024)} MiB)",
                    )
                )
                continue
            if (
                storage_free_bytes is not None
                and storage_free_bytes < candidate.download_size_bytes * 11 // 10
            ):
                warnings.append("INSUFFICIENT_STORAGE")
                alternatives.append((candidate.id, "download size exceeds free storage margin"))
                continue
            if model_id is None:
                model_id = candidate.id
                reasons.append(
                    f"{candidate.id} ({candidate.parameters}, {candidate.quantization}) "
                    "fits within the safe memory budget of "
                    f"~{budget // (1024 * 1024)} MiB."
                )
                if candidate.status == "experimental":
                    warnings.append("MODEL_CANDIDATE_EXPERIMENTAL")
                    reasons.append("Candidate is experimental until benchmarked on this device.")
            else:
                alternatives.append((candidate.id, "valid fallback if the recommended model fails"))

    ok = runtime_id is not None and model_id is not None
    return Recommendation(
        runtime_id=runtime_id,
        model_id=model_id,
        ok=ok,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        alternatives=tuple(alternatives),
    )
