# 13 — Target Device Readiness Gate

Status discipline (roadmap §18): every claim below is tagged
IMPLEMENTED / MAC VERIFIED / TERMUX VERIFIED / UNKNOWN. Nothing in this
document is TERMUX VERIFIED yet, because no Termux validation has run.
This gate DEFINES what we will measure on the target device; it does not
guess the results.

## Purpose

The MacBook is the development environment; Termux/Android is the target
validation environment. Before any Termux bring-up, this gate freezes
WHAT gets measured, WITH WHICH instrument, and HOW decisions are derived
from evidence. Rule: measurements first, defaults second, code third.

## Entry criteria

1. MacBook MVP checklist (doc 12 §14) fully MAC VERIFIED and accepted.
2. Security hardening phases delivered (audit retention, filesystem
   TOCTOU/symlink review) — done, MAC VERIFIED.
3. Platform-sensitive code paths behind explicit abstractions:
   - RuntimeResolver for binaries (no hardcoded paths) — MAC VERIFIED
   - lifecycle state machine + HTTP-probed status — MAC VERIFIED
   - env-tunable timeouts (dev-host defaults documented as such) — MAC VERIFIED
4. `./ruach probe` instrument available — IMPLEMENTED, MAC VERIFIED,
   TERMUX VERIFIED pending.

## The instrument: `./ruach probe`

Stdlib-only Python (`bootstrap/probe.py`) so it can run under Termux's
Python BEFORE heavy wheels are proven there. Writes a timestamped JSON
record to `~/.ruach/benchmarks/probe-<UTC>.json` with schema_version 1.

Sections and their honesty rules:

| Section | Measures | On failure |
|---|---|---|
| device_profile | arch, ABI, cores, RAM total/avail, storage avail | unavailable + reason |
| python | version, implementation, executable | always measured |
| backend_dependencies | per-package importability + version (fastapi, uvicorn, sqlalchemy, alembic, pydantic_core, pydantic_settings, httpx) | per-package unavailable |
| sqlite | version, WAL support (file-backed), FK enforcement | unavailable |
| runtime_binary | llama-server resolution path/source/size via RuntimeResolver | unavailable if unresolved |
| model_artifact | configured model presence + size | skipped/unavailable honestly |
| storage_paths | writability of ~/.ruach/{config,data,workspace,run,benchmarks} | per-path unavailable |
| process_lifecycle_probe | SIGKILL spawn/reap detection on THIS platform | unavailable |
| inference_latency | first-token latency, one-token p50/p95/max, 64-token p50/p95 + tokens/sec vs running endpoint | skipped if unreachable |
| manual_target_fields | battery drain during ~5 min inference, thermal throttling, background reaping, installer UX notes | recorded nulls with instructions |

The manual fields exist because no script can honestly observe Android
battery/thermal/background-kill behavior from inside Termux. They are
filled by the human validator during the session, into the record.

## Metrics → decision policy

| Metric | Instrument | Decision rule |
|---|---|---|
| RAM available at idle | device_profile | If < 1.5× observed model RSS, model is NOT deployable to that tier; capability tiers get re-derived from data (doc 10 §6 placeholders die here) |
| Cold load → first token | timed against started stack | Sets RUACH_MODEL_READY_TIMEOUT_SECONDS default = p95 × safety factor 2, ROUNDED UP, recorded in docs with the measurement |
| One-token p95 (warm) | probe inference_latency | Sets interactive expectation; UI copy must not promise faster than measured |
| 64-token p95 + tok/s | probe inference_latency | Sets RUACH_INFERENCE_TIMEOUT default headroom; if p95 > timeout × 0.5, timeout raised WITH citation or UX changed instead |
| Storage free after install | df before/after scripted install | Installer refuses below measured footprint + 20% margin |
| Backend deps import time & success | probe backend_dependencies | Any unavailable wheel → find ARM/Termux-compatible alternative BEFORE promising support; no silent pip hacks in installer |
| SIGKILL reap behavior | probe lifecycle section | Confirms our PID-liveness logic holds on-device; phantom-process risk assessed manually (backgrounded app), mitigations only if OBSERVED |
| Battery/thermal | manual fields | Record-only first pass; optimization work prioritized by evidence |

## Exit criteria (gate PASSED means)

1. A complete probe record exists FROM THE TARGET DEVICE covering every
   section measured/unavailable-with-reason (no unknown-unknowns).
2. Manual fields filled for battery, thermal, backgrounding, installer UX.
3. Every dev-host default that differs from the measured reality has been
   changed WITH a citation to the record (timeouts, tiers).
4. The §16-style installer flow has been walked once BY HAND on the
   target, with friction notes recorded — automation comes after.
5. All results reported with the four-status vocabulary; anything not
   exercised stays UNKNOWN, never inferred.

Only after exit does implementation work begin (packaging, installer
script, service integration) — each change citing the record it serves.

## What this gate explicitly forbids

- Writing Termux-specific code paths before a probe record exists.
- Claiming performance/memory figures without a record citation.
- Treating macOS numbers as transferable estimates.
