
# RUACH — Project Structure & Code Organization

**Document:** 03_PROJECT_STRUCTURE.md  
**Version:** 0.1  
**Status:** Draft for approval  
**Scope:** RUACH MVP

---

## 1. Purpose

This document defines the repository structure and code-organization rules for RUACH.

The goal is not to create many folders for appearance.

The goal is to create boundaries that make responsibilities obvious and prevent:

- business logic leaking into API handlers
- infrastructure leaking into domain code
- giant files
- circular dependencies
- duplicated logic
- unclear ownership
- uncontrolled AI-generated code

This document is a blueprint.

OpenCode must not create the complete structure blindly. It should create files incrementally as implementation requires them.

---

# 2. Repository-Level Structure

The proposed repository structure is:

```text
ruach/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   ├── infrastructure/
│   │   ├── config/
│   │   └── main.py
│   │
│   └── tests/
│
├── frontend/
│   └── ...
│
├── docs/
│   └── ...
│
├── scripts/
│   └── ...
│
├── .env.example
├── .gitignore
├── README.md
└── ...
````

This is an architectural target.

The implementation process must still follow the project's one-file-at-a-time rule.

---

# 3. Backend Structure

Initial backend structure:

```text
backend/
├── app/
│   ├── api/
│   ├── application/
│   ├── domain/
│   ├── infrastructure/
│   ├── config/
│   └── main.py
│
└── tests/
```

---

# 4. `app/main.py`

### Responsibility

Application entry point.

It should be responsible for:

* creating/configuring the FastAPI application
* registering API routes
* configuring application lifecycle hooks
* initializing required application dependencies

It should NOT contain:

* business logic
* database queries
* model prompting logic
* tool execution logic

Keep this file small.

Conceptually:

```text
main.py
   ↓
create application
   ↓
register components
   ↓
start
```

---

# 5. `app/api/`

The API transport boundary.

Proposed structure:

```text
api/
├── routes/
├── schemas/
└── dependencies.py
```

These names are intentionally generic enough to evolve.

---

## 5.1 `api/routes/`

Contains HTTP/WebSocket route handlers.

Example future structure:

```text
routes/
├── health.py
└── chat.py
```

Route handlers should:

1. receive transport input
2. validate input
3. invoke an application use case/service
4. map result to an HTTP response

They should NOT:

* call SQLite directly
* construct model prompts directly
* execute shell commands
* contain orchestration algorithms

Bad:

```python
@router.post("/chat")
def chat(request):
    rows = sqlite.execute(...)
    prompt = build_prompt(...)
    result = model.generate(prompt)
    return result
```

Preferred conceptual flow:

```python
@router.post("/chat")
def chat(request):
    result = chat_service.execute(request)
    return result
```

---

# 6. `api/schemas/`

Contains transport-facing request/response models.

These models describe what crosses the API boundary.

Examples:

```text
ChatRequest
ChatResponse
ErrorResponse
HealthResponse
```

API schemas should not automatically become domain models.

The API contract and internal business model are separate concerns.

---

# 7. `api/dependencies.py`

Contains API-level dependency wiring.

Possible responsibilities:

* obtaining application services
* request-scoped dependencies
* shared API dependencies

Do not turn this into a global service locator.

Dependencies should remain explicit.

---

# 8. `app/application/`

This is the application/use-case layer.

Proposed structure:

```text
application/
├── chat/
├── conversation/
└── ...
```

The exact modules will grow only when requirements require them.

---

# 9. Application Layer Responsibilities

Application code coordinates use cases.

Examples:

```text
SendChatMessage
CreateConversation
GetConversation
```

A use case may coordinate:

```text
request
  ↓
load context
  ↓
call inference
  ↓
persist message
  ↓
return result
```

Application code should not care whether:

* SQLite is the database implementation
* a specific model runtime is used
* FastAPI or another transport called it

---

# 10. `app/domain/`

The domain layer contains concepts and rules that represent RUACH's core behavior.

Possible structure:

```text
domain/
├── conversation/
├── inference/
└── ...
```

The domain should remain intentionally small in the MVP.

Do not create elaborate Domain-Driven Design structures merely for terminology.

Only introduce domain objects where they improve correctness or clarity.

---

# 11. Domain Layer Rules

Domain code should not depend on:

* FastAPI
* HTTP
* SQLite implementation
* browser code
* Termux commands
* specific model-runtime SDKs

The domain should be as infrastructure-independent as reasonably possible.

---

# 12. `app/infrastructure/`

Infrastructure contains concrete implementations.

Proposed structure:

```text
infrastructure/
├── persistence/
├── inference/
└── ...
```

Possible future structure:

```text
infrastructure/
├── persistence/
│   └── sqlite/
│
├── inference/
│   └── local_runtime/
│
└── logging/
```

Infrastructure is where framework/runtime-specific details belong.

---

# 13. Persistence Structure

Potential structure:

```text
infrastructure/persistence/
└── sqlite/
    ├── database.py
    ├── models.py
    └── repositories/
```

Do not create all of these files immediately.

Create them only when the persistence implementation reaches that requirement.

Responsibilities:

```text
database.py
    connection/session configuration

models.py
    database-specific persistence models

repositories/
    persistence operations
```

Database-specific details must stay inside the persistence boundary.

---

# 14. Inference Structure

Potential structure:

```text
infrastructure/inference/
└── local_runtime/
    ├── client.py
    └── ...
```

The exact runtime is not predetermined by this document.

The architecture must support an adapter such as:

```text
Application
    ↓
InferencePort
    ↓
LocalInferenceAdapter
    ↓
Runtime
```

Do not allow runtime-specific imports to spread throughout application code.

---

# 15. `app/config/`

Configuration belongs here.

Potential responsibilities:

* environment loading
* settings validation
* paths
* server configuration
* model configuration
* database configuration

Example conceptual settings:

```text
HOST
PORT
DATABASE_PATH
MODEL_PATH
MODEL_RUNTIME
LOG_LEVEL
```

Never hard-code machine-specific paths into application modules.

---

# 16. `backend/tests/`

Tests should mirror architectural responsibilities where practical.

Possible structure:

```text
tests/
├── unit/
├── integration/
└── api/
```

---

## 16.1 Unit Tests

Test isolated logic.

Examples:

* application use cases
* domain behavior
* validation
* prompt/context construction
* error mapping

Unit tests should avoid requiring a real model whenever possible.

---

## 16.2 Integration Tests

Test component boundaries.

Examples:

```text
Application
    ↓
SQLite
```

or:

```text
Application
    ↓
Inference Adapter
```

Use controlled test implementations where possible.

---

## 16.3 API Tests

Test the FastAPI contract.

Examples:

* valid request
* invalid request
* model unavailable
* malformed input
* health endpoint

---

# 17. Test Doubles

The architecture should allow controlled substitutes for infrastructure.

For example:

```text
RealInferenceAdapter
FakeInferenceAdapter
```

This allows tests to verify application behavior without requiring a real LLM for every test.

The same principle may apply to persistence.

Do not build an elaborate mocking framework unless the project actually needs one.

---

# 18. `frontend/`

The frontend is a separate presentation application.

Its internal architecture will be defined in a dedicated frontend document.

At the system level:

```text
frontend
    ↓ HTTP/WebSocket
FastAPI
```

The frontend must not know implementation details of:

* SQLite
* local model runtime
* Termux
* Python modules

It only knows the API contract.

---

# 19. `docs/`

Documentation contains project-level engineering documents.

The architecture documents we are creating belong here in the actual repository.

Examples:

```text
docs/
├── 00_PROJECT_CHARTER.md
├── 01_REQUIREMENTS.md
├── 02_SYSTEM_ARCHITECTURE.md
├── 03_PROJECT_STRUCTURE.md
└── ...
```

Documentation should evolve with architecture decisions.

---

# 20. `scripts/`

Scripts are optional utilities for development or operational tasks.

Examples may eventually include:

```text
scripts/
├── dev.sh
├── test.sh
└── ...
```

Do not create scripts that merely wrap one obvious command unless they improve reliability or developer experience.

Never put core business logic into shell scripts.

---

# 21. Root Configuration Files

Expected root-level files may include:

```text
README.md
.gitignore
.env.example
```

Additional files depend on the selected Python/frontend tooling.

OpenCode must not invent configuration files without a reason.

---

# 22. Dependency Rules

The following dependency direction is required:

```text
API
 ↓
Application
 ↓
Domain / Ports
 ↑
Infrastructure
```

More precisely:

```text
┌──────────────┐
│     API      │
└──────┬───────┘
       ↓
┌──────────────┐
│ Application  │
└──────┬───────┘
       ↓
┌──────────────┐
│    Domain    │
└──────────────┘
       ↑
       │ implements interfaces
┌──────────────┐
│Infrastructure│
└──────────────┘
```

Infrastructure may depend on domain/application interfaces.

Domain must NOT depend on infrastructure.

---

# 23. Circular Dependency Rule

Circular dependencies are prohibited.

If:

```text
A → B
B → A
```

appears necessary, stop and reconsider the design.

Possible solutions:

* introduce an interface
* move shared concepts to a lower layer
* split responsibilities
* redesign the dependency

Do not solve circular dependencies with import hacks.

---

# 24. File Size Rule

There is no magical maximum line count.

However, a file should be reconsidered when it begins to contain multiple unrelated responsibilities.

Warning signs:

* many unrelated classes
* many unrelated functions
* difficult navigation
* excessive imports
* multiple reasons to change the same file

Prefer cohesive files over arbitrary fragmentation.

---

# 25. Naming Conventions

Python:

* modules/files: `snake_case.py`
* functions: `snake_case`
* variables: `snake_case`
* classes: `PascalCase`
* constants: `UPPER_SNAKE_CASE`

Use names that communicate responsibility.

Prefer:

```text
inference_adapter.py
```

over:

```text
utils2.py
```

Avoid vague names such as:

```text
helpers.py
misc.py
common.py
stuff.py
manager.py
```

unless their responsibility is genuinely clear.

---

# 26. `utils` Rule

Do not create a generic `utils.py` as a dumping ground.

If a helper belongs to a specific responsibility, keep it near that responsibility.

For example:

```text
application/chat/prompt_builder.py
```

is preferable to:

```text
utils/prompt.py
```

when prompt construction is part of chat behavior.

---

# 27. No Premature Abstraction

Do not create:

```text
BaseRepository
AbstractService
GenericManager
UniversalAdapter
BaseModelFactory
```

unless there is a real repeated behavior or requirement that justifies it.

Abstractions must solve an observed problem.

---

# 28. No Premature Files

The architecture document describes possible future structure.

It does NOT mean OpenCode should immediately create every directory and placeholder file.

Implementation should proceed incrementally.

Example:

If we are implementing the health endpoint, create only the files genuinely required for that feature.

Do not create ten empty modules because the architecture diagram contains ten concepts.

---

# 29. One-File-at-a-Time Implementation

OpenCode must follow:

```text
1. Inspect repository
2. Identify target file
3. Explain purpose
4. Show proposed change
5. Ask for approval
6. Modify ONE file
7. Run relevant validation
8. Report result
9. Wait
10. Continue
```

If a feature genuinely requires multiple files, OpenCode should explain the dependency order and still request approval before each file by default.

---

# 30. Command Safety

Before executing a meaningful command, OpenCode must show:

```text
Command:
<exact command>

Purpose:
<why>

Expected side effects:
<effects>

Risk:
<low/medium/high>

Proceed?
```

Examples requiring explicit approval:

* package installation
* migrations
* file deletion
* permission changes
* Git operations
* process termination
* model downloads
* network-facing configuration

Read-only commands may be executed when they are necessary for inspection, but the agent should still explain important commands when they affect the workflow.

---

# 31. Architecture Ownership

OpenCode implements the architecture.

It does not independently redefine the architecture.

If OpenCode believes a requirement requires a structural change, it must stop and explain:

```text
Current architecture:
...

Problem:
...

Proposed change:
...

Why:
...

Trade-offs:
...

Security implications:
...

Approval required.
```

The developer remains the final decision-maker.

---

# 32. Definition of Structural Completion

The project structure is considered correct when:

* responsibilities are obvious
* dependencies have a clear direction
* API code is thin
* application logic is isolated
* infrastructure is replaceable where useful
* tests can target individual boundaries
* no generic dumping-ground modules exist
* no unnecessary placeholder files exist
* OpenCode can identify where a new feature belongs without guessing

---

# 33. Final Principle

The folder structure should tell the story of the system.

A developer should be able to look at:

```text
api/
application/
domain/
infrastructure/
```

and immediately understand:

> How a request enters RUACH, where the intelligence is coordinated, what the core concepts are, and where external/runtime dependencies live.

Structure is not decoration.

> **Architecture is expressed through boundaries, and boundaries are enforced through code organization.**

```

