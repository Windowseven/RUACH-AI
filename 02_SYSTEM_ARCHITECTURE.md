# RUACH — System Architecture

**Document:** 02_SYSTEM_ARCHITECTURE.md
**Version:** 0.1
**Status:** Draft for approval
**Scope:** RUACH MVP

---

## 1. Purpose

This document defines the technical architecture of RUACH v0.1.

It explains:

* runtime topology
* application boundaries
* module responsibilities
* dependency direction
* request lifecycle
* data flow
* process boundaries
* configuration boundaries
* security boundaries
* local deployment model

This document does not define implementation details for every module. Those belong in the relevant module/design documents.

---

# 2. Architectural Goals

RUACH architecture must optimize for:

1. Security
2. Simplicity
3. Local execution
4. Testability
5. Maintainability
6. Clear dependency direction
7. Low operational complexity
8. Future extensibility

The architecture should allow future capabilities without forcing them into the MVP prematurely.

---

# 3. Architectural Style

RUACH uses a:

> **Local-first modular monolith**

It is a single application/runtime from an operational perspective, but internally divided into explicit modules with controlled dependencies.

We do NOT use microservices for the MVP.

The system should remain one deployable local application unless a future requirement proves that process separation is necessary.

---

# 4. Runtime Topology

The primary runtime exists on one Android device.

Conceptually:

```text
┌──────────────────────────────────────────────────────────────┐
│                     ANDROID DEVICE                            │
│                                                              │
│  ┌────────────────┐                                          │
│  │ Browser / PWA  │                                          │
│  │                │                                          │
│  │ RUACH UI       │                                          │
│  └───────┬────────┘                                          │
│          │ HTTP / WebSocket                                  │
│          │ 127.0.0.1:<PORT>                                  │
│          ▼                                                   │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                    TERMUX                            │    │
│  │                                                      │    │
│  │  ┌──────────────┐                                    │    │
│  │  │   FastAPI    │                                    │    │
│  │  │   API        │                                    │    │
│  │  └──────┬───────┘                                    │    │
│  │         │                                            │    │
│  │         ▼                                            │    │
│  │  ┌──────────────────┐                                │    │
│  │  │ AI Orchestrator  │                                │    │
│  │  └──────┬───────────┘                                │    │
│  │         │                                            │    │
│  │     ┌───┴───────────────┐                            │    │
│  │     ▼                   ▼                            │    │
│  │ ┌───────────┐     ┌──────────────┐                  │    │
│  │ │ SQLite    │     │ Inference    │                  │    │
│  │ │           │     │ Engine       │                  │    │
│  │ └───────────┘     └──────┬───────┘                  │    │
│  │                          │                           │    │
│  │                          ▼                           │    │
│  │                    ┌───────────┐                     │    │
│  │                    │ Local LLM │                     │    │
│  │                    └───────────┘                     │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

The browser and backend run on the same physical device.

---

# 5. Network Boundary

The MVP has a deliberate localhost boundary.

Default:

```text
Browser
   │
   │ HTTP / WebSocket
   ▼
127.0.0.1:<configured-port>
   │
   ▼
FastAPI
```

The API MUST bind to localhost by default.

The architecture assumes that localhost access is the normal communication mechanism between UI and backend.

Do not expose the API to the LAN by default.

---

# 6. Major Components

RUACH consists of these logical components:

```text
Client
  ↓
API
  ↓
Application
  ↓
AI Runtime
  ↓
Persistence
```

Expanded:

```text
Browser / PWA
      │
      ▼
FastAPI API
      │
      ▼
Application Services
      │
      ▼
AI Orchestrator
   ┌──┴─────────────┐
   ▼                ▼
Memory           Inference
   │                │
SQLite            LLM Runtime
                    │
                    ▼
                 Local LLM
```

---

# 7. Component Responsibilities

## 7.1 Browser / PWA

The client layer.

Responsibilities:

* presentation
* user input
* API communication
* streaming response display
* connection state
* client-side interaction state

It must not contain server-side secrets or privileged logic.

It must not access the local filesystem directly as part of the RUACH backend architecture.

---

## 7.2 API Layer

Technology:

**FastAPI**

Responsibilities:

* HTTP routing
* request validation
* response serialization
* authentication/authorization hooks if introduced later
* WebSocket connection handling
* API-level error mapping

The API layer should be thin.

It should delegate business behavior to application services.

### Dependency rule

```text
API → Application
```

The API must not directly manipulate the LLM runtime or database implementation when application services can perform the operation.

---

## 7.3 Application / Orchestration Layer

This is the main business logic boundary.

The AI Orchestrator coordinates:

* conversation handling
* context retrieval
* inference requests
* response assembly
* future tool decisions

The Orchestrator should not know about HTTP-specific concepts such as request objects.

It should work with application/domain data.

### Dependency rule

```text
Application → Interfaces
```

Concrete infrastructure implementations are injected behind interfaces/ports where useful.

---

# 8. Inference Boundary

The application must not spread model-runtime-specific code throughout the codebase.

Use an inference abstraction.

Conceptually:

```text
AI Orchestrator
       │
       ▼
InferencePort
       │
       ▼
LocalInferenceAdapter
       │
       ▼
Local Model Runtime
       │
       ▼
GGUF / Local Model
```

The exact inference runtime may change.

The Orchestrator should not need to know whether the underlying runtime is:

* llama.cpp
* another local runtime
* a future optimized backend

The implementation adapter owns those details.

---

# 9. Persistence Boundary

SQLite is the initial local persistence mechanism.

Conceptually:

```text
Application
    │
    ▼
Repository / Persistence Interface
    │
    ▼
SQLite Adapter
    │
    ▼
SQLite Database
```

Do not allow raw SQL/database-specific operations to leak throughout the application.

Database implementation details belong inside the persistence layer.

---

# 10. Initial Data Model Boundary

The MVP needs only a small persistence model.

Conceptually:

```text
Conversation
    │
    └── Message
           ├── role
           ├── content
           ├── timestamp
           └── metadata
```

Potential roles:

```text
user
assistant
system
```

The exact schema will be defined in the database architecture document.

Do not add tables simply because future features may need them.

---

# 11. Request Lifecycle

## 11.1 Normal Chat

The canonical request lifecycle is:

```text
1. User enters prompt
        ↓
2. Browser sends request
        ↓
3. FastAPI validates request
        ↓
4. Application service receives command
        ↓
5. Orchestrator loads context
        ↓
6. Orchestrator calls inference interface
        ↓
7. Local inference runtime executes model
        ↓
8. Local LLM generates response
        ↓
9. Orchestrator receives model output
        ↓
10. Persistence stores conversation data
        ↓
11. Application returns result
        ↓
12. FastAPI serializes response
        ↓
13. Browser renders response
```

This is the canonical MVP flow.

---

# 12. Streaming

Streaming is desirable but must not complicate the first vertical slice unnecessarily.

The architecture should allow:

```text
Local LLM
   ↓
Inference Adapter
   ↓
Orchestrator
   ↓
FastAPI WebSocket / Streaming Response
   ↓
Browser
```

However:

> Do not introduce streaming before the basic request/response path is stable and tested.

Streaming should be implemented as an evolution of the inference boundary, not as a separate architecture.

---

# 13. Error Boundary

Errors should be handled at the layer where they are meaningful.

Example:

```text
Local runtime error
      ↓
Inference Adapter
      ↓
Application-level error
      ↓
API error mapping
      ↓
Safe client response
```

Do not expose raw infrastructure exceptions directly to the browser.

---

# 14. Configuration Boundary

Environment-specific values must be configurable.

Examples:

* server host
* server port
* database path
* model path
* model runtime settings
* logging level

Application code should not hard-code machine-specific paths.

Conceptually:

```text
Environment
    ↓
Configuration Layer
    ↓
Application Components
```

Configuration should be validated at startup.

Invalid critical configuration should cause a clear startup failure rather than an obscure runtime failure.

---

# 15. Security Architecture

Security boundaries exist at multiple levels.

```text
Browser
   │
   │ untrusted input
   ▼
API Validation
   │
   ▼
Application
   │
   ▼
Inference
```

The browser is untrusted.

The model is also not treated as a trusted security authority.

This is important for future tool execution.

---

# 16. Future Tool Boundary

Tools are outside the initial core vertical slice.

When introduced:

```text
AI Orchestrator
       │
       ▼
Tool Policy
       │
       ▼
Tool Registry
       │
       ▼
Specific Tool
       │
       ▼
Termux / Android OS
```

The Orchestrator should request an action.

A policy layer decides whether the action is:

* allowed automatically
* requires approval
* forbidden

This prevents the model from directly controlling the operating system.

---

# 17. Process Model

For MVP, prefer the smallest number of processes necessary.

Conceptually:

```text
Android
  │
  └── Termux
       │
       └── RUACH process
            ├── FastAPI
            ├── Application
            ├── Orchestrator
            └── Persistence access
```

The model runtime may run:

1. inside the same process, OR
2. as a separate local process,

depending on the selected inference technology.

This decision must be made after evaluating the actual runtime.

Do not create a separate service merely for architectural aesthetics.

---

# 18. Dependency Direction

The dependency graph should generally point inward:

```text
             ┌─────────────────┐
             │   Presentation  │
             └────────┬────────┘
                      ↓
             ┌─────────────────┐
             │      API        │
             └────────┬────────┘
                      ↓
             ┌─────────────────┐
             │   Application   │
             └────────┬────────┘
                      ↓
             ┌─────────────────┐
             │    Interfaces   │
             └────────┬────────┘
                      ↓
        ┌─────────────┴─────────────┐
        ↓                           ↓
 Persistence Adapter          Inference Adapter
        ↓                           ↓
     SQLite                     LLM Runtime
```

Infrastructure should implement interfaces rather than dictate application architecture.

---

# 19. Suggested Backend Module Structure

This is a starting architecture, not permission to create all files immediately.

Conceptually:

```text
backend/
├── app/
│   ├── api/
│   ├── application/
│   ├── domain/
│   ├── infrastructure/
│   └── main.py
│
├── tests/
│
└── ...
```

Possible responsibilities:

```text
api/
    HTTP/WebSocket transport

application/
    use cases
    orchestration

domain/
    core models
    business rules
    interfaces where appropriate

infrastructure/
    SQLite
    inference runtime
    configuration
    logging
```

Exact package structure will be finalized in the project structure document.

---

# 20. Architecture Decision: Modular Monolith

### Decision

Use a modular monolith.

### Why

RUACH runs on one device and currently has one primary user.

Microservices would introduce:

* additional processes
* networking complexity
* service discovery concerns
* deployment complexity
* debugging overhead
* unnecessary resource consumption

None are justified by the MVP requirements.

### Future escape hatch

If a future requirement requires process separation, individual modules should already have clear boundaries that make extraction possible.

But we do not design for distributed deployment prematurely.

---

# 21. Architecture Decision: SQLite

### Decision

Use SQLite for MVP persistence.

### Why

RUACH is:

* local
* single-user initially
* resource-constrained
* offline-first

SQLite provides:

* zero external database server
* local persistence
* transactional behavior
* mature tooling
* low operational overhead

A future database migration should only happen if requirements justify it.

---

# 22. Architecture Decision: Localhost

### Decision

Bind the API to localhost by default.

### Why

This minimizes network attack surface.

The normal user experience is:

```text
Browser → 127.0.0.1 → RUACH
```

LAN/public access is not part of the MVP.

---

# 23. Architecture Decision: Adapter Boundary for LLM Runtime

### Decision

Hide the concrete inference runtime behind an application-facing interface.

### Why

The model runtime is infrastructure.

RUACH should be able to change inference technology without rewriting:

* API logic
* conversation logic
* persistence
* UI

The adapter owns runtime-specific behavior.

---

# 24. Architecture Invariants

The following must remain true unless an explicit architecture decision changes them:

1. Browser is the client.
2. FastAPI is the API boundary.
3. Orchestrator owns AI application coordination.
4. Model execution happens locally.
5. SQLite is local.
6. API defaults to localhost.
7. The model does not directly control the OS.
8. Sensitive tools require policy/approval.
9. Infrastructure dependencies remain behind clear boundaries.
10. MVP remains a modular monolith.
11. No cloud AI dependency is required for core operation.
12. No unnecessary distributed infrastructure is introduced.

---

# 25. Architecture Review Checklist

Before implementation begins, confirm:

* [ ] Runtime topology is understood.
* [ ] Module responsibilities are clear.
* [ ] Dependency direction is understood.
* [ ] API boundary is clear.
* [ ] Orchestrator boundary is clear.
* [ ] Inference boundary is clear.
* [ ] Persistence boundary is clear.
* [ ] Localhost security boundary is clear.
* [ ] Tool execution is isolated from the core MVP.
* [ ] No unnecessary services exist.
* [ ] The developer understands why each major component exists.

---

# 26. Final Architectural Principle

RUACH should be architecturally simple on the outside and disciplined on the inside.

Operationally:

```text
One device.
One local application.
One browser client.
One local model.
One local database.
```

Internally:

```text
Clear boundaries.
Explicit dependencies.
Controlled permissions.
Testable modules.
Deliberate evolution.
```

The architecture must remain understandable to the developer who is building it.

> **Complexity must be earned by requirements.**
