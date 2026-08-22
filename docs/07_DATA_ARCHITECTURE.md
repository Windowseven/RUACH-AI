# RUACH — Data Architecture

**Document:** `07_DATA_ARCHITECTURE.md`
**Version:** 0.1
**Status:** Draft for approval
**Scope:** RUACH MVP

---

# 1. Purpose

This document defines how RUACH MVP stores, organizes, accesses, protects, and manages persistent data.

RUACH is local-first.

Therefore, the data architecture must prioritize:

* simplicity
* reliability
* transactional integrity
* local persistence
* offline operation
* recoverability
* privacy
* maintainability
* low resource usage

The primary database is:

```text
SQLite
```

The database is accessed through:

```text
SQLAlchemy 2.x
```

and schema changes are managed through:

```text
Alembic
```

---

# 2. Data Architecture Principles

RUACH follows these principles:

1. SQLite is the source of truth for persistent application state.
2. Database access occurs through the application/data layer.
3. The frontend never accesses SQLite directly.
4. The LLM never accesses SQLite directly.
5. Tools must not bypass application-level data rules.
6. Schema changes require migrations.
7. Sensitive data must be minimized.
8. Large binary/model files must not be stored inside SQLite unnecessarily.
9. Database transactions must preserve consistency.
10. Data deletion must be intentional and predictable.

---

# 3. High-Level Data Flow

```text
┌─────────────────────┐
│      Frontend       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│      FastAPI        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Application Layer   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Repository / Data   │
│      Access         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│       SQLite        │
└─────────────────────┘
```

The LLM and Tool Engine interact with application services rather than directly with database internals.

---

# 4. Database Location

The database location must be configurable.

Example:

```text
RUACH_DATABASE_PATH
```

A typical local installation may use a path similar to:

```text
$HOME/.ruach/data/ruach.db
```

The exact installation path is an implementation decision.

The database should not live inside arbitrary source-code directories by default.

---

# 5. Database File

MVP uses a single SQLite database.

Conceptually:

```text
ruach.db
```

SQLite auxiliary files may also exist depending on the journal configuration.

These files must be treated as part of the database lifecycle.

---

# 6. SQLite Configuration

The application should configure SQLite deliberately.

Where appropriate, the database should use:

```text
foreign_keys = ON
```

Foreign-key enforcement must not depend on developer assumptions.

The application should also use an appropriate transaction/journal configuration for the target environment.

---

# 7. WAL Consideration

SQLite Write-Ahead Logging may be used if it provides better concurrent read/write behavior for the RUACH workload.

Conceptually:

```text
journal_mode = WAL
```

However, WAL must be tested on the actual Termux/Android environment before becoming a hard requirement.

The architecture should not assume desktop SQLite behavior is identical on every mobile environment.

---

# 8. Core Data Domains

RUACH MVP data can be divided into these domains:

```text
Conversation
Message
Tool Request
Tool Approval
Tool Execution
Audit Event
Application Settings
```

Potential future domains include:

```text
Memory
Workspace
Model Configuration
Scheduled Task
User Profile
Plugin
```

Future domains must not be introduced until justified.

---

# 9. Entity Relationship Overview

Conceptually:

```text
Conversation
     │
     └──────< Message
                 │
                 │
                 └────── Tool Request
                              │
                              ├──── Tool Approval
                              │
                              └──── Tool Execution
                                       │
                                       └──── Audit Event
```

This represents the logical relationship between user interaction and privileged operations.

---

# 10. Conversation

A conversation represents a persistent user interaction session.

Conceptual fields:

```text
id
title
created_at
updated_at
```

Example:

```json
{
  "id": "conv_123",
  "title": "Python debugging",
  "created_at": "...",
  "updated_at": "..."
}
```

---

# 11. Conversation ID

Conversation IDs must be unique.

UUIDs are a suitable default.

Example:

```text
550e8400-e29b-41d4-a716-446655440000
```

The exact identifier format is an implementation detail, but IDs must not rely on sequential user-visible integers where unnecessary.

---

# 12. Message

A message belongs to a conversation.

Conceptual fields:

```text
id
conversation_id
role
content
created_at
```

Relationships:

```text
Conversation
     │
     └──────< Message
```

Deleting a conversation should define what happens to its messages.

For MVP:

> Messages should normally be deleted with their parent conversation.

---

# 13. Message Roles

MVP should recognize explicit roles.

```text
user
assistant
system
tool
```

However, not every role is necessarily rendered directly in the frontend.

Internal/system messages should remain controlled by the application.

---

# 14. Message Content

Message content is primarily text.

The database should not store model hidden chain-of-thought.

Store:

```text
user-visible content
necessary structured metadata
```

Do not store:

```text
private chain-of-thought
unnecessary intermediate reasoning
secrets
raw environment contents
```

---

# 15. Message Metadata

If additional metadata is required, use a structured field rather than continually adding columns for temporary attributes.

Potential metadata:

```text
model identifier
latency
token counts if available
streaming state
client information where justified
```

Metadata must not contain secrets unnecessarily.

---

# 16. Tool Request

A Tool Request represents an operation proposed by the orchestrator/model.

Conceptual fields:

```text
id
conversation_id
message_id
tool_name
arguments
risk_level
status
created_at
```

Important:

> A tool request is a request to perform an action, not evidence that the action was executed.

---

# 17. Tool Request Status

Possible statuses:

```text
pending
approved
rejected
executing
completed
failed
denied
expired
```

State transitions must be controlled.

Example:

```text
pending
   ↓
approved
   ↓
executing
   ↓
completed
```

Or:

```text
pending
   ↓
rejected
```

---

# 18. Tool Approval

An approval represents an explicit authorization decision by the user.

Conceptual fields:

```text
id
tool_request_id
decision
created_at
expires_at
```

Possible decisions:

```text
approved
rejected
```

The approval must be associated with one specific Tool Request.

---

# 19. Approval Security

Approval records must not be used as general permissions.

Incorrect:

```text
User approved one delete operation
        ↓
All future deletes automatically approved
```

Correct:

```text
Approval
    ↓
Specific Tool Request
    ↓
Specific arguments
    ↓
Specific operation
```

Approval is not a permanent capability grant.

---

# 20. Tool Execution

A Tool Execution represents an actual attempt to execute a tool.

Conceptual fields:

```text
id
tool_request_id
started_at
completed_at
status
exit_code
duration_ms
output_summary
error_code
```

Not every raw tool output should necessarily be stored.

---

# 21. Execution vs Request

These are intentionally separate concepts.

```text
Tool Request
    =
"What should happen?"
```

```text
Tool Execution
    =
"What actually happened?"
```

This distinction is important for auditing.

Example:

```text
Tool Request:
filesystem.delete("test.txt")

Execution:
status = failed
reason = file not found
```

The request existed, but the destructive action did not occur.

---

# 22. Audit Event

An Audit Event records security-relevant system activity.

Examples:

```text
tool_requested
tool_allowed
tool_denied
approval_requested
approval_granted
approval_rejected
tool_started
tool_completed
tool_failed
path_blocked
security_violation
```

Conceptual fields:

```text
id
event_type
request_id
tool_request_id
timestamp
metadata
```

---

# 23. Audit Data Minimization

Audit logs must provide enough information for investigation without becoming a copy of all user data.

Prefer:

```text
tool
risk level
status
target classification
request ID
timestamp
result
```

Avoid unnecessarily storing:

```text
passwords
tokens
private keys
full documents
complete secrets
```

---

# 24. Request Correlation

Important records should be traceable.

Conceptually:

```text
request_id
     │
     ├── Message
     ├── Tool Request
     ├── Tool Approval
     ├── Tool Execution
     └── Audit Event
```

This makes debugging and security investigation easier.

---

# 25. Settings

Application settings may be stored in SQLite when persistence is useful.

Examples:

```text
theme
model selection
workspace configuration
UI preferences
inference configuration
```

Security-sensitive secrets should not automatically be stored as plain database values.

---

# 26. Secrets and Database Storage

SQLite is local, but local does not mean automatically secure.

Do not assume:

```text
SQLite
=
secure secret storage
```

Secrets should be avoided where possible.

If persistent credentials are eventually required, a dedicated secret-storage strategy must be introduced through an explicit security decision.

---

# 27. Model Configuration

Model configuration may be represented as application configuration rather than database records.

Possible fields:

```text
runtime
model_path
context_length
temperature
max_tokens
```

Model weights themselves must not be stored inside SQLite.

---

# 28. Binary Data

Large binary files should not be stored in the SQLite database by default.

Examples:

```text
model weights
large documents
images
videos
archives
```

Instead:

```text
Filesystem
   ↓
Metadata in SQLite
```

The database may store:

```text
path
size
hash
mime_type
created_at
```

when such metadata is required.

---

# 29. Filesystem and Database Consistency

When SQLite references a filesystem resource, consistency becomes a concern.

Example:

```text
SQLite:
document = /workspace/file.txt

Filesystem:
file.txt deleted
```

The application must handle stale references gracefully.

Database records must not be treated as proof that a file physically exists.

---

# 30. Database Access Layer

Application code should not scatter raw SQL throughout the project.

Preferred architecture:

```text
Service
  ↓
Repository / Data Access
  ↓
SQLAlchemy
  ↓
SQLite
```

This improves:

* testability
* consistency
* transaction management
* maintainability

---

# 31. SQLAlchemy Models

SQLAlchemy models represent persistence structures.

They should not automatically become the API contract.

Avoid exposing ORM objects directly through FastAPI responses.

Instead:

```text
SQLAlchemy Model
       ↓
Application Model / Schema
       ↓
Pydantic Response
```

---

# 32. Pydantic vs SQLAlchemy

These technologies have different responsibilities.

```text
Pydantic
=
validation / API schemas
```

```text
SQLAlchemy
=
database persistence
```

Do not treat them as interchangeable.

---

# 33. Transactions

Database modifications that form one logical operation should use transactions.

Example:

```text
Create Tool Request
        +
Create Audit Event
```

should either:

```text
both succeed
```

or:

```text
both fail
```

where appropriate.

---

# 34. Transaction Boundaries

Transaction boundaries should be defined at the application/service layer rather than randomly inside individual low-level functions.

Conceptually:

```text
Application Operation
        ↓
Transaction
        ↓
Repository operations
        ↓
Commit
```

---

# 35. Concurrency

SQLite supports concurrent reads but has limitations around concurrent writes.

RUACH should therefore avoid unnecessary write contention.

Potential sources include:

```text
chat activity
tool activity
audit logging
settings updates
```

The application should keep write transactions short.

---

# 36. Database Connection Management

Database connections must be managed by the application.

The system should:

* create connections appropriately
* close them appropriately
* avoid connection leaks
* handle transaction rollback
* respect SQLite concurrency characteristics

---

# 37. Database Initialization

Startup should verify:

```text
database path
database accessibility
schema version
required migrations
```

If the schema is incompatible:

```text
fail safely
```

rather than silently modifying the database.

---

# 38. Migrations

Alembic is the authoritative schema migration mechanism.

Every schema change must have a migration.

Example:

```text
Migration 001
    ↓
Migration 002
    ↓
Migration 003
```

Migrations must be version-controlled.

---

# 39. Migration Rules

Never rely on:

```text
"Just modify the table manually."
```

Instead:

```text
Schema change
    ↓
Alembic migration
    ↓
Review
    ↓
Test
    ↓
Apply
```

---

# 40. Migration Testing

Before applying a migration to an important database:

1. Test it against a copy.
2. Verify schema correctness.
3. Verify application compatibility.
4. Verify rollback strategy where supported.
5. Verify data preservation.

---

# 41. Deletion Policy

Data deletion must be explicit.

Potential deletion operations:

```text
delete message
delete conversation
delete tool history
delete audit records
reset database
```

These operations should not be mixed together accidentally.

---

# 42. Conversation Deletion

Deleting a conversation should remove its associated messages.

Related tool records should have a documented lifecycle.

Possible approach:

```text
Conversation deleted
      ↓
Messages deleted
      ↓
Tool requests deleted or retained as audit records
```

The exact policy must preserve security auditing where required.

---

# 43. Audit Retention

Audit records may need longer retention than normal conversation data.

Example:

```text
Conversation:
user may delete

Security audit:
retained according to local policy
```

However, RUACH MVP should avoid unnecessary permanent retention.

The retention policy must balance:

```text
privacy
+
debuggability
+
security
```

---

# 44. Reset / Factory State

RUACH should eventually provide a controlled reset mechanism.

Conceptually:

```text
Reset RUACH
    ↓
Confirm
    ↓
Delete application data
    ↓
Preserve required installation files
```

A reset must not accidentally delete unrelated user files.

---

# 45. Database Backup

SQLite makes local backup relatively simple.

Potential backup mechanism:

```text
RUACH
  ↓
SQLite backup
  ↓
backup file
```

Backups should be created using SQLite-aware mechanisms where possible rather than blindly copying a live database file during writes.

---

# 46. Backup Security

Backups may contain:

```text
conversations
messages
tool history
settings
audit data
```

Therefore backups must be treated as sensitive data.

Do not automatically upload backups to cloud storage.

---

# 47. Recovery

RUACH should eventually support recovery from a valid database backup.

Recovery flow:

```text
Backup
   ↓
Validate
   ↓
Restore
   ↓
Run migrations if required
   ↓
Verify integrity
   ↓
Start application
```

---

# 48. Database Integrity

SQLite integrity checks may be used during diagnostics.

Example concept:

```text
PRAGMA integrity_check;
```

The application may expose database diagnostics to local administration tooling without exposing them to the AI.

---

# 49. Data Validation

Database constraints should enforce important invariants.

Examples:

```text
NOT NULL
UNIQUE
FOREIGN KEY
CHECK
```

Application-level validation and database-level constraints should complement each other.

---

# 50. Foreign Keys

Relationships should use foreign keys where appropriate.

Example:

```text
messages.conversation_id
        ↓
conversations.id
```

Foreign-key enforcement must be enabled.

---

# 51. Cascading Deletes

Cascading deletes should be used carefully.

Suitable:

```text
Conversation
   ↓
Messages
```

Potentially dangerous:

```text
Conversation
   ↓
Audit history
```

Security history should not disappear accidentally because a user deleted a conversation.

---

# 52. Timestamps

Persistent entities should use consistent timestamps.

Recommended:

```text
UTC
```

for stored timestamps.

The UI may convert timestamps to local time for display.

---

# 53. Timestamp Format

Application-level timestamps should use timezone-aware representations.

Example:

```text
2026-08-22T14:30:00Z
```

Avoid ambiguous local timestamps in persistent records.

---

# 54. Identifiers

Internal identifiers should be stable and unique.

UUIDs are preferred for entities that may be exposed through APIs.

Avoid leaking database implementation details through identifiers.

---

# 55. Indexing

Indexes should be introduced where query patterns justify them.

Likely indexes:

```text
messages.conversation_id
messages.created_at
tool_requests.conversation_id
tool_requests.status
tool_approvals.tool_request_id
audit_events.request_id
audit_events.created_at
```

Do not create indexes blindly.

Every index adds storage and write overhead.

---

# 56. Query Design

Queries should retrieve only the data required.

Avoid:

```text
SELECT *
```

when the application only requires a subset of fields.

This becomes especially important when records contain large content fields.

---

# 57. Large Content

Conversation messages and tool outputs can become large.

The application should establish reasonable limits.

Potential controls:

```text
maximum message size
maximum stored tool output
maximum metadata size
maximum API request size
```

---

# 58. Tool Output Storage

Tool outputs may be large.

The system should consider:

```text
store complete output
store truncated output
store summary + reference
```

For MVP:

> Store only the amount of output required for functionality, debugging, and auditability.

Do not turn SQLite into an unlimited command-output archive.

---

# 59. Sensitive Tool Output

Some tools may return sensitive information.

Examples:

```text
environment variables
private files
credential files
process information
```

Such outputs must not automatically be persisted.

The Tool Engine and application layer should classify sensitive results before storage.

---

# 60. Data Ownership

The user owns the local application data.

RUACH should not assume ownership of user files simply because the Tool Engine can access them.

The system should distinguish:

```text
RUACH application data
```

from:

```text
User filesystem data
```

---

# 61. Workspace Metadata

If workspace management is implemented, SQLite may store metadata such as:

```text
workspace id
workspace path
created_at
updated_at
```

The actual workspace files remain on the filesystem.

---

# 62. No Database Access from the LLM

The LLM must never receive unrestricted database access.

Incorrect:

```text
LLM
 ↓
SQL
 ↓
SQLite
```

Correct:

```text
LLM
 ↓
Application capability
 ↓
Validated service
 ↓
Repository
 ↓
SQLite
```

The model should interact with domain capabilities rather than arbitrary SQL.

---

# 63. No Arbitrary SQL Tool

RUACH MVP must not expose:

```text
database.execute_sql(any_string)
```

to the AI.

An arbitrary SQL tool would create unnecessary privilege and security risks.

If database interaction is ever needed, it should use narrowly defined domain tools.

---

# 64. Data Access Permissions

Application services should have clear responsibilities.

Example:

```text
ConversationService
MessageService
ToolService
ApprovalService
AuditService
SettingsService
```

Services should not casually access unrelated data.

---

# 65. Repository Responsibilities

Repositories should focus on persistence operations.

Example:

```text
ConversationRepository
MessageRepository
ToolRequestRepository
ApprovalRepository
AuditRepository
SettingsRepository
```

Business/security decisions belong above the repository layer.

---

# 66. Service Layer

The service layer coordinates business operations.

Example:

```text
ChatService
    ↓
ConversationService
    ↓
MessageRepository
```

and:

```text
ToolService
    ↓
Policy Engine
    ↓
ToolRequestRepository
    ↓
Tool Executor
```

---

# 67. Data and Security Boundary

Database records must not automatically grant permissions.

Example:

```text
tool_request.status = "approved"
```

is meaningful only if the approval was produced by the trusted authorization flow.

The application must not trust arbitrary database mutations.

---

# 68. Data Corruption Handling

If a database record is malformed or inconsistent:

```text
detect
 ↓
log
 ↓
fail safely
```

Do not silently reinterpret corrupted security state as permission.

For example:

```text
Unknown approval state
       ↓
DENY execution
```

---

# 69. Offline Operation

The database must remain fully functional without internet access.

Core persistence operations:

```text
create conversation
store message
retrieve history
store tool activity
store approvals
store audit events
```

must not require cloud services.

---

# 70. Data Export

A future export feature may allow users to export conversations.

Potential formats:

```text
JSON
Markdown
plain text
```

Export must respect privacy and should not automatically include sensitive internal metadata.

---

# 71. Data Import

Importing external conversation/data files should treat them as untrusted input.

Imported content must not:

* execute code
* modify security policy
* create unauthorized approvals
* grant capabilities

Import is data ingestion, not authorization.

---

# 72. Schema Evolution

The database schema will evolve.

The architecture must support:

```text
v1
 ↓
v2
 ↓
v3
```

without requiring users to manually rebuild the database after every application update.

Alembic migrations are responsible for controlled evolution.

---

# 73. MVP Logical Schema

The initial logical schema is:

```text
┌────────────────────┐
│    conversations   │
├────────────────────┤
│ id                 │
│ title              │
│ created_at         │
│ updated_at         │
└─────────┬──────────┘
          │
          │ 1:N
          ▼
┌────────────────────┐
│      messages      │
├────────────────────┤
│ id                 │
│ conversation_id    │
│ role               │
│ content            │
│ created_at         │
└─────────┬──────────┘
          │
          │ 1:N
          ▼
┌────────────────────┐
│   tool_requests    │
├────────────────────┤
│ id                 │
│ message_id         │
│ tool_name          │
│ arguments          │
│ risk_level         │
│ status             │
│ created_at         │
└─────────┬──────────┘
          │
     ┌────┴─────────────┐
     │                  │
     ▼                  ▼
┌───────────────┐  ┌────────────────┐
│ tool_approvals│  │ tool_executions│
├───────────────┤  ├────────────────┤
│ id            │  │ id             │
│ request_id    │  │ request_id     │
│ decision      │  │ status         │
│ created_at    │  │ started_at     │
│ expires_at    │  │ completed_at   │
└───────────────┘  └───────┬────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ audit_events │
                    ├──────────────┤
                    │ id           │
                    │ event_type   │
                    │ request_id   │
                    │ metadata     │
                    │ timestamp    │
                    └──────────────┘
```

This is the initial logical model, not necessarily the final physical schema.

---

# 74. Recommended Initial Tables

MVP should begin with approximately:

```text
conversations
messages
tool_requests
tool_approvals
tool_executions
audit_events
settings
```

Additional tables require justification.

---

# 75. JSON Columns

SQLite may store structured metadata as JSON text.

Potential candidates:

```text
tool_requests.arguments
audit_events.metadata
message.metadata
settings.value
```

JSON fields should not become an excuse for storing the entire relational model inside arbitrary blobs.

Use structured columns when the data is:

* frequently queried
* security-sensitive
* relational
* required for constraints

---

# 76. Normalization Principle

Data should be normalized where relationships matter.

Do not duplicate:

```text
conversation title
user identity
tool definitions
```

through every message or tool execution record unless there is a specific reason.

However, audit records may intentionally snapshot limited information for historical accuracy.

---

# 77. Audit Snapshot Principle

Audit records may store small immutable snapshots.

Example:

```text
tool_name
risk_level
decision
target classification
```

This protects audit interpretation even if configuration changes later.

Do not store unnecessary full request contents.

---

# 78. Data Lifecycle

A typical chat lifecycle:

```text
User message
    ↓
Message stored
    ↓
AI response generated
    ↓
Assistant message stored
    ↓
Tool request created if required
    ↓
Approval created if required
    ↓
Execution recorded
    ↓
Audit event recorded
```

---

# 79. Data Lifecycle on Failure

If inference fails:

```text
User message
    ↓
stored
    ↓
Inference failure
    ↓
error state recorded
```

The system should not pretend an assistant response exists if generation failed.

---

# 80. Tool Failure Lifecycle

If a tool fails:

```text
Tool Request
    ↓
Execution started
    ↓
Execution failed
    ↓
Failure recorded
    ↓
Audit event
```

The Tool Request must not be marked `completed` simply because execution was attempted.

---

# 81. Approval Expiration

Pending approvals should not remain valid forever.

Possible field:

```text
expires_at
```

If expired:

```text
pending
   ↓
expired
```

An expired approval must not authorize execution.

---

# 82. Database Security Invariants

Unless explicitly changed:

1. SQLite remains the MVP persistence layer.
2. Frontend cannot access SQLite directly.
3. LLM cannot access SQLite directly.
4. Arbitrary SQL is not exposed as an AI capability.
5. Foreign keys are enabled.
6. Schema changes use Alembic.
7. Database writes use controlled transactions.
8. Secrets are not unnecessarily stored.
9. Large binary/model files are stored outside SQLite.
10. Audit records are generated by trusted application components.
11. Approval records are operation-specific.
12. Unknown security states fail closed.
13. Stored timestamps use UTC.
14. Database paths are configurable.
15. Backups are treated as sensitive data.

---

# 83. Data Architecture and Security

The data architecture exists to support the security architecture.

Especially:

```text
Tool Request
      ↓
Approval
      ↓
Execution
      ↓
Audit
```

This creates a persistent record of the lifecycle of privileged operations.

The database therefore supports security without becoming the security authority itself.

---

# 84. Data Architecture and Offline Operation

RUACH must remain useful without:

```text
cloud database
cloud storage
external analytics
internet connectivity
```

Core data must remain local.

---

# 85. Performance Principles

SQLite performance should be protected through:

```text
short transactions
appropriate indexes
bounded queries
bounded content
limited write contention
prepared/parameterized queries
```

Do not optimize prematurely.

Measure before introducing complexity.

---

# 86. Backup Strategy

MVP should support a simple local backup strategy.

Conceptually:

```text
RUACH database
      ↓
SQLite-aware backup
      ↓
Timestamped backup
      ↓
Local backup directory
```

The exact backup command/tool will be defined during implementation.

---

# 87. Restore Safety

Restore operations must require deliberate user action.

A restore should never silently overwrite the active database.

Recommended conceptual flow:

```text
Select backup
     ↓
Validate backup
     ↓
Confirm restore
     ↓
Create safety backup
     ↓
Restore
     ↓
Verify integrity
```

---

# 88. Database Diagnostics

The system should eventually provide local diagnostics for:

```text
database connectivity
schema version
migration status
integrity
database size
```

Diagnostics must not expose secrets.

---

# 89. Data Testing

Tests must cover:

```text
CRUD operations
foreign keys
cascade behavior
transactions
migration upgrades
migration failures
concurrent access where relevant
corrupt/invalid records
approval lifecycle
audit lifecycle
deletion behavior
backup/restore
```

---

# 90. Repository Testing

Repository tests should verify persistence behavior independently from HTTP.

Example:

```text
ConversationRepository
    ↓
SQLite test database
    ↓
create
read
update
delete
```

This allows database failures to be isolated from API failures.

---

# 91. Service Testing

Service tests should verify business rules.

Example:

```text
ToolService
    ↓
Policy
    ↓
Approval
    ↓
Execution state
```

The tests should verify that invalid state transitions are rejected.

---

# 92. Migration Testing

CI/development workflow should verify that:

```text
empty database
    ↓
all migrations
    ↓
current schema
```

works correctly.

A fresh installation must be reproducible.

---

# 93. Data Architecture vs Filesystem

RUACH has two distinct persistence domains:

```text
SQLite
=
application state
```

and:

```text
Filesystem
=
user files / models / external artifacts
```

They must not be confused.

---

# 94. Final Architecture

The intended persistence architecture is:

```text
                 ┌─────────────────┐
                 │    Frontend     │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │     FastAPI     │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Application     │
                 │ Services        │
                 └────────┬────────┘
                          │
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
             ┌──────────┐  ┌─────────────┐
             │Repository│  │ Tool Engine │
             └────┬─────┘  └─────────────┘
                  │
                  ▼
             ┌──────────┐
             │ SQLite   │
             └──────────┘
```

The filesystem remains outside the database:

```text
Application
     │
     ├────────── SQLite
     │
     └────────── Approved Filesystem
```

---

# 95. Final Principle

RUACH should not treat data storage as an afterthought.

The database must preserve the history and state required to make the system:

```text
Reliable
Recoverable
Auditable
Offline-capable
Secure
Maintainable
```

At the same time:

> **Store what the system needs. Do not store everything simply because it can be stored.**

The simplest correct data architecture is the preferred architecture.

---

# 96. Data Architecture Invariants

Unless explicitly changed through an approved architecture decision:

1. SQLite remains the MVP database.
2. SQLAlchemy remains the database access layer.
3. Alembic remains the migration mechanism.
4. Application state remains separate from user filesystem data.
5. The LLM has no direct database access.
6. The frontend has no direct database access.
7. Arbitrary SQL is not exposed as a tool.
8. Tool requests and executions remain separate concepts.
9. Security-sensitive actions remain auditable.
10. Database transactions preserve logical consistency.
11. Database schema changes are version-controlled.
12. Large model files remain outside the database.
13. Sensitive data storage is minimized.
14. Backup and restore are explicit operations.
15. Unknown or inconsistent authorization states fail closed.

---

# 97. Closing Statement

RUACH's data layer should be boring.

That is a feature.

We do not need:

```text
Redis
PostgreSQL
MongoDB
Vector Database
Kafka
Cloud Storage
```

for the MVP.

We need:

```text
SQLite
   +
SQLAlchemy
   +
Alembic
   +
good schema design
   +
clear boundaries
   +
correct transactions
```

> **Simple data architecture gives RUACH a stable foundation without turning a local AI project into distributed-systems homework.**
