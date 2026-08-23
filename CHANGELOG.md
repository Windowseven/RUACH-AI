# Changelog

All notable changes. Format: rough Keep-a-Changelog spirit; statuses in
entries follow the roadmap evidence discipline (IMPLEMENTED / MAC
VERIFIED / TERMUX VERIFIED / UNKNOWN).

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
