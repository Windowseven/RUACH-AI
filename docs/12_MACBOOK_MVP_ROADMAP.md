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
