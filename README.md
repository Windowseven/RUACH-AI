# RUACH

A local-first AI workspace: chat with a model that runs entirely on your
machine, and let it *propose* file actions inside one workspace folder —
which only ever execute after **you** approve them. Nothing leaves your
device.

## Quick start (development host)

```sh
./install.sh          # venv + backend + UI build + doctor
./ruach setup         # guided: llama.cpp runtime + model download
./ruach start         # http://127.0.0.1:8018 opens in your browser
```

Other commands: `./ruach stop`, `./ruach status`, `./ruach doctor`
(`--verbose`, `--json`, `--check-runtime`, `--check-inference`),
`./ruach setup --plan` (preview the installation plan without executing),
`./ruach verify` (full local MVP gate), `./ruach probe` (device
benchmark), `./ruach version`.

## What it is

- **Local intelligence** — FastAPI + SQLite backend; llama.cpp serving a
  GGUF model on loopback (or a deterministic stub for development).
- **Safety by architecture** — the model's tool requests are parsed,
  policy-checked, and held for human approval before execution. Denial
  is the default; the model can never approve itself.
- **Audited** — every proposal, decision, and execution is appended to a
  rotating local audit log; write failures halt the action.
- **Simple UI** — React + Vite + TypeScript + Tailwind, built to static
  files served by the backend (Node is needed only to build).

## Termux (Android)

The CLI itself is stdlib-only — it runs on Termux's Python with no
installation step. After cloning:

```sh
pkg update && pkg install python git
termux-wake-lock                 # keep the device awake during setup
cd RUACH-AI

./ruach                          # guided entrypoint (first run offers Setup)
# or command-by-command:
./ruach doctor                   # what THIS device can do (read-only)
./ruach setup                    # guided: directories + model + config
```

What setup does and does not do on Termux:

- **Works now:** device scan, capability report, installation plan,
  model download (verified SHA-256), config generation, verification.
- **Pending spike (docs/11):** building llama.cpp on-device. Until the
  spike records a PASS, there are two honest paths:
  - run the Part B build from docs/11 yourself and place the binary at
    `~/.ruach/runtime/llama-server` (doctor/setup then detect it), or
  - develop against the deterministic stub: `./ruach start --stub`.

For the full API/UI stack inside Termux:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -U pip wheel
pip install -e ./backend         # armv7 note: docs/15 §37 records the
                                 # pydantic-core wheel constraint here
./ruach start                    # http://127.0.0.1:8018
```

Model transfer from a development host (no big download on the phone):
see docs/11 Part C — `./staging/push_model.sh` (adb or scp routes).

## Requirements

- Python 3.11+ (3.12 tested)
- Node 20+ (build-time only)
- ~1 GB disk for runtime + small model

## Documentation

| Doc | Contents |
|---|---|
| docs/06–10 | API contract, data architecture, workflow, UI/UX, inference runtime |
| docs/12 | Roadmap + evidence-status discipline (what is verified where) |
| docs/13 | Target-device readiness gate (measurements before promises) |
| docs/14 | Threat model (assets, controls, accepted residuals) |
| docs/15 | RUACH Doctor: capability discovery → profile selection → plan → verify |
| docs/16 | Doctor & guided installation: modes, planner rules, dependency profiles |
| docs/17 | Guided CLI UX: progressive disclosure, failure menus, resume, safety |

## Development

```sh
./ruach verify        # staged gate: doctor → unit → bootstrap → fresh
                      # install ×2 → UI build → browser E2E
```

Statuses used throughout the project: IMPLEMENTED / MAC VERIFIED /
TERMUX VERIFIED / UNKNOWN — never inferred from each other.
