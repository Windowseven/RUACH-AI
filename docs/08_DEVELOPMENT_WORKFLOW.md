# RUACH — Development Workflow

**Document:** `08_DEVELOPMENT_WORKFLOW.md`  
**Version:** 0.1  
**Status:** Draft for approval  
**Scope:** RUACH MVP

---

# 1. Purpose

This document defines how RUACH MVP is developed.

The goal is to ensure that development remains:

- deliberate
- reproducible
- test-driven where practical
- secure
- reviewable
- understandable
- compatible with Termux
- resistant to uncontrolled AI-generated changes

RUACH is being built as a learning project as well as a functional system.

Therefore:

> The development process must optimize for understanding, not merely speed.

---

# 2. Core Development Principle

RUACH must not be developed through uncontrolled vibe-coding.

The preferred workflow is:

```text
Requirement
    ↓
Design
    ↓
Decision
    ↓
Implementation
    ↓
Test
    ↓
Review
    ↓
Integration
```

No stage may be skipped for convenience.

Each stage produces a reviewable result that the next stage depends on.

---

# 3. Development Lifecycle Stages

## 3.1 Requirement

Work begins from a requirement in `01_REQUIREMENTS.md`.

Every unit of work traces to an identifier:

```text
FR-xxx   Functional requirement
SR-xxx   Security requirement
NFR-xxx  Non-functional requirement
```

Work without a traceable requirement does not begin.

If a needed requirement does not exist, it is discussed and added first.

## 3.2 Design

Before implementation, the approach is stated:

```text
which files are affected
which architecture boundaries apply
which existing components are reused
```

Design stays within the structure defined in `03_PROJECT_STRUCTURE.md`.

## 3.3 Decision

Where alternatives exist, one is chosen explicitly.

Ambiguity is resolved before code is written.

Decisions that change documented behavior update the relevant document.

## 3.4 Implementation

Implementation proceeds incrementally:

```text
one file at a time
smallest complete increment first
no speculative code
follow naming conventions from 03_PROJECT_STRUCTURE.md
```

## 3.5 Test

Behavior is verified automatically where practical.

Security-relevant behavior requires explicit negative tests:

```text
denied operations
expired approvals
invalid input
unauthorized paths
```

## 3.6 Review

Every change is reviewed by the human owner before integration.

Review checks:

```text
correctness
requirement traceability
architecture conformance
security implications
test coverage
```

## 3.7 Integration

Code integrates only after review passes.

Git operations are never performed unless explicitly requested.

---

# 4. Traceability Rule

Every change maps to:

```text
a requirement ID, or
an explicitly approved decision
```

Unrequested features are not added while implementing a requirement.

Improvement ideas discovered during work are noted, not silently implemented.

---

# 5. One File At A Time

Files are created or modified one at a time.

A file is fully understood before the next file is touched.

Bulk generation of entire directory trees is prohibited.

The repository grows only as fast as understanding grows.

---

# 6. Rules for AI Coding Agents

When OpenCode (or any AI coding agent) performs implementation work, it must:

1. Read the relevant specification documents before writing code.
2. State which requirement the work traces to.
3. Propose file changes before making them for non-trivial work.
4. Introduce no dependency without explicit approval.
5. Never use technologies on the prohibited list in `04_TECH_STACK.md`.
6. Perform no git commit, push, or branch operation unless explicitly requested.
7. Modify no unrelated files opportunistically.
8. Run tests, lint, and type checks before claiming completion.
9. Report limitations and assumptions honestly.
10. Ask when uncertain rather than guessing.
11. Present all state-changing commands and file contents to the owner with explanations before executing them.

---

# 7. Testing Discipline

Tests accompany behavior. A feature without tests is not complete.

Rules:

```text
tests live in backend/tests/ mirroring app structure
test observable behavior, not internal trivia
failure paths are tested, not only success paths
security controls always have deny-path tests
failing tests are never skipped or deleted silently
```

pytest is the test framework.

---

# 8. Quality Gates

Work does not integrate until all gates pass:

```text
[ ] pytest suite passes
[ ] black formatting clean
[ ] ruff lint clean
[ ] mypy type check clean
[ ] relevant acceptance criteria from 01_REQUIREMENTS.md met
[ ] security invariants from 05_SECURITY_ARCHITECTURE.md respected
[ ] diff contains no unrelated changes
```

Anything touching tools, filesystem access, network access,
policy evaluation, or approval flow requires an explicit security
review against `05_SECURITY_ARCHITECTURE.md`.

---

# 9. Definition of Done

A unit of work is done when:

```text
behavior implemented
tests written and passing
quality gates green
documentation updated if decisions changed
requirement traceability recorded
reviewed and approved by the human owner
```

"Works on my machine" is not a completion state.

---

# 10. Documentation Duty

Documentation is part of the system.

If implementation and documentation disagree, one of them is wrong.

The mismatch is flagged and reconciled in the same cycle — either the code changes or the document changes.

Stale documentation is treated as a defect.

---

# 11. Change Discipline

Preferred change size:

```text
small
single-purpose
reviewable in one sitting
```

Large changes are decomposed into sequences of small ones.

Unrelated improvements are noted, not applied.

---

# 12. Workflow Invariants

Unless explicitly changed through an approved decision:

1. No code without a traceable requirement.
2. No skipped lifecycle stages.
3. One file at a time during creation phases.
4. No silent dependencies.
5. No unrequested git operations.
6. No integration without human review.
7. No security-sensitive change without explicit security review.
8. Failing tests block progress.
9. Understanding outranks speed.
10. When ambiguous, ask rather than assume.