# RUACH — Technology Stack

**Document:** 04_TECH_STACK.md  
**Version:** 0.1  
**Status:** Draft for approval  
**Scope:** RUACH MVP

---

# 1. Purpose

This document defines the technologies used to build RUACH MVP.

Technology choices must be:

- intentional
- lightweight
- compatible with Termux/Android
- secure
- maintainable
- easy to understand
- suitable for offline/local execution

Popularity alone is not a valid reason for introducing a dependency.

---

# 2. Technology Selection Principles

Every technology must satisfy at least one meaningful requirement.

Before adding a dependency, ask:

1. What problem does it solve?
2. Can the standard library solve the problem?
3. Does it work reliably on Termux/Android?
4. What is its maintenance cost?
5. Does it increase attack surface?
6. Does it increase resource consumption?
7. Does it improve testability?
8. Can the developer understand the technology well enough to maintain it?

If the answer is unclear:

> Do not add the dependency yet.

---

# 3. High-Level Stack

RUACH MVP uses:

```text
┌─────────────────────────────────────┐
│             Browser / PWA           │
│       HTML / CSS / TypeScript       │
└──────────────────┬──────────────────┘
                   │
                   │ HTTP / WebSocket
                   ▼
┌─────────────────────────────────────┐
│              FastAPI                │
│              Python                 │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│        Application / Orchestrator   │
│              Python                 │
└──────────────┬───────────────┬──────┘
               │               │
               ▼               ▼
        ┌────────────┐   ┌───────────────┐
        │   SQLite   │   │ Local Inference│
        └────────────┘   └───────┬───────┘
                                  │
                                  ▼
                            ┌───────────┐
                            │ Local LLM │
                            └───────────┘
4. Backend Language
Decision

Use:

Python 3.12+

Python is the primary backend language.

Why Python?

Python is appropriate because RUACH involves:

AI/LLM integration
inference orchestration
local model tooling
API development
data processing
experimentation
automation

Python also provides a mature ecosystem for AI-related development.

Constraint

Python must not become an excuse for excessive dependencies.

Prefer:

Python standard library

where the problem is simple enough.

5. API Framework
Decision

Use:

FastAPI

FastAPI is the HTTP/API boundary for RUACH.

Responsibilities include:

routing
request validation
response serialization
WebSocket support
API documentation
dependency injection
6. Why FastAPI?

FastAPI is selected because it provides:

strong type-based request validation
Pydantic integration
async support
automatic API documentation
good Python ecosystem compatibility
simple development workflow

The API layer must remain thin.

FastAPI should not contain core AI orchestration logic.

7. Data Validation
Decision

Use:

Pydantic

Pydantic is responsible primarily for:

API request validation
API response models
configuration validation
structured data validation

Example:

Browser
   ↓
HTTP JSON
   ↓
Pydantic
   ↓
Validated Application Input
8. ORM / Database Access
Decision

Use:

SQLAlchemy 2.x

with SQLite for the MVP.

SQLAlchemy provides:

database abstraction
explicit queries
transaction management
testability
future migration flexibility
9. Database
Decision

Use:

SQLite

SQLite is the primary persistence layer for RUACH MVP.

Why SQLite?

RUACH is:

local-first
initially single-user
designed for Termux
offline-oriented
resource constrained

SQLite provides:

no separate database server
local persistence
transactional guarantees
low resource usage
simple backup
mature ecosystem
10. Migration Tool
Decision

Use:

Alembic

for database schema migrations.

Even though SQLite is simple, schema changes must remain explicit and reproducible.

Migration files should be version-controlled.

Do not modify production schema manually without a documented migration.

11. Local Inference Runtime
Decision

RUACH will use a local inference runtime behind an adapter boundary.

The application must NOT directly depend on a specific runtime throughout the codebase.

Architecture:

Orchestrator
      ↓
InferencePort
      ↓
LocalInferenceAdapter
      ↓
Inference Runtime
      ↓
Local Model
12. Runtime Selection Rule

The exact inference runtime is intentionally treated as an infrastructure decision.

Candidate runtimes may include:

llama.cpp
Ollama
llama-cpp-python
other Termux-compatible local runtimes

The final runtime must be selected based on:

Android/Termux compatibility
CPU architecture
memory requirements
model format
inference speed
installation complexity
Python compatibility
streaming support
maintenance burden

No runtime should be added to the application layer directly.

13. Model Format

The architecture should prefer model formats that can run efficiently on local hardware.

A likely target is:

GGUF

because of its compatibility with common lightweight local inference runtimes.

The exact model is a separate decision.

Model selection must consider:

parameter count
quantization
RAM requirements
context length
response quality
inference speed
device capabilities
14. Frontend
Decision

Use a lightweight web frontend.

The frontend must be accessible through the local browser.

The frontend communicates with FastAPI using:

HTTP

and eventually:

WebSocket / streaming

where justified.

15. Frontend Technology

The initial frontend stack should be:

TypeScript
HTML
CSS

A framework may be introduced if the UI complexity justifies it.

The project must not introduce a frontend framework merely because modern projects commonly use one.

If a framework is selected later, the decision must be documented.

16. Frontend Principle

The frontend is a client.

It does not own backend intelligence.

It must never directly access:

SQLite
local model files
Termux shell
backend filesystem
Python modules

Communication:

Frontend
   ↓
API Contract
   ↓
FastAPI
17. API Documentation

FastAPI's generated OpenAPI documentation will be used during development.

Expected endpoints will be documented through the API contract.

Development tools may include:

Swagger UI
ReDoc

These are development aids, not separate runtime architecture components.

18. Testing
Decision

Use:

pytest

for backend tests.

Testing levels:

Unit
Integration
API

Tests must be written around behavior and boundaries.

19. Async Testing

Where asynchronous application code exists, use appropriate pytest async tooling.

Do not introduce asynchronous programming everywhere merely because FastAPI supports it.

Use async when it provides a meaningful benefit.

20. Code Formatting
Decision

Use:

Black

for Python formatting.

Formatting should be automated rather than manually negotiated.

21. Linting
Decision

Use:

Ruff

for Python linting.

Ruff should enforce useful correctness and style rules.

Do not enable hundreds of rules blindly.

Rules should support maintainability rather than generate noise.

22. Type Checking
Decision

Use:

MyPy

where practical.

Type checking should be introduced progressively.

The objective is:

explicit interfaces
+
clear data flow
+
fewer runtime surprises

not maximum type complexity.

23. Dependency Management

The project must use a reproducible Python dependency workflow.

The exact package/dependency manager may be selected during environment setup based on Termux compatibility.

Regardless of the manager:

dependencies must be explicitly declared
versions must be controlled
unnecessary packages must not be added
development dependencies must be distinguishable from runtime dependencies
24. Environment Configuration

Use environment variables/configuration files for environment-specific values.

Example:

RUACH_HOST
RUACH_PORT
RUACH_DATABASE_PATH
RUACH_MODEL_PATH
RUACH_MODEL_RUNTIME
RUACH_LOG_LEVEL

Do not commit secrets.

Provide:

.env.example

when environment configuration requires it.

25. Logging

Use Python's standard logging facilities initially.

Do not introduce a third-party logging framework unless requirements justify it.

Logging should support:

startup diagnostics
request lifecycle diagnostics
inference failures
database failures
security events
tool approval events

Never log:

API secrets
authentication tokens
sensitive user content unnecessarily
raw credentials
private filesystem data
26. HTTP Client

If RUACH needs outbound HTTP requests in future components, choose a dedicated client only when required.

Candidate:

httpx

However:

HTTPX is not an MVP dependency until an actual outbound HTTP requirement exists.

Do not install it preemptively.

27. Serialization

Use standard JSON serialization through FastAPI/Pydantic for API communication.

Do not introduce another serialization format unless a concrete requirement appears.

28. Frontend Build Tool

The frontend build tool must be selected based on the actual frontend architecture.

Potential candidates include:

Vite

if a TypeScript application requires bundling.

However:

Tooling should follow frontend complexity.

A simple static frontend should not require an unnecessarily complicated build system.

29. Git

Use:

Git

for version control.

The repository must contain:

.gitignore

that excludes:

virtual environments
local model files
database files where appropriate
environment secrets
generated build artifacts
caches
logs
30. Local Model Files

Model weights must NOT be committed to Git.

For example:

*.gguf

should normally be excluded.

Models should live outside source control.

31. Security Principle for Dependencies

Every dependency increases:

complexity
+
attack surface
+
maintenance cost

Therefore:

Dependency count is a design concern.

Before adding a package:

Problem
   ↓
Can stdlib solve it?
   ↓
Can existing dependency solve it?
   ↓
Is package maintained?
   ↓
Is package compatible with Termux?
   ↓
Is security impact acceptable?
   ↓
Approve dependency
32. Technology Decision Record

Every major technology change must be documented.

Example:

Decision:
Replace Runtime A with Runtime B

Reason:
Runtime A does not perform adequately on target Android hardware.

Impact:
Inference adapter changes.

Security impact:
Review local process permissions.

Migration:
...

Approval:
Required.
33. Prohibited Technology Decisions

The following must NOT be introduced into MVP without an explicit architectural decision:

Redis
Kafka
RabbitMQ
Docker
Kubernetes
Microservices
PostgreSQL
Cloud LLM APIs
External authentication services
External vector databases
Cloud object storage

This does not mean they are bad technologies.

It means they are not justified by current MVP requirements.

34. Cloud Independence

Core RUACH operation must not require:

OpenAI
Anthropic
Gemini
OpenRouter
cloud database
cloud authentication
cloud storage

The core experience should remain local.

Optional integrations may exist later.

35. Offline Requirement

The following should work without internet access once dependencies and model files have been installed:

Start RUACH
      ↓
Open browser
      ↓
Send prompt
      ↓
Local inference
      ↓
Receive response

Network access must not be a requirement for core inference.

36. Termux Compatibility

All selected runtime dependencies must be evaluated against the actual target environment.

Target:

Android
   ↓
Termux
   ↓
Python runtime

Do not assume that a package supporting desktop Linux automatically works on Android/Termux.

Installation must be tested on the real target environment.

37. Resource Awareness

RUACH must respect mobile hardware constraints.

Important resources:

RAM
CPU
storage
battery
thermal limits

Avoid:

unnecessary background workers
excessive processes
memory-heavy caches
large default context windows
unnecessary model duplication
38. Architecture vs Technology

Technology choices must not dictate architecture.

Correct:

Architecture
    ↓
Interface
    ↓
Technology implementation

Incorrect:

Library
    ↓
Architecture

Example:

The Orchestrator should depend on an inference interface.

It should not depend directly on a specific LLM library.

39. MVP Technology Summary
Area	Technology
Backend	Python 3.12+
API	FastAPI
Validation	Pydantic
Database	SQLite
ORM/Data Access	SQLAlchemy 2.x
Migrations	Alembic
Testing	pytest
Formatting	Black
Linting	Ruff
Type Checking	MyPy
Logging	Python standard logging
Frontend	TypeScript + HTML + CSS
API Documentation	OpenAPI / FastAPI
Version Control	Git
Inference	Local runtime behind adapter
Model	Local model, likely GGUF
Deployment	Termux / localhost
40. Technology Selection Invariants

Unless explicitly changed through an architecture decision:

Python remains the backend language.
FastAPI remains the API boundary.
SQLite remains the MVP database.
Core inference remains local.
The inference runtime remains behind an adapter.
The API defaults to localhost.
Cloud services are not required for core operation.
Model weights are not stored in Git.
Dependencies must be justified.
Termux compatibility must be tested on the actual target device.
41. Final Principle

RUACH is not a technology showcase.

We are not trying to use every modern tool.

We are building a system that is:

Local
Secure
Understandable
Testable
Efficient
Maintainable
Extensible

The best technology is not the most sophisticated technology.

The best technology is the simplest technology that satisfies the requirement without creating unnecessary risk or complexity.


