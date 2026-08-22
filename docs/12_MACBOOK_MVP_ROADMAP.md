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
| 8 | Dev-host inference bring-up: build llama.cpp locally, `ruach start` skeleton, prove real prompt→response through InferencePort | AI integration |
| 9 | Tool Engine core per docs/05: ToolRequest schema, PolicyEngine (ALLOW/DENY/REQUIRE_APPROVAL), workspace boundary + safe path resolution, approval store + binding, filesystem read/list/write executor, audit log, adversarial security tests | Tool Engine |
| 10 | Frontend MVP per docs/09: design tokens, boot screen wired to `/status`, chat workspace, composer, error/offline states, mobile layout; vanilla HTML/CSS/JS served by FastAPI (single process — also the right shape for Termux; doc 09 §83/§87 discourage heavy frameworks) | Frontend |
| 11 | Full `./ruach start` wiring: load generated env config, spawn llama-server if configured, launch uvicorn serving UI+API, health checks; doctor upgrades | CLI DoD |
| 12 | Scripted fresh-environment E2E test = **MACBOOK MVP GATE**; then resume target validation (docs/11) on the phone | Gate |

Rules that continue to apply: no architectural pivots without evidence; no
"complete" claims without running user-flow proof; target-device facts only
from the device.

Streaming (SSE) is deliberately deferred until after the gate; MVP proves
non-streaming round-trip first (docs/09 §34 states apply when it exists).
