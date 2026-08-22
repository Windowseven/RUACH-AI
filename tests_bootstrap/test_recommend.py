from pathlib import Path

from ruach_setup.capability import analyze, build_profile
from ruach_setup.device import RawEnvironment
from ruach_setup.recommend import recommend
from ruach_setup.registry import ModelEntry, RuntimeEntry, load_models, load_runtimes

DATA = Path(__file__).parents[1] / "ruach_setup" / "data"


def assessment_for(**raw_overrides):
    raw = RawEnvironment(
        platform_name="Linux",
        termux_prefix="/data/data/com.termux/files/usr",
        termux_version="0.118.3",
        android_build_prop_exists=True,
        machine="aarch64",
        cpu_cores=8,
        mem_total_kb=8 * 1024**3 // 1024,
        mem_available_kb=int(4.6 * 1024**3) // 1024,
        home_path="/home/u",
        storage_total_bytes=64 * 1024**3,
        storage_free_bytes=30 * 1024**3,
        python_version="3.14.6",
    )
    from dataclasses import replace

    return analyze(build_profile(replace(raw, **raw_overrides)))


def tiny_model(model_id: str, memory_mb: int) -> ModelEntry:
    return ModelEntry(
        id=model_id,
        family="test",
        parameters="tiny",
        format="gguf",
        quantization="Q0",
        file_name=f"{model_id}.gguf",
        download_size_bytes=memory_mb * 1024 * 1024,
        estimated_memory_bytes=memory_mb * 1024 * 1024,
        min_recommended_memory_bytes=memory_mb * 1024 * 1024,
        max_context_tokens=2048,
        quality_tier="light",
        speed_expectation="fast",
        status="experimental",
        source_url="https://example.invalid/x.gguf",
        sha256="",
    )


def test_arm64_balanced_recommends_llamacpp_and_largest_fitting_model():
    result = recommend(
        assessment_for(), load_runtimes(DATA / "runtimes.toml"), load_models(DATA / "models.toml")
    )
    assert result.runtime_id == "llama_cpp"
    assert result.model_id == "qwen3-4b"
    assert result.ok
    assert any("officially supports arm64" in r for r in result.reasons)
    assert any("fits within the safe memory budget" in r for r in result.reasons)
    assert ("qwen3-0.6b", "valid fallback if the recommended model fails") in result.alternatives


def test_itel_real_device_gets_no_model_but_explains_why():
    result = recommend(
        assessment_for(machine="armv7l", mem_total_kb=1_872_060, mem_available_kb=640_700),
        load_runtimes(),
        load_models(),
    )
    assert result.runtime_id == "llama_cpp"
    assert result.model_id is None
    assert not result.ok
    assert "RUNTIME_ARCH_EXPERIMENTAL" in result.warnings
    assert "MEMORY_BUDGET_INSUFFICIENT" in result.warnings
    assert all("exceeds available budget" in why for _, why in result.alternatives)


def test_small_budget_no_candidate_fits():
    result = recommend(
        assessment_for(machine="armv7l", mem_available_kb=900 * 1024),
        load_runtimes(),
        load_models(),
    )
    assert result.model_id is None
    assert not result.ok
    assert len(result.alternatives) == 2
    assert all("exceeds safe budget" in why for _, why in result.alternatives)


def test_unknown_memory_blocks_recommendation():
    result = recommend(
        assessment_for(mem_total_kb=None, mem_available_kb=None),
        load_runtimes(),
        load_models(),
    )
    assert result.ok is False
    assert "CAPABILITY_UNKNOWN" in result.warnings
    assert any("without reliable memory information" in r for r in result.reasons)


def test_unsupported_architecture_blocks_runtime():
    result = recommend(
        assessment_for(machine="sparc"),
        load_runtimes(),
        load_models(),
    )
    assert result.runtime_id is None
    assert not result.ok
    assert "ARCHITECTURE_UNSUPPORTED" in result.warnings


def test_x86_64_is_experimental_not_supported():
    result = recommend(
        assessment_for(machine="x86_64"),
        load_runtimes(),
        load_models(),
    )
    assert result.runtime_id == "llama_cpp"
    assert "RUNTIME_ARCH_EXPERIMENTAL" in result.warnings


def test_insufficient_storage_excludes_model_and_warns():
    result = recommend(
        assessment_for(),
        load_runtimes(),
        load_models(),
        storage_free_bytes=100 * 1024 * 1024,
    )
    assert result.model_id is None
    assert "INSUFFICIENT_STORAGE" in result.warnings
    assert all("storage" in why for _, why in result.alternatives)


def test_registry_order_defines_preference_with_synthetic_entries():
    runtimes = load_runtimes()
    models = {"bigger": tiny_model("bigger", 500), "smaller": tiny_model("smaller", 100)}
    # available ~1.45 GiB -> budget ~550 MiB: only "bigger" fits
    result = recommend(assessment_for(mem_available_kb=1_480_000), runtimes, models)
    assert result.model_id == "bigger"
    assert result.alternatives[0][0] == "smaller"
    models_reordered = {"smaller": models["smaller"], "bigger": models["bigger"]}
    # available ~0.98 GiB -> budget ~152 MiB: only "smaller" fits
    result2 = recommend(assessment_for(mem_available_kb=1_000_000), runtimes, models_reordered)
    assert result2.model_id == "smaller"
    assert result2.alternatives[0][0] == "bigger"


def test_missing_primary_runtime_is_reported():
    fake_runtime = RuntimeEntry(
        id="other",
        name="Other",
        interface="cli",
        server_binary="other",
        status="optional_future",
        acquisition="source_build",
        supported_architectures={"arm64": "supported"},
        pin_policy="tag",
        source_url="https://example.invalid",
        notes="",
    )
    result = recommend(assessment_for(), {"other": fake_runtime}, load_models())
    assert result.runtime_id is None
    assert "NO_PRIMARY_RUNTIME" in result.warnings
    assert not result.ok


def test_every_recommendation_reason_mentions_model_fit_or_failure():
    for kwargs in (
        {},
        {"machine": "armv7l", "mem_total_kb": 1_872_060, "mem_available_kb": 640_700},
        {"machine": "sparc"},
    ):
        result = recommend(assessment_for(**kwargs), load_runtimes(), load_models())
        if result.model_id or not result.ok:
            assert result.reasons, f"unexplained result for {kwargs}"
