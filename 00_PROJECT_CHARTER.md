# RUACH — Project Charter

## 1. Project Identity

**Project:** RUACH
**Type:** Local-first, offline AI platform
**Primary Runtime:** Android + Termux
**Client:** Browser / PWA
**Backend:** Python + FastAPI
**AI Runtime:** Local inference engine + local LLM
**Storage:** SQLite
**Status:** Architecture / implementation preparation

RUACH is a private AI system designed to run locally on an Android device through Termux.

The browser is the user-facing client. The backend, orchestration layer, model runtime, tools, memory, and application data run locally on the same device.

The core promise is:

> **Private local intelligence, running on your own device.**

---

## 2. Vision

RUACH should become a serious local AI environment rather than a simple chatbot.

The initial implementation must establish a clean foundation that can later support:

* conversational AI
* local model inference
* conversation memory
* controlled local tools
* filesystem awareness
* shell/tool execution
* project analysis
* developer assistance
* extensible AI agents

The MVP must remain intentionally small.

We optimize for:

1. Correctness
2. Security
3. Learnability
4. Maintainability
5. Clear architecture
6. Local-first operation

Feature quantity is secondary.

---

## 3. Non-Goals for the Initial MVP

The MVP will NOT attempt to become:

* a cloud AI platform
* a multi-user SaaS application
* a Kubernetes deployment
* a distributed system
* an internet-facing API
* a replacement for a full operating system
* an unrestricted autonomous shell agent

Do not introduce infrastructure merely because it is common in cloud architectures.

Every component must have a concrete reason to exist on a single Android device.

---

## 4. Core Architectural Principle

RUACH is **localhost-first**.

The primary request lifecycle is:

```text
User
  ↓
Browser / PWA
  ↓
localhost HTTP / WebSocket
  ↓
FastAPI
  ↓
AI Orchestrator
  ├── SQLite
  ├── Local Inference Engine
  │      ↓
  │   Local LLM
  └── Tool Engine
         ↓
      Termux / Android OS
  ↓
AI Orchestrator
  ↓
FastAPI
  ↓
Browser
```

The browser is the client.

Termux is the local runtime environment.

Termux is NOT the origin of a user's browser request.

---

## 5. Engineering Principles

### 5.1 Security First

Security is a design constraint, not a later feature.

Before implementing a capability, answer:

* What can this component access?
* What can an attacker control?
* What happens if the AI makes a malicious or incorrect decision?
* What permissions are required?
* Can the capability be restricted?
* What is the safest default?

Dangerous operations must require explicit user approval.

RUACH must never silently execute destructive or high-impact commands.

---

### 5.2 Human Approval for Sensitive Actions

Any operation capable of changing the user's environment must be treated as potentially sensitive.

Examples:

* shell commands
* file deletion
* file modification
* package installation
* git operations that modify state
* network operations
* process termination

The system should distinguish between:

**Read-only actions**

and

**Mutating actions**

The default behavior should be conservative.

Before executing a sensitive action, RUACH should present the proposed action and require explicit approval.

Example:

```text
RUACH wants to execute:

rm -rf ./build

Reason:
Clean generated build artifacts.

[Approve] [Reject]
```

The AI must not be treated as inherently trustworthy.

---

### 5.3 Explainability

Important actions should be understandable to the user.

The system should expose:

* what action is being requested
* why it is being requested
* what tool will execute it
* what scope it affects
* whether the action is read-only or mutating

We prefer explicit behavior over hidden magic.

---

### 5.4 Clean Code

Code should be:

* small
* readable
* cohesive
* testable
* explicit
* typed where appropriate
* documented when behavior is non-obvious

Avoid:

* giant files
* hidden global state
* unnecessary abstractions
* premature frameworks
* duplicated business logic
* magic behavior
* speculative features

---

### 5.5 Smart Architecture

Architecture must follow actual requirements.

Do not add a technology because it looks sophisticated.

For every dependency ask:

> What problem does this solve?

For every abstraction ask:

> Why does this abstraction exist?

For every service ask:

> Does this need to be a separate service?

For the MVP, prefer a modular monolith over distributed architecture.

---

### 5.6 Learnability

RUACH is also a learning project.

Implementation decisions must be understandable to the developer.

The AI coding agent must not silently make large architectural decisions.

When a design decision is non-trivial, explain:

1. The problem
2. The available options
3. The chosen option
4. Why it was chosen
5. The trade-offs

---

## 6. Controlled AI Coding Workflow

OpenCode is the implementation agent.

However, OpenCode must operate as an engineering assistant, not as an autonomous code generator.

### Rule 1 — Inspect Before Changing

Before modifying a file:

1. Inspect the relevant repository structure.
2. Read the relevant existing code.
3. Identify dependencies.
4. Explain the intended change.

Never blindly overwrite files.

### Rule 2 — One File at a Time

Default workflow:

```text
Inspect
  ↓
Explain
  ↓
Propose change
  ↓
Ask for approval
  ↓
Modify ONE file
  ↓
Run relevant validation
  ↓
Show result
  ↓
Wait for approval
  ↓
Continue
```

Do not modify multiple files in one step unless the user explicitly approves a multi-file change.

### Rule 3 — Commands Require Approval

Before executing a command that can modify the system, install dependencies, delete files, migrate data, or otherwise create meaningful side effects:

1. Show the exact command.
2. Explain what it does.
3. Explain potential side effects.
4. Ask for approval.

Example:

```text
I want to run:

python -m pytest tests/

Purpose:
Run the test suite.

Side effects:
None expected; read-only.

Proceed? [yes/no]
```

For destructive commands, approval is mandatory.

### Rule 4 — No Silent Dependency Installation

Never install packages automatically.

Propose:

```text
python -m pip install fastapi
```

Explain why it is needed and wait for approval.

### Rule 5 — No Silent Git Operations

Do not automatically:

* commit
* push
* reset
* checkout
* rebase
* delete branches

Show the command and ask first.

### Rule 6 — Explain Unknown Code

If OpenCode encounters code that is difficult to understand or potentially important, stop and explain it rather than guessing.

---

## 7. Definition of Done

A feature is not complete merely because the code runs.

A feature is complete when:

* implementation exists
* architecture remains coherent
* security considerations are addressed
* relevant tests exist
* validation passes
* errors are handled intentionally
* documentation is updated when necessary
* the developer understands the implementation

---

## 8. MVP Philosophy

Build the smallest complete vertical slice first.

The first milestone should eventually allow:

```text
Browser
   ↓
FastAPI
   ↓
AI Orchestrator
   ↓
Local LLM
   ↓
Response
   ↓
Browser
```

Only after that works reliably should we introduce:

* SQLite memory
* tool engine
* controlled shell access
* filesystem tools
* project intelligence
* advanced agent behavior

Do not build the entire platform before validating the core loop.

---

## 9. Engineering Gate

Before moving to the next implementation phase, verify:

* Is the current behavior correct?
* Is the security model understood?
* Are permissions minimal?
* Are tests present?
* Does the developer understand the code?
* Are we adding complexity for a real reason?

If any answer is unclear, stop and resolve it before continuing.

---

## 10. Final Principle

RUACH should be built deliberately.

The objective is not:

> "Make an AI agent as fast as possible."

The objective is:

> **Build a secure, understandable, well-architected local AI system while learning how every important part works.**

No vibe coding.

No blind commands.

No unexplained abstractions.

No unnecessary infrastructure.

**Design → Understand → Approve → Implement → Test → Review → Continue.**
