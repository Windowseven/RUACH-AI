# Changelog

All notable changes. Format: rough Keep-a-Changelog spirit; statuses in
entries follow the roadmap evidence discipline (IMPLEMENTED / MAC
VERIFIED / TERMUX VERIFIED / UNKNOWN).

## [0.4.0] — 2026-08-24

### Added
- **RUACH Doctor engine (docs/15):** full read-only lifecycle — SCAN →
  NORMALIZE → ANALYZE → SELECT PROFILE → PLAN → VERIFY → REPORT.
  Probes for platform/Android/Termux, memory (incl. swap configured vs
  usable), storage per filesystem, Python runtime + wheel platform +
  venv capability, toolchain (clang/gcc/make/cmake/ninja/git/rustc/
  cargo), network (offline-tolerant), native inference capability
  levels, model artifact, and Python dependency classification
  (AVAILABLE_WHEEL … SOURCE_BUILD_BLOCKED).
- **Runtime profiles & decision engine:** HYBRID-NATIVE /
  HYBRID-PYTHON / NATIVE / PYTHON / MINIMAL / UNSUPPORTED with
  explainable reasons, inspectable scores, hard-constraint overrides,
  and confidence grading. A single dependency failure never classifies
  a device unsupported (docs/15 §44); UNSUPPORTED only when every path
  fails.
- **Installation planner (docs/16):** deterministic mode rules,
  per-mode step lists (hybrid = the docs' seven steps), dependency
  profiles, ESTIMATE-marked storage figures, and `--mode` validation
  that lists available alternatives when a request exceeds device
  capabilities.
- **Synthetic device fixtures** covering Android ARMv7 low-memory
  (docs/15 §37 reference case), ARM64 capable/constrained, Linux
  ARM64/x86_64, macOS dev host, no-toolchain, native-only, and
  severely constrained classes; profile selection is asserted for all.
- **Guided setup UX (docs/17):** interactive WELCOME → SCAN → CLASSIFY
  → PLAN → CONFIRM → INSTALL → VERIFY → MODEL_SETUP → READY flow with
  visible progress, smart-default prompts, failure menus (retry /
  alternative / skip / technical details / exit), safe Ctrl+C handling
  with resume hints, idempotent re-runs, and a non-interactive mode
  with deterministic defaults and meaningful exit codes.
- **Operation logging:** timestamped logs under ~/.ruach/logs/{doctor,
  setup,...} plus append-only setup.log; secret-looking keys redacted;
  logging failures never crash diagnostics.

### Changed
- `./ruach doctor` now renders the concise capability block by default
  (Status/Profile/Inference/API/Model storage/Warnings) with
  `--verbose` for the full matrix/findings/verification detail and
  `--json` for machine-readable output; `--check-runtime` executes the
  configured llama-server binary, `--check-inference` queries a running
  server's health endpoint.
- `./ruach setup --plan` previews the installation plan without
  touching anything; interactive terminals get the guided flow while
  scripts keep the deterministic non-interactive output.
- `./ruach status` renders the human-readable status block (Runtime/
  Backend/Inference/Model/API/Storage/Overall) with `--json` retained
  for automation.
- Doctor's environment verification is strictly read-only (writability
  checked via nearest existing directory; nothing created during scan).
- Installer state advancement is forward-only, fixing a resume-order
  crash when the runtime stage was recorded before the model stage.

## [0.3.0] — 2026-08-23

### Added
- Frontend rebuilt on React 19 + Vite 7 + TypeScript strict + Tailwind v4;
  ships as static files from `frontend/dist` (Node is dev-time only).
- CI workflow: ruff + mypy + backend/bootstrap suites + UI build +
  browser E2E on every push/PR (`RUACH_E2E_BROWSER_CHANNEL` for runners).
- Adversarial proposal-parser suite; concurrency race suite; context
  endurance test.
- Runtime log rotation (5 MB, one backup generation) for backend and
  model-server logs.
- Threat model document (docs/14); installer script; version command.

### Fixed
- **Approval double-decision race (real bug):** approve/reject were
  check-then-act; concurrent decisions could both pass the PENDING check.
  Transitions are now atomic compare-and-set updates — exactly one
  decision wins; losers get non-executing outcomes. Found by the new
  race tests; stable across repeated runs.

## [0.2.0] — earlier this session
- Security hardening: audit-log retention with fail-closed writes;
  filesystem TOCTOU/symlink kernel-level defenses; RuntimeResolver;
  process lifecycle states; env-tunable timeouts; verify stage classes.
- CLI orchestration (`./ruach start|stop|status|verify`), staged MVP gate,
  device-readiness probe instrument, target readiness gate definition.

## [0.1.0]
- Backend core: conversations, context assembly, orchestrator with
  classified phases, tool engine (policy → approval → execution), audit
  log, migrations from zero, stub + llama.cpp runtimes, vanilla UI
  (since replaced), browser E2E.
