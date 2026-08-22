# RUACH — Requirements Specification

**Document:** 01_REQUIREMENTS.md
**Version:** 0.1
**Status:** Draft for approval
**Scope:** RUACH MVP

---

## 1. Purpose

This document defines the functional and non-functional requirements for the first working version of RUACH.

It is a contract between:

* the product vision
* the architecture
* the implementation
* the tests
* the developer
* OpenCode as implementation assistant

Requirements in this document must be satisfied before the corresponding feature is considered complete.

This document intentionally defines a small MVP.

---

# 2. Product Definition

RUACH is a local-first AI application running on an Android device through Termux.

The user interacts with RUACH through a browser/PWA.

The initial system provides a local conversational AI experience backed by a locally running language model.

The core request path is:

```text
User
  ↓
Browser / PWA
  ↓
localhost
  ↓
FastAPI
  ↓
AI Orchestrator
  ↓
Local Inference Engine
  ↓
Local LLM
  ↓
AI Orchestrator
  ↓
FastAPI
  ↓
Browser
```

The first MVP should prove this path reliably before adding powerful local tools.

---

# 3. MVP Goals

RUACH v0.1 must prove five things:

1. A browser can connect to RUACH through localhost.
2. FastAPI can receive and validate a chat request.
3. The application can route the request through an Orchestrator.
4. A local LLM can generate a response.
5. The response can be returned to the browser.

Secondary goals:

6. Basic local conversation persistence.
7. Clean error handling.
8. Secure local-only defaults.
9. Testable modular architecture.
10. Clear developer-facing logs without leaking sensitive content unnecessarily.

---

# 4. Explicit Non-Goals

The following are OUT OF SCOPE for v0.1 unless explicitly approved later:

* unrestricted shell execution
* autonomous destructive actions
* arbitrary filesystem modification
* package installation by the AI
* remote/public API exposure
* cloud AI providers
* multi-user authentication
* SaaS tenancy
* distributed services
* Kubernetes
* Redis
* message queues
* PostgreSQL
* vector databases
* RAG pipelines
* web browsing by the AI
* autonomous internet access
* automatic Git commits/pushes
* background autonomous agents
* voice interaction
* image generation
* mobile-native UI
* multi-model routing

These may become future capabilities, but they must not silently enter the MVP.

---

# 5. Actors

## 5.1 User

The human operating RUACH through the browser.

The user:

* opens the local RUACH interface
* submits prompts
* receives responses
* can inspect conversation history when supported
* controls approval for sensitive future capabilities

---

## 5.2 Browser / PWA

The client application.

Responsibilities:

* render the chat interface
* collect user input
* send requests to localhost
* display streaming/final responses
* display errors
* maintain client-side UI state

The browser is NOT responsible for:

* model inference
* filesystem access
* shell execution
* database access
* AI orchestration

---

## 5.3 FastAPI Server

The local HTTP application server.

Responsibilities:

* expose API endpoints
* validate incoming requests
* route requests
* enforce request-level security controls
* return responses
* expose health information where appropriate

FastAPI must not contain the core AI reasoning/orchestration logic.

---

## 5.4 AI Orchestrator

The application coordination layer.

Responsibilities:

* construct model input
* coordinate conversation context
* call the inference abstraction
* normalize model responses
* prepare future tool requests
* coordinate persistence

The Orchestrator is the central application layer between the API and AI runtime.

---

## 5.5 Local Inference Engine

The runtime abstraction responsible for executing a local model.

The application should interact with an abstraction rather than hard-coding model-runtime details throughout the codebase.

Responsibilities:

* load/use the configured local model runtime
* receive inference requests
* return generated output
* expose useful runtime errors

---

## 5.6 Local LLM

The actual language model running on-device.

The model is considered an implementation dependency of the inference layer.

The application must avoid coupling business logic directly to a specific model file.

---

## 5.7 SQLite

Local persistence.

For the MVP it may store:

* conversations
* messages
* basic application settings

Database access must remain behind a clear persistence boundary.

---

# 6. Functional Requirements

## FR-001 — Local Application Startup

RUACH MUST be able to start as a local application on the Android/Termux environment.

Expected result:

```text
RUACH process
    ↓
FastAPI server
    ↓
localhost
```

The startup process must provide a clear indication of whether the application started successfully.

---

## FR-002 — Localhost Binding

The development/default server MUST bind to localhost by default.

Preferred default:

```text
127.0.0.1
```

RUACH MUST NOT expose the API publicly by default.

Binding to all interfaces such as:

```text
0.0.0.0
```

must require an explicit configuration decision and security review.

---

## FR-003 — Browser Access

The user MUST be able to open the RUACH web interface from the same device.

The browser must be able to communicate with the local FastAPI server.

---

## FR-004 — Chat Request

The client MUST allow the user to submit a text prompt.

A request must contain sufficient information for the backend to process the message.

The backend MUST validate the request before passing it to the Orchestrator.

Invalid requests MUST return controlled errors.

---

## FR-005 — Request Routing

FastAPI MUST route valid chat requests to the AI Orchestrator.

The API layer must not duplicate orchestration logic.

Expected flow:

```text
Browser
  ↓
FastAPI
  ↓
Orchestrator
```

---

## FR-006 — Local Inference

The Orchestrator MUST be able to request inference through the Local Inference Engine.

The Orchestrator must not depend directly on UI concerns.

---

## FR-007 — Model Response

The Local LLM MUST produce a response when the model is available and correctly configured.

If the model is unavailable, the system MUST return a meaningful error rather than crashing.

Example conceptual error:

```text
Local model is unavailable.
Check model configuration and runtime status.
```

Do not expose raw stack traces to the browser in production-facing responses.

---

## FR-008 — Response Delivery

The generated response MUST travel back through:

```text
Local LLM
  ↓
Orchestrator
  ↓
FastAPI
  ↓
Browser
```

The user must receive the response in the UI.

---

## FR-009 — Conversation Context

The system SHOULD support basic conversation context.

For v0.1, context may be implemented using persisted messages.

The architecture must make it possible to improve context management later without rewriting the entire API layer.

---

## FR-010 — Local Persistence

When persistence is enabled, RUACH MUST store conversation data locally.

No conversation data should be sent to an external cloud service by the core MVP.

---

## FR-011 — Health Check

The backend SHOULD provide a lightweight health endpoint.

The health check should distinguish, where practical, between:

* application process available
* database available
* inference runtime available

Do not expose unnecessary internal details through public health responses.

---

## FR-012 — Controlled Error Handling

Expected failures MUST be handled deliberately.

Examples:

* invalid request
* database unavailable
* model unavailable
* inference failure
* malformed model response
* internal application error

The application should return safe, structured errors.

---

# 7. Security Requirements

## SR-001 — Local-Only Default

RUACH MUST default to localhost access.

No public network exposure should occur without explicit configuration.

---

## SR-002 — No Secrets in Source Code

API keys, passwords, tokens, private paths, and other secrets MUST NOT be hard-coded.

The MVP should not require cloud API keys.

---

## SR-003 — Input Validation

All externally supplied input MUST be validated at the API boundary.

Do not trust browser input.

---

## SR-004 — No Implicit Shell Execution

The MVP MUST NOT allow the LLM to execute arbitrary shell commands automatically.

A future Tool Engine must have an explicit security boundary.

---

## SR-005 — Human Approval

Any future tool capable of modifying the environment MUST support explicit user approval.

The AI must not be the final authority for sensitive operations.

---

## SR-006 — Least Privilege

Every component should receive only the permissions it actually requires.

Avoid running unnecessary processes with elevated privileges.

---

## SR-007 — Safe Error Messages

Internal stack traces, filesystem paths, secrets, and implementation details MUST NOT be exposed unnecessarily through API responses.

Detailed diagnostics belong in controlled developer logs.

---

## SR-008 — Dependency Discipline

Dependencies must be intentionally selected and reviewed.

Do not add packages simply because they are convenient.

---

# 8. Non-Functional Requirements

## NFR-001 — Maintainability

Code must be organized by responsibility.

API, orchestration, inference, persistence, and configuration must not become one monolithic file.

---

## NFR-002 — Testability

Core application logic MUST be testable without requiring a real browser for every test.

Where practical, infrastructure dependencies should be abstracted so unit tests can isolate business logic.

---

## NFR-003 — Observability

The application should provide useful developer diagnostics for:

* startup
* request lifecycle
* inference failures
* database failures
* unexpected exceptions

Logs must avoid unnecessarily dumping complete user conversations or sensitive data.

---

## NFR-004 — Performance

The MVP should remain usable on the target Android/Termux environment.

Do not optimize prematurely.

Measure before introducing complexity.

---

## NFR-005 — Offline Operation

After required software and model assets are installed, the core chat workflow MUST be capable of operating without internet access.

The MVP must not require a remote AI API.

---

## NFR-006 — Portability

Application-specific logic should not depend unnecessarily on one exact Android filesystem path.

Configuration should be used for environment-specific paths.

---

# 9. User Experience Requirements

The initial UI should communicate clearly:

* RUACH is running locally
* model status
* connection status
* current conversation
* errors
* loading/inference state

The UI should not pretend that an external cloud AI is being used.

If the local model is unavailable, the UI should clearly explain the problem.

---

# 10. Future Tool System Boundary

Tools are intentionally not part of the first core vertical slice.

When introduced, the architecture should follow:

```text
AI Orchestrator
      ↓
Tool Policy
      ↓
Tool Engine
      ↓
Specific Tool
      ↓
Termux / OS
```

The AI should NOT receive unrestricted direct shell access.

Each tool should declare:

* name
* purpose
* input schema
* read/write classification
* permission requirements
* approval requirement
* execution boundary
* output schema
* error behavior

This requirement establishes the future security boundary without prematurely implementing it.

---

# 11. Acceptance Criteria for MVP

RUACH v0.1 is considered functionally complete when all of the following are true:

### A. Startup

```text
Termux
  ↓
Start RUACH
  ↓
FastAPI available on localhost
```

### B. Browser

The browser can open the RUACH UI locally.

### C. Request

A user can enter:

```text
Hello RUACH
```

and submit it.

### D. Backend

FastAPI validates the request and routes it to the Orchestrator.

### E. AI

The Orchestrator calls the local inference layer.

### F. Model

The local model generates a response.

### G. Response

The response returns:

```text
LLM
 ↓
Orchestrator
 ↓
FastAPI
 ↓
Browser
```

### H. Failure

If the model is unavailable, the application does not crash and provides a meaningful error.

### I. Security

The default server is localhost-only and there is no unrestricted shell execution.

### J. Tests

Relevant automated tests pass.

---

# 12. Requirement Traceability

Every implementation task should be traceable to one or more requirements.

Example:

```text
Task:
Implement POST /api/chat

Requirements:
FR-004
FR-005
FR-006
FR-008
SR-003
SR-007
```

If a proposed feature cannot be mapped to an existing requirement, OpenCode should stop and ask whether the requirement should be added.

---

# 13. Change Control

Requirements are not immutable.

However, changes must be deliberate.

When proposing a new requirement, document:

1. Why it is needed.
2. What problem it solves.
3. What architecture it affects.
4. What security implications it introduces.
5. What additional implementation/testing cost it creates.

Do not silently expand the MVP.

---

# 14. Development Rule

The implementation process must follow:

```text
Requirement
   ↓
Design
   ↓
Explain
   ↓
User approval
   ↓
Implementation
   ↓
Test
   ↓
Review
   ↓
Next requirement
```

A working feature that violates the requirements or security model is NOT considered complete.

---

# 15. Guiding Principle

RUACH v0.1 should prove one thing exceptionally well:

> **A secure, understandable, genuinely local AI conversation can run from a browser through localhost to a model running on the same Android device.**

Everything else comes after this foundation.
