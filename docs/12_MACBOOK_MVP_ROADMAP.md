# 12 — MacBook MVP Roadmap (Roadmap Correction)

**Document:** `12_MACBOOK_MVP_ROADMAP.md`
**Version:** 1.0
**Status:** APPROVED (user directive, 2026-08-23)
**Supersedes:** any interpretation that treated component completion or
target-device preparation as project completion.

---

# 1. The Correction

The statement "the Mac side of the project is complete" is rejected.

The MacBook is the **DEVELOPMENT WORKSTATION**. Android + Termux is the
**TARGET RUNTIME**. These are different concepts.

The correct lifecycle:

```text
ARCHITECTURE
    ↓
IMPLEMENTATION
    ↓
LOCAL DEVELOPMENT
    ↓
FULL PRODUCT INTEGRATION
    ↓
MACBOOK END-TO-END VALIDATION   ← first major Definition-of-Done gate
    ↓
PRODUCT READY
    ↓
ANDROID + TERMUX TARGET VALIDATION
    ↓
TARGET-SPECIFIC FIXES
    ↓
RELEASE
```

Definition of Done is based on **USER FLOW**, not on files written or modules
finished in isolation.

---

# 2. MVP Completion Path (must work as one coherent experience)

```text
User
 ↓
./ruach setup
 ↓
environment detection
 ↓
configuration
 ↓
runtime preparation
 ↓
model configuration
 ↓
RUACH backend
 ↓
AI inference
 ↓
frontend
 ↓
browser UI
 ↓
chat
 ↓
AI response
```

RUACH is a product, not a collection of engineering components.
The UI is not final decoration; the user experience IS part of the product.

---

# 3. Three Product Surfaces

| Surface | Scope |
|---|---|
| **A. Bootstrap / CLI** (`./ruach`) | setup, detection, configuration, dependency + runtime + model preparation, diagnostics, health checks |
| **B. AI Backend** | API, orchestration, inference, conversation, tool engine, security boundaries, persistence |
| **C. Frontend** | boot sequence, RUACH identity, chat workspace, real backend integration — NOT a static mockup |

---

# 4. ADB and Transfer Stance

ADB (and `staging/push_model.sh`) are **developer validation conveniences
only**. They are NOT part of RUACH's product architecture. The production
user flow is:

```text
Android user → Termux → git clone RUACH → ./ruach setup → RUACH READY
```

No MacBook required. No ADB required. Model acquisition must ultimately work
through `./ruach setup` itself (registry URL + verified download already
implemented for this purpose).

---

# 5. Definitions of Done (per surface)

## CLI (doc §8)
`./ruach`, `setup`, `doctor`, `--help`, `--version` work coherently; and
`./ruach setup` can take a clean environment to RUACH READY with no hidden
manual steps.

## AI layer (doc §10)
prompt → API → orchestrator → InferencePort → local runtime → model →
response → API → frontend → user. The adapter stays behind the port; no
architecture bypass for demo purposes.

## Tool Engine (doc §11, per docs/05)
AI → structured tool request → policy → approval → execution → result.
No unrestricted shell execution; dangerous operations per Security
Architecture (deny-by-default, workspace boundary, approval binding, audit).

## Frontend (doc §9, per docs/09)
boots, shows RUACH identity and intended visual language, loading/boot
sequence driven by REAL backend state, connects to actual backend, sends real
prompts, receives real responses, handles loading/error/connection states,
works on mobile-sized screens, avoids generic "AI SaaS" visual patterns.

## Integration gate (doc §12)
Fresh development environment → `ruach setup` → backend → local inference →
frontend → browser → chat → real response. This scripted, repeatable test is
the **MACBOOK END-TO-END MVP** milestone.

---

# 6. Honest Status at Time of Correction

```text
Architecture             COMPLETE        docs 00–11
Backend implementation   IN PROGRESS     chat/conversations/db/status done; orchestrator thin; NO tool engine code
CLI                      IN PROGRESS     setup/doctor/install-model done; `ruach start` missing; dev-host runtime path missing
AI integration           IN PROGRESS     LlamaCppAdapter built but never proven against a real llama-server
Tool Engine              NOT STARTED     spec complete (docs/05), zero implementation
Frontend                 NOT STARTED     spec complete (docs/09), zero implementation
End-to-end integration   NOT STARTED
MacBook product test     NOT STARTED     ← current milestone
Termux validation        DEFERRED        until the gate above passes
Release                  NOT STARTED
```

---

# 7. Increment Plan Toward the Gate

| Inc | Content | Closes |
|---|---|---|
| 8 | Dev-host inference bring-up: build llama.cpp locally, `ruach start` skeleton, prove real prompt→response through InferencePort | AI integration — DONE: compiled from source (CPU), Qwen3-0.6B-Q8_0 served, real round-trip ~12s through full stack; n_predict cap + <think> stripping added; real-model proposal formatting unreliable at 0.6B (fail-safe held: invented syntax = inert text); GBNF grammar constraint is post-gate work |
| 9 | Tool Engine core per docs/05: ToolRequest schema, PolicyEngine (ALLOW/DENY/REQUIRE_APPROVAL), workspace boundary + safe path resolution, approval store + binding, filesystem read/list/write executor, audit log, adversarial security tests | Tool Engine — DONE (d538ca8): core+API+orchestrator; model proposals parsed from `<tool_request>` blocks, approvals surfaced to UI, decisions recorded as tool events |
| 10 | Frontend MVP per docs/09: design tokens, boot screen wired to `/status`, chat workspace, composer, error/offline states, mobile layout; vanilla HTML/CSS/JS served by FastAPI (single process — also the right shape for Termux; doc 09 §83/§87 discourage heavy frameworks) | Frontend — boot+chat+approval card live (a2ed12f, 6a27421); settings/tool-approval views remain |
| 11 | Full `./ruach start` wiring: load generated env config, spawn llama-server if configured, launch uvicorn serving UI+API, health checks; doctor upgrades | CLI DoD |
| 12 | Scripted fresh-environment E2E test = **MACBOOK MVP GATE**; then resume target validation (docs/11) on the phone | Gate |

## Priority 3 — Multi-Turn Conversation (DONE)

Layering enforced: route -> ConversationService -> ConversationRepository /
MessageRepository -> ContextBuilder(RecentMessagesStrategy) -> InferencePort.
Bounded window via RUACH_CONTEXT_MAX_MESSAGES (default 12); system instructions
are code-owned; tool results persist into history (bounded preview) and flow
back to the model. Migration c3d7e1a9f2b4 adds messages(conversation_id, seq)
index + conversations.updated_at.

Proofs: tests/test_memory.py T1-T7 (continuity, coreference, tool context,
isolation, boundary, restart, malicious-history inertness) + live suite 5/5
with the real Qwen model incl. name recall and cross-turn read. Acceptance
demo executed over HTTP against the live stack.

Honest claim (docs/13 §30): RUACH has persistent multi-turn conversation
context. NOT long-term semantic memory.

Rules that continue to apply: no architectural pivots without evidence; no
"complete" claims without running user-flow proof; target-device facts only
from the device.

Streaming (SSE) is deliberately deferred until after the gate; MVP proves
non-streaming round-trip first (docs/09 §34 states apply when it exists).

## Priority 4 — Persistent Approvals (DONE)

Approval requests moved from an in-memory side-channel into SQLite
(`approval_requests` table, migration d5e8f2a7b3c1): arguments live IN the
record, conversation linkage is stored at creation, and every record ends in
APPROVED/CONSUMED, REJECTED or EXPIRED — no silent orphaned state. `ApprovalIndex`
deleted; the store is the single source of truth.

Key engineering findings (directive docs/13 P4):

1. **SQLite transaction discipline.** The chat turn must not hold a write
   transaction across inference: user message now COMMITS before
   `run_turn()`; results persist in a second short transaction. Crash
   property: the user's words survive even if inference dies mid-turn.
   `busy_timeout` (RUACH_DATABASE_BUSY_TIMEOUT_MS, default 5000) mitigates
   short contention only — it is NOT a substitute for correct boundaries.
2. **Failure classification.** Infrastructure failures no longer masquerade
   as security denials: DB/store outages produce SYSTEM_ERROR + honest
   "internal system error" text + `tool_execution_error` audit events.
   Policy denials keep their security events. Both still fail closed;
   nothing executes on either class of failure. False `tool_denied` audit
   records are treated as unacceptable (audit = evidence).
3. **Timezone correctness.** SQLite returns naive datetimes; TTL math must
   normalize to UTC or expiry skews by the local offset (found on EAT/+3).
4. **Degenerate sampling hardening.** Bounded resampling (max 3 samples)
   for echo/fence loops with honest no-action fallback. Known residual:
   Qwen3-0.6B occasionally burns tokens on reasoning spill; sampling knobs
   (`/no_think`, repeat penalty) are a P8-hardening candidate, deferred.

Proofs: tests/test_approval_persistence.py A–F + outage-classification
tests (restart survival via two fresh engine instances over one DB file,
approve/reject/expiry persisted, stale sweep idempotent, fingerprint
binding survives restart). Live acceptance against real Qwen backend:
approval created → server killed/restarted → same approval id approved →
tool executed; separate run with RUACH_APPROVAL_TTL_SECONDS=8 → late
approve → honest EXPIRED denial, nothing executed. Full gates green:
unit 80 passed, ruff clean, mypy clean, live suite 5/5.

Orphan policy (#13): deleting a conversation SETs conversation_id NULL;
the row stays auditable, cannot be executed via chat (404), and expires
by TTL at the latest. Direct tools-API approvals are conversation-less by
design and resolve only through that endpoint.

## Priority 5 — Fresh Database / Migration Gate (DONE)

Alembic is now the authoritative production schema path. `create_all()`
survives ONLY in isolated test fixtures (audited: no production call site).
Startup no longer trusts the database: a new boot hook verifies every ORM
table exists and FAILS LOUDLY (`run alembic upgrade head` diagnostic)
instead of silently repairing — a migration failure is a boot failure.

Proofs (backend/tests/test_fresh_database_gate.py, 7 tests): empty DB →
`alembic upgrade head` → head matches repository head (single-head chain
asserted); migrated schema compared table-for-table against ORM metadata
plus directive spot-checks (messages.seq, approval columns, CHECK
constraint, both indexes, FK ondelete=SET NULL); real app boots against the
migrated temp DB via the production config mechanism (RUACH_DATABASE_URL,
isolated workspace+audit paths) with lifespan running; representative E2E:
conversation → user message → protected request → PENDING approval row in
SQLite → approve after process restart → CONSUMED + assistant reply; an
UNMIGRATED db fails startup loudly (RuntimeError, never self-heals);
newest migration downgrades and re-upgrades cleanly on SQLite; P4 approval
reconstruction from empty DB (create → restart → resolve) re-proven.
Single-database integrity (#18): conversations, messages and approvals all
verified inside the one configured file.

Acceptance demo (#24), scripted and repeatable:
backend/scripts/fresh_install_demo.sh — two installs from zero in separate
temp dirs: migrate → verify head → boot → health → conversation → tool
request → kill server → restart → approve → execution confirmed → schema
dumps diffed IDENTICAL. "RUACH can reconstruct its persistence layer from
source-controlled migrations" now has standing evidence.

env.py note: an explicitly injected sqlalchemy.url (gate/tests) wins;
otherwise settings/RUACH_DATABASE_URL remain the only configuration source.
Model sampling hardening (/no_think etc.) stays parked for the future
runtime-hardening phase per senior-dev instruction.

## Priority 6 — Frontend E2E (DONE)

The UI is now proven by automated browser tests, not manual clicking.
`backend/tests/test_frontend_e2e.py` spins a fully isolated stack (fresh
migrated SQLite, own workspace + audit log, stub model runtime) and drives
headless Google Chrome via Playwright (system Chrome channel; bundled
Chromium is unavailable on this macOS). Five scenarios: boot checklist must
reflect REAL /ready states before the workspace shows; chat round trip plus
cross-turn memory through the full composer→context pipeline; approval
APPROVE executes the filesystem delete for real (file verified gone on
disk); approval DENY leaves the file untouched; conversations persist and
reload from the sidebar after a page reload.

Two real defects found and fixed — exactly what this gate exists for:

1. CSS could defeat the `hidden` attribute (`.boot-screen { display:flex }`
   beats the UA stylesheet), so the boot overlay never visually dismissed.
   Global guard added: `[hidden] { display:none !important }`.
2. Rejecting an approval returned no capability in the tool activity line
   (`TOOL — REJECTED`). The decision record knows its capability regardless
   of outcome; orchestrator now carries it on REJECTED like every other
   state.

Tool-activity vocabulary in the UI now distinguishes policy DENIED from
user REJECTED. Playwright deps are isolated under the optional `e2e`
extra; the suite skips cleanly without them.

## Priority 11 — Full `./ruach start` wiring (DONE)

`ruach start` is now the real entry point a stranger uses: it loads the
generated env config (`~/.ruach/config/ruach.env`; process environment
wins over file), spawns llama-server when the runtime is configured,
launches uvicorn serving UI+API, and verifies readiness HONESTLY —
inference readiness requires an actual one-token completion (a bare
/health poll lies during model load), backend readiness is the same
/api/v1/ready contract the boot screen uses. PID files make `ruach stop`
and `ruach status` work from any shell; double-start is refused; SIGTERM/
Ctrl+C tears the whole stack down cleanly (verified: no stray processes).

Doctor upgrades: backend dependency imports, migration-chain head parsing
(stdlib regex, multi-head = failure), applied-vs-head schema check on the
real DB, generated-config parse, model artifact + llama-server binary
presence, workspace writability.

Acceptance against the REAL stack (Qwen3-0.6B via .build/runtime/
llama-server): start → ready in 35s; live chat round trip (68s CPU);
"delete report.txt" → persisted PENDING approval with correct capability/
args; full `ruach stop`; restart via `ruach start`; approval resolved
across that restart → COMPLETED, file verifiably deleted; stop leaves no
processes. Also observed and correct-by-design: Qwen proposed a malformed
write ("Content must be a string") and the engine answered an honest
policy denial instead of executing anything.

Tests: tests_bootstrap/test_runtime.py (8) covers env-file parsing,
config precedence, honest inference-readiness probing against a fake
model server (loading-state must NOT pass), stub-stack end-to-end with
real uvicorn child, double-start refusal, clean stop semantics.

## Security Observation — Malformed Tool Proposal (recorded 2026-08-23)

Observed during real `ruach start` execution: Qwen3-0.6B generated a
malformed write-tool proposal whose `content` argument was not a valid
string. Observed behavior:

    Real Model -> Malformed Tool Proposal -> Validation/Policy Boundary
    -> DENIED -> No Tool Execution

Classification:

- Model/tool-call correctness: FAIL
- Input validation: PASS
- Policy enforcement: PASS
- Fail-closed behavior: PASS
- Unauthorized execution: NONE

This confirms that malformed model output does not directly reach the tool
execution layer. This observation must NOT be interpreted as evidence that
the model's tool-calling reliability is solved. The model can be stupid;
the system must not be stupid with it. Accordingly, the MVP gate below
asserts SYSTEM honesty under BOTH branches (well-formed proposal ->
approval flow; malformed proposal -> explicit denial) and never asserts
model intelligence.

## Incident 12 — Scripted Fresh-Environment MVP Gate (DONE)

`./ruach verify` is the gate: one command from checkout to proven-working.
Stages: doctor → backend unit suite → bootstrap suite → twice-from-zero
migration demo → headless-browser E2E → (with --live) real-model smoke.
The live smoke asserts SYSTEM honesty under both proposal branches and
NEVER asserts model intelligence: a well-formed proposal must enter the
approval flow and only execute after APPROVE; anything else (malformed,
ineligible, unparseable prose) must leave the filesystem untouched. The
binding check is filesystem truth (`protected_turn_is_fail_closed`), not
model wording — "no unauthorized execution" is the invariant; denial
phrasing is noise.

Two real defects the gate caught immediately:

1. `ruach start` did not migrate a VIRGIN database — it only worked on
   machines with dev history because the backend (correctly) refuses to
   boot unmigrated. start() now runs idempotent `alembic upgrade head`
   (the sole sanctioned schema path) before launching uvicorn. Regression
   test: start() on an empty DB reaches ready with all tables present.
2. The first live-smoke classifier trusted denial PHRASES. Qwen phrased
   an honest fail-closed denial as "took no action" and the gate called
   it dishonest — proof that string matching is not a security boundary.
   Rewritten around the execution invariant above.

Full-gate result on this machine: MVP GATE PASSED including the live
stage (Qwen3-0.6B; round trips slow ~60-70s CPU, one degenerate
template-echo reply observed — system stayed honest and fail-closed
throughout; sampling hardening remains parked for the future runtime-
hardening phase).

MACBOOK MVP GATE: REACHED. Remaining per roadmap: target-device
validation (docs/11) on Android/Termux — explicitly out of scope until
senior dev says go.

## SEQUENCE CORRECTION (2026-08-23)

The earlier "MACBOOK MVP GATE: REACHED" line was PREMATURE: the MVP
definition includes audit retention and a filesystem security review,
which did not exist yet. Retracted. Termux remains the TARGET VALIDATION
environment; the MacBook is the DEVELOPMENT environment. No Termux work
starts until every Mac-side requirement reaches Definition of Done.
Reporting now follows the evidence discipline: IMPLEMENTED / MAC VERIFIED
/ TERMUX VERIFIED / UNKNOWN — never "Mac verified" as evidence of "Termux
verified".

### Security hardening delivered this phase

**Audit-log retention (P11A) — IMPLEMENTED, MAC VERIFIED.** Size-based
rotation (default 5 MB active segment), N retained rotated segments
(default 2), oldest segment deleted only at the DOCUMENTED retention
boundary; rotation renames evidence, never truncates; `read_all` spans
segments chronologically; any write/stat failure raises AuditWriteError
so tool operations FAIL CLOSED rather than execute unlogged. Settings:
RUACH_AUDIT_MAX_BYTES / RUACH_AUDIT_RETENTION_SEGMENTS.

**Filesystem TOCTOU/symlink review (P11B) — IMPLEMENTED, MAC VERIFIED.**
The validate-then-open race is closed at the kernel level: workspace root
fd pinned at construction; every intermediate component opened
O_NOFOLLOW|O_DIRECTORY (ELOOP -> policy denial); final opens use
O_NOFOLLOW, unlinks use follow_symlinks=False; writes create 0600 files;
symlink escape attempts are refused even when planted after the
policy-time check (tested by simulating the swap race). Honest residual
limitations, documented not hidden: real-directory swaps stay inside the
workspace by construction; approval binds argument STRINGS not inodes;
hardlink escapes require out-of-model write access (out of scope).

**RuntimeResolver (P12 §7) — IMPLEMENTED, MAC VERIFIED, TERMUX PENDING.**
Hardcoded `.build/runtime/llama-server` removed from orchestration.
Resolution order: RUACH_LLAMA_SERVER_BIN -> ~/.ruach/runtime/ ->
project-local .build/runtime/ -> PATH. Platform differences come from
$HOME and PATH, not from platform branches in application code.

**Process lifecycle (P12 §9) — IMPLEMENTED, MAC VERIFIED, TERMUX
UNKNOWN.** STARTING/HEALTHY/UNRESPONSIVE/STOPPING/STOPPED/FAILED recorded
in a state file; `status` combines PID liveness with an HTTP readiness
probe — an alive PID alone is explicitly NOT health proof. No speculative
Android process hacks.

**Timeouts (P12 §10) — IMPLEMENTED, MAC VERIFIED.**
RUACH_MODEL_READY_TIMEOUT_SECONDS / RUACH_BACKEND_READY_TIMEOUT_SECONDS
tunable; current defaults are DEVELOPMENT-HOST values. Target-device
defaults will come from real benchmarks — not guessed.

**./ruach verify dependency audit (P12 §8) — IMPLEMENTED.** Stage
classification: doctor=CORE (stdlib only); backend-unit/bootstrap-tests=
TEST_ONLY; fresh-install demo=PLATFORM_SPECIFIC (bash+sqlite3 CLI+mktemp,
dev convenience); browser-e2e=OPTIONAL_DEV (playwright+Chrome); live smoke
=OPTIONAL_DEV (needs built runtime+model). Missing conveniences now SKIP
with reasons instead of failing. CORE product commands (start/stop/
status/doctor) depend only on Python + venv.

### MacBook MVP checklist (§14) — current truth

| Requirement | Status |
|---|---|
| ./ruach start orchestration | MAC VERIFIED |
| Backend starts correctly | MAC VERIFIED |
| Inference runtime starts correctly | MAC VERIFIED |
| Model loads | MAC VERIFIED |
| Browser UI works | MAC VERIFIED |
| Real chat works | MAC VERIFIED |
| Multi-turn works | MAC VERIFIED |
| Tool proposal works | MAC VERIFIED (model correctness NOT implied) |
| Policy works | MAC VERIFIED |
| Approval works (persist/restart/TTL) | MAC VERIFIED |
| Tool execution works | MAC VERIFIED |
| Rejection works | MAC VERIFIED |
| Persistence works | MAC VERIFIED |
| Restart recovery works | MAC VERIFIED |
| Migrations from empty DB | MAC VERIFIED |
| Security boundaries work | MAC VERIFIED |
| Frontend E2E passes | MAC VERIFIED |
| Startup/shutdown lifecycle works | MAC VERIFIED |
| Audit logging works | MAC VERIFIED |
| Audit retention policy implemented | MAC VERIFIED (this phase) |
| Filesystem security review completed | MAC VERIFIED (this phase) |
| Documentation reflects actual behavior | IN PROGRESS (this update) |

Remaining before re-declaring the MacBook gate: full `./ruach verify`
rerun on the hardened code, then Target Device Readiness Gate DESIGN
(measurements only — no guessing).

### Target Device Readiness Gate — defined (2026-08-23)

docs/13_TARGET_READINESS_GATE.md freezes the measurement plan. The
instrument `./ruach probe` (bootstrap/probe.py) is IMPLEMENTED and MAC
VERIFIED: stdlib-only, honest statuses per section, JSON records under
~/.ruach/benchmarks/. No Termux execution has happened; every target-
device number remains UNKNOWN until a record comes from the phone.
