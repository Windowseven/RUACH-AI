# 10 — Inference Runtime

**Status:** Corrected architecture (supersedes the discarded Ollama-first INFRA-001 plan)

---

## 1. Architectural identity

> **RUACH is offline AI for Android using Termux.**

The target platform is the source of truth:

```text
Android
   │
   ▼
Termux
   ├── Python + FastAPI + SQLite (RUACH app)
   │
   ▼
InferencePort            (app/application/inference.py)
   │
   ▼
LlamaCppAdapter          (app/infrastructure/inference_llamacpp.py)
   │
   ▼
llama.cpp (llama-server) (local process, localhost only)
   │
   ▼
GGUF model file          (outside git, path via config)
```

| Concern | Decision |
|---|---|
| Target runtime | `llama.cpp` |
| Model candidate | `Qwen3 4B` GGUF (**candidate — not frozen until benchmarked on target hardware**, see §6) |
| Target environment | Android + Termux |
| Application boundary | `InferencePort` only — no llama.cpp types outside the adapter |
| Optional future runtimes | Ollama or others, **only if a concrete requirement appears**, always behind `InferencePort` |

Desktop (this macOS machine) is a development workbench only. Desktop compatibility is never
treated as proof of Termux compatibility.

## 2. Integration method decision

Options evaluated for driving llama.cpp from Termux:

| Option | Verdict | Reason |
|---|---|---|
| Subprocess `llama-cli` per request | Rejected | Reloads the whole GGUF on every chat turn — unusable latency for a 4B model |
| Python bindings (`llama-cpp-python`) | Deferred | Heavy native build inside Termux; in-process memory coupling; new dependency requiring justification per workflow rule #9 |
| **`llama-server` long-running process** | **Chosen** | Model loads once; stable HTTP interface on localhost; identical story on desktop and Termux; RUACH talks plain JSON with stdlib `urllib` — zero new dependencies |

Network boundary (enforced): `llama-server` binds to `127.0.0.1` only. It is infrastructure,
never exposed publicly, and all runtime specifics live exclusively inside `LlamaCppAdapter`.

## 3. Configuration

Environment variables (prefix `RUACH_`, loaded by `app/config/settings.py`):

| Variable | Default | Meaning |
|---|---|---|
| `RUACH_MODEL_RUNTIME` | `llama_cpp` | Selected runtime family |
| `RUACH_MODEL_NAME` | `qwen3` | Human-readable model identifier |
| `RUACH_MODEL_PATH` | *(empty)* | Absolute path to the `.gguf` file. Empty = adapter assumes server already loaded a model |
| `RUACH_MODEL_SERVER_URL` | `http://127.0.0.1:8080` | Where `llama-server` listens |
| `RUACH_INFERENCE_TIMEOUT_SECONDS` | `120.0` | Per-request HTTP timeout |

Model weights must never enter git. Only fields with demonstrated requirements are exposed;
context size / threads will be added after real benchmarking shows they are needed.

## 4. Failure states

Application-level exceptions (`app/application/inference.py`) mapped to API envelope codes by
`app/api/errors.py`. Raw subprocess/HTTP errors never reach users.

| Condition | Exception | HTTP | Envelope code |
|---|---|---|---|
| Runtime process not reachable | `InferenceRuntimeUnavailable` | 503 | `RUNTIME_UNAVAILABLE` |
| GGUF file missing at configured path | `ModelNotFound` | 503 | `MODEL_NOT_FOUND` |
| Server reports model still loading / load failure | `ModelLoadFailed` | 503 | `MODEL_LOAD_FAILED` |
| Request exceeded timeout | `InferenceTimeout` | 504 | `INFERENCE_TIMEOUT` |
| Non-200 from runtime / malformed output | `InferenceFailed` | 502 | `INFERENCE_FAILED` |

Health states reported by `LlamaCppAdapter.health()`: `ready`, `loading`,
`runtime_unavailable`, `model_not_found`, `model_load_failed`, `error`.

## 5. Testing layout

- `tests/test_inference_llamacpp.py` — unit tests over fake openers (connection refused,
  timeout ×2, HTTP 500, malformed output, missing model, health variants). No network, no model.
- `tests/test_integration_llamacpp.py` — real round trip through `InferencePort →
  LlamaCppAdapter → llama-server → GGUF → response`. Runs only when
  `RUACH_LIVE_INFERENCE=1` and a local `llama-server` is up.
- Chat route tests run against `StubInference` via dependency override (`tests/conftest.py`),
  so unit suites stay hermetic.

Run the live check once llama.cpp is available:

```bash
llama-server -m "$RUACH_MODEL_PATH" --host 127.0.0.1 --port 8080 &
cd backend && RUACH_LIVE_INFERENCE=1 ../.venv/bin/pytest tests/test_integration_llamacpp.py -v
```

## 6. Benchmark protocol (required before freezing the model)

Fill this on the **actual target device** (Android + Termux). Do not substitute desktop numbers.

```text
Device/Android version:
Termux version:
CPU architecture:
Available RAM at test time:
Model file:                qwen3 4B, quant: ____________
GGUF size on disk:
Context size used:
Threads used:
Test prompt:               "Summarize why local AI matters in two sentences."
Time to first token:
Approximate tokens/sec:
Total response time:
Peak RAM observed:
Stability (crashes/OOM?):
Thermal behavior:
Usable context ceiling:
```

If Qwen3 4B fails or underperforms: document failure, cause, RAM requirement, observed
limitation **first**; only then evaluate smaller GGUF candidates. No silent switches.

## 7. Termux environment investigation results

Measured on the actual target device (2026-08-22):

```text
[x] Android version ............ 15
[x] Device ..................... itel A6611L
[x] CPU architecture ........... armeabi-v7a / armv7l — 32-bit ARM, 8 cores
[x] Termux version ............. 0.118.3
[x] Python version ............. 3.14.6
[x] Available RAM .............. 1.87 MB×10⁶ kB total (1.87 GB); ~0.63 GB free at idle
[x] Available storage .......... 31 GB free
[x] Compiler availability ...... clang 21.1.8, cmake 4.4.2, ninja, git 2.55.0
[ ] llama.cpp build result ..... pending
[ ] llama-server boot .......... pending
```

Key constraint: **32-bit userland**. All binaries must be compiled natively on-device;
no prebuilt aarch64 assets are usable.

## 7b. Qwen3 4B pre-build verdict (recorded per fallback rule §16)

```text
Failure:            Model cannot be loaded on target hardware
Cause:              4B parameters at Q4 quantization ≈ 2.3–2.5 GB weights alone,
                    exceeding the device's 1.87 GB TOTAL system RAM
Performance:        Not runnable — no benchmark possible
Observed limitation: Hard physical memory ceiling (not a tuning problem)
```

Consequence: candidate evaluation proceeds to a smaller GGUF from the same model family —
**Qwen3 0.6B** (expected ~450–650 MB depending on quantization) — once llama-server is
proven working. Final freeze happens only after its full benchmark table (§6) is recorded.
No silent switch occurred: this verdict was documented first.

## 8. Ollama disposition

An earlier draft of INFRA-001 installed Ollama as the primary runtime. That decision was
reversed: the install was removed, no Ollama code paths exist, and no Ollama dependency is
declared. If Ollama is ever revisited it enters **only** as another `InferencePort`
implementation and never becomes an architectural requirement.

## 9. Development workstation reference (desktop, non-target)

Recorded for context only — these numbers prove nothing about Termux:

```text
macOS 12.7.6 Monterey, x86_64, Intel i5-5250U @1.6GHz, 4 GB RAM, 47 GB free disk
Python 3.12.14 (.venv), port 8018 default (8000 occupied by system VPN service)
Ollama GUI could not launch here (OS 12 incompatible) — noted, then removed entirely
```
