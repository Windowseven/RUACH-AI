# RUACH — API Contract

**Document:** `06_API_CONTRACT.md`
**Version:** 0.1
**Status:** Draft for approval
**Scope:** RUACH MVP

---

# 1. Purpose

This document defines the HTTP and WebSocket API contract for RUACH MVP.

The API is the formal communication boundary between:

```text
Browser / PWA
      ↓
FastAPI
      ↓
Application Layer
      ↓
Orchestrator
      ↓
Tool Engine / Inference
```

The frontend must communicate with RUACH through this contract.

The frontend must not access:

* SQLite directly
* Python modules directly
* local model files
* Termux shell
* operating-system processes
* privileged filesystem operations

---

# 2. API Design Principles

The RUACH API must be:

* explicit
* predictable
* typed
* versionable
* secure
* easy to test
* easy to understand
* suitable for localhost operation

The API must not expose internal implementation details unnecessarily.

---

# 3. API Base URL

Development default:

```text
http://127.0.0.1:<PORT>
```

The default host should remain localhost.

Example:

```text
http://127.0.0.1:8018
```

The actual port is configuration-driven. On the owner's machine, port 8000 is
occupied by a third-party VPN daemon (`VPN4Test`), so the backend default is 8018
(see `backend/app/config/settings.py`).

---

# 4. API Versioning

The API must use an explicit version prefix.

MVP:

```text
/api/v1
```

Example:

```text
GET /api/v1/health
```

Versioning prevents future API changes from silently breaking the frontend.

---

# 5. Content Type

JSON is the default API representation.

Requests:

```http
Content-Type: application/json
```

Responses:

```http
Content-Type: application/json
```

Exceptions such as streaming responses may use another appropriate content type.

---

# 6. Request ID

Each API request should have a request identifier.

Example:

```http
X-Request-ID: 7b8d2d4c-...
```

If the client does not provide one, the backend should generate one.

The request ID should be propagated through relevant internal operations.

Example:

```text
HTTP Request
     ↓
request_id
     ↓
Orchestrator
     ↓
Inference
     ↓
Tool Engine
     ↓
Audit Log
```

This allows one user interaction to be traced across components.

---

# 7. Common Response Structure

Successful responses should use predictable structures.

Example:

```json
{
  "data": {},
  "request_id": "..."
}
```

Error responses should use a structured format.

Example:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request.",
    "details": []
  },
  "request_id": "..."
}
```

The frontend should rely on the error code rather than parsing human-readable messages.

---

# 8. HTTP Status Codes

RUACH should use conventional HTTP status codes.

| Status | Meaning                                  |
| ------ | ---------------------------------------- |
| 200    | Successful request                       |
| 201    | Resource created                         |
| 202    | Accepted for processing                  |
| 204    | Successful request with no body          |
| 400    | Invalid request                          |
| 401    | Authentication required where applicable |
| 403    | Operation not permitted                  |
| 404    | Resource not found                       |
| 409    | Resource conflict                        |
| 413    | Request too large                        |
| 422    | Validation failure                       |
| 429    | Rate limit exceeded                      |
| 500    | Internal server error                    |
| 503    | Service unavailable                      |

The API must not return `200` for failed operations merely because the server itself responded successfully.

---

# 9. Health Endpoint

The API must provide a basic health endpoint.

```http
GET /api/v1/health
```

Example response:

```json
{
  "data": {
    "status": "ok"
  },
  "request_id": "..."
}
```

The health endpoint must not expose:

* secrets
* environment variables
* filesystem contents
* model configuration details that should remain private

---

# 10. Readiness Endpoint

A separate readiness endpoint may be provided.

```http
GET /api/v1/ready
```

Its purpose is to determine whether RUACH is ready to process requests.

Possible states:

```text
ready
not_ready
degraded
```

Example:

```json
{
  "data": {
    "status": "ready",
    "inference": "available",
    "database": "available"
  },
  "request_id": "..."
}
```

---

# 11. System Information Endpoint

If system information is exposed, it must be intentionally limited.

Possible endpoint:

```http
GET /api/v1/system
```

Allowed information may include:

```text
RUACH version
API version
inference availability
database availability
runtime status
```

Do not expose sensitive operating-system information unnecessarily.

---

# 12. Chat Endpoint

The primary user interaction endpoint is:

```http
POST /api/v1/chat
```

Purpose:

> Submit a user message to the RUACH orchestrator.

---

# 13. Chat Request

Example:

```json
{
  "message": "Explain this Python error.",
  "conversation_id": "optional-id"
}
```

Fields:

| Field           | Type        | Required |
| --------------- | ----------- | -------- |
| message         | string      | yes      |
| conversation_id | UUID/string | no       |

The backend must validate:

* message type
* message length
* conversation identifier
* request size

---

# 14. Chat Response

Example:

```json
{
  "data": {
    "message_id": "msg_123",
    "conversation_id": "conv_123",
    "role": "assistant",
    "content": "The error occurs because..."
  },
  "request_id": "req_123"
}
```

The API should not expose internal model reasoning or hidden chain-of-thought.

Only the user-facing response and appropriate structured metadata should be returned.

---

# 15. Conversation Creation

If conversations are persistent in MVP, provide:

```http
POST /api/v1/conversations
```

Example request:

```json
{
  "title": "Python debugging"
}
```

Response:

```json
{
  "data": {
    "id": "conv_123",
    "title": "Python debugging"
  },
  "request_id": "..."
}
```

---

# 16. Conversation Listing

```http
GET /api/v1/conversations
```

Example:

```json
{
  "data": [
    {
      "id": "conv_123",
      "title": "Python debugging",
      "created_at": "2026-08-22T12:00:00Z"
    }
  ],
  "request_id": "..."
}
```

Pagination should be introduced if the number of conversations can become large.

---

# 17. Conversation Retrieval

```http
GET /api/v1/conversations/{conversation_id}
```

The response may include:

```text
conversation metadata
messages
timestamps
tool activity metadata where appropriate
```

The API must not expose:

* internal prompts
* secrets
* hidden model reasoning
* security-sensitive internal state

---

# 18. Conversation Deletion

```http
DELETE /api/v1/conversations/{conversation_id}
```

Expected successful response:

```http
204 No Content
```

Deletion must follow the application's data-retention policy.

---

# 19. Message Model

A message should conceptually contain:

```json
{
  "id": "msg_123",
  "conversation_id": "conv_123",
  "role": "user",
  "content": "Hello",
  "created_at": "..."
}
```

Supported roles should be explicitly defined.

MVP:

```text
user
assistant
system/internal
tool
```

Internal roles must not automatically be rendered as normal user-facing messages.

---

# 20. Streaming

RUACH may support streamed model responses.

Preferred future interface:

```http
POST /api/v1/chat/stream
```

Possible transport:

```text
Server-Sent Events
```

or:

```text
WebSocket
```

The exact streaming transport remains an implementation decision.

---

# 21. Streaming Principle

Streaming must not bypass security controls.

Incorrect:

```text
Stream
   ↓
direct tool execution
```

Correct:

```text
Stream
   ↓
Orchestrator
   ↓
Tool proposal
   ↓
Policy
   ↓
Approval
   ↓
Execution
```

---

# 22. Tool Request Model

AI-generated tool calls must use structured data.

Example:

```json
{
  "tool": "filesystem.read",
  "arguments": {
    "path": "README.md"
  }
}
```

The model must not be allowed to submit arbitrary executable code as the tool request.

---

# 23. Tool Invocation Endpoint

The frontend should not normally invoke privileged tools directly.

However, if an explicit API endpoint is required for controlled tool operations:

```http
POST /api/v1/tools/execute
```

it must remain behind:

* validation
* authorization
* policy evaluation
* audit logging

The frontend must never be able to bypass the Tool Engine.

---

# 24. Tool Request Schema

Example:

```json
{
  "tool": "filesystem.read",
  "arguments": {
    "path": "README.md"
  }
}
```

The server determines:

```text
risk level
authorization requirement
allowed target
resource limits
execution policy
```

The client does not determine these values.

---

# 25. Tool Approval Endpoint

Sensitive operations may require explicit user approval.

Endpoint:

```http
POST /api/v1/tool-approvals/{approval_id}
```

Example request:

```json
{
  "decision": "approve"
}
```

Allowed decisions:

```text
approve
reject
```

The backend must verify that the approval corresponds to the exact pending operation.

---

# 26. Approval Security

The frontend must never be able to modify:

```text
tool
arguments
risk_level
target
request_id
```

through the approval request.

The approval endpoint should only communicate the user's decision.

Example:

```json
{
  "decision": "approve"
}
```

The backend retrieves the original pending action.

---

# 27. Pending Tool Approvals

Endpoint:

```http
GET /api/v1/tool-approvals
```

Purpose:

> Retrieve operations currently waiting for user authorization.

Example:

```json
{
  "data": [
    {
      "id": "approval_123",
      "tool": "filesystem.delete",
      "risk_level": "high",
      "target": "workspace/test.txt",
      "status": "pending"
    }
  ],
  "request_id": "..."
}
```

Sensitive arguments should be displayed carefully.

---

# 28. Tool Activity

The UI may display tool activity.

Endpoint:

```http
GET /api/v1/tool-activity
```

Example:

```json
{
  "data": [
    {
      "tool": "filesystem.read",
      "status": "completed",
      "created_at": "..."
    }
  ],
  "request_id": "..."
}
```

The endpoint must not expose sensitive internal data unnecessarily.

---

# 29. Filesystem API

The frontend should not receive unrestricted filesystem APIs.

If filesystem browsing is required for the UI, it must operate within an approved workspace.

Example:

```http
GET /api/v1/workspace/files
```

Possible response:

```json
{
  "data": [
    {
      "name": "README.md",
      "type": "file",
      "size": 1240
    },
    {
      "name": "src",
      "type": "directory"
    }
  ],
  "request_id": "..."
}
```

---

# 30. Workspace Boundary

All workspace API operations must respect the configured RUACH workspace.

The API must reject attempts to access paths outside the workspace.

Example:

```text
/api/v1/workspace/files?path=../../etc
```

must be rejected.

---

# 31. File Content Endpoint

If required:

```http
GET /api/v1/workspace/files/content
```

with a controlled path parameter.

The endpoint must enforce:

* workspace boundary
* file size limits
* path normalization
* access policy

---

# 32. File Modification API

If the UI needs file editing:

```http
PUT /api/v1/workspace/files/content
```

Example:

```json
{
  "path": "notes/example.txt",
  "content": "Hello"
}
```

The backend must validate the target before writing.

Sensitive modifications may require approval.

---

# 33. API and Tool Separation

The API layer and Tool Engine are different boundaries.

```text
HTTP API
   ↓
Application Service
   ↓
Tool Engine
   ↓
Tool
```

The API must not directly implement filesystem or process security logic.

---

# 34. Error Model

All API errors should use structured error codes.

Example:

```json
{
  "error": {
    "code": "TOOL_NOT_ALLOWED",
    "message": "The requested operation is not permitted.",
    "details": []
  },
  "request_id": "req_123"
}
```

---

# 35. Error Codes

Initial error codes may include:

```text
VALIDATION_ERROR
NOT_FOUND
CONFLICT
TOOL_NOT_FOUND
TOOL_NOT_ALLOWED
APPROVAL_REQUIRED
APPROVAL_REJECTED
PATH_NOT_ALLOWED
RESOURCE_LIMIT
INFERENCE_UNAVAILABLE
DATABASE_UNAVAILABLE
INTERNAL_ERROR
```

The list may grow as the API evolves.

---

# 36. Validation Errors

Validation errors should identify the relevant field where safe.

Example:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request.",
    "details": [
      {
        "field": "message",
        "reason": "Message cannot be empty."
      }
    ]
  },
  "request_id": "..."
}
```

---

# 37. API Security Rules

The API must enforce:

```text
localhost default
strict request validation
request size limits
tool authorization
workspace boundaries
structured errors
safe CORS
no secret exposure
audit logging
```

---

# 38. Authentication Boundary

MVP assumes local single-user operation.

Therefore, authentication may be omitted from the initial localhost-only API.

However:

> This is an explicit MVP constraint, not a permanent assumption.

If network access is introduced, authentication and authorization must be revisited.

---

# 39. API Rate Limits

Localhost-only MVP may use lightweight rate limiting or omit it initially where appropriate.

However, expensive operations should still have internal limits.

For example:

```text
maximum tool calls per request
maximum inference duration
maximum request body size
maximum concurrent inference operations
```

---

# 40. Idempotency

Operations that may be retried must define whether they are idempotent.

Examples:

```text
GET     → generally idempotent
DELETE  → should be designed carefully
POST    → usually not inherently idempotent
PUT     → generally idempotent
```

Sensitive operations should avoid accidental duplicate execution.

---

# 41. Tool Execution Idempotency

A particularly important case is:

```text
User approves
      ↓
network/client retries request
      ↓
same operation executes twice
```

The backend should use an operation/approval identifier to prevent unintended duplicate execution where necessary.

---

# 42. Concurrency

The API must define behavior when multiple operations target the same resource.

Example:

```text
Request A
   ↓
modify file

Request B
   ↓
modify same file
```

The application layer should prevent inconsistent state where necessary.

Database transactions and application-level locking may be used when justified.

---

# 43. Database Transactions

API operations that modify multiple related records should use appropriate database transactions.

Example:

```text
Create tool request
      +
Create audit event
      +
Update approval state
```

must not leave the system in an inconsistent partial state.

---

# 44. API Timeout Behavior

Long-running inference or tool operations must not cause unlimited HTTP connections to remain open.

The architecture should support:

```text
request
   ↓
job/task
   ↓
status/stream
```

when an operation exceeds reasonable request duration.

The exact asynchronous job model can be introduced when required.

---

# 45. Inference Status

The API may expose inference status.

Example:

```http
GET /api/v1/inference/status
```

Possible response:

```json
{
  "data": {
    "status": "available",
    "runtime": "local"
  },
  "request_id": "..."
}
```

Do not expose unnecessary internal runtime details.

---

# 46. Configuration API

Configuration should generally be managed locally by the backend.

The frontend should not freely modify security-sensitive configuration.

Avoid an endpoint such as:

```http
POST /api/v1/config
```

that allows arbitrary configuration mutation.

Sensitive configuration changes should use explicit settings with validation and authorization.

---

# 47. API Documentation

FastAPI should generate OpenAPI documentation from typed request/response models.

Development endpoints:

```text
/docs
/redoc
/openapi.json
```

These should be considered development/documentation interfaces.

---

# 48. OpenAPI as Contract

The OpenAPI schema should remain synchronized with the implementation.

The following must be represented accurately:

```text
paths
request schemas
response schemas
error schemas
status codes
parameters
```

The frontend should consume the documented API contract rather than guessing backend behavior.

---

# 49. Frontend API Client

The frontend should communicate through a small API client layer.

Conceptually:

```text
UI Component
     ↓
API Client
     ↓
HTTP
     ↓
FastAPI
```

Components should not contain raw API calls everywhere.

---

# 50. API Client Responsibilities

The client should handle:

* request creation
* JSON serialization
* response parsing
* error parsing
* request IDs where appropriate
* streaming
* retry behavior where safe

It must not implement backend security decisions.

---

# 51. Retry Rules

Retries must be conservative.

Safe candidates:

```text
GET
read-only operations
temporary availability failures
```

Dangerous automatic retries:

```text
delete
write
process execution
package installation
other side-effecting operations
```

A retry must never duplicate a sensitive action accidentally.

---

# 52. Chat Streaming Events

If streaming is implemented, events should use explicit types.

Conceptual example:

```json
{
  "type": "message.delta",
  "data": {
    "text": "Hello"
  }
}
```

Possible event types:

```text
message.started
message.delta
message.completed
tool.proposed
tool.approval_required
tool.completed
tool.failed
error
```

---

# 53. Tool Approval Streaming

A streamed interaction may emit:

```json
{
  "type": "tool.approval_required",
  "data": {
    "approval_id": "approval_123",
    "tool": "filesystem.delete",
    "risk_level": "high"
  }
}
```

The frontend then displays the approval interface.

The approval itself must still be submitted through the secure backend endpoint.

---

# 54. Streaming Security

Streaming events must not expose:

* hidden system prompts
* secrets
* internal chain-of-thought
* unauthorized filesystem content
* raw credentials
* security-sensitive internal state

---

# 55. API Observability

Relevant API events should be traceable through:

```text
request_id
conversation_id
message_id
tool_request_id
approval_id
```

These identifiers should make debugging possible without exposing private content.

---

# 56. API Contract Invariants

Unless explicitly changed:

1. API version prefix remains `/api/v1`.
2. JSON is the default API format.
3. localhost is the default network boundary.
4. Frontend never accesses SQLite directly.
5. Frontend never accesses Termux directly.
6. Privileged operations pass through the Tool Engine.
7. AI output is never treated as executable code.
8. Tool authorization is server-side.
9. Approval decisions are server-side.
10. Error responses use structured error codes.
11. Request IDs support traceability.
12. Security-sensitive operations are auditable.
13. Streaming cannot bypass authorization.
14. Retries must not duplicate dangerous operations.
15. API contracts must remain synchronized with OpenAPI.

---

# 57. MVP Endpoint Summary

| Method | Endpoint                          | Purpose                        |
| ------ | --------------------------------- | ------------------------------ |
| GET    | `/api/v1/health`                  | Basic health                   |
| GET    | `/api/v1/ready`                   | Readiness                      |
| GET    | `/api/v1/system`                  | Limited system status          |
| POST   | `/api/v1/chat`                    | Send message                   |
| POST   | `/api/v1/chat/stream`             | Stream response if implemented |
| POST   | `/api/v1/conversations`           | Create conversation            |
| GET    | `/api/v1/conversations`           | List conversations             |
| GET    | `/api/v1/conversations/{id}`      | Get conversation               |
| DELETE | `/api/v1/conversations/{id}`      | Delete conversation            |
| GET    | `/api/v1/tool-approvals`          | Pending approvals              |
| POST   | `/api/v1/tool-approvals/{id}`     | Approve/reject tool            |
| GET    | `/api/v1/tool-activity`           | Tool activity                  |
| GET    | `/api/v1/inference/status`        | Inference status               |
| GET    | `/api/v1/workspace/files`         | Workspace listing              |
| GET    | `/api/v1/workspace/files/content` | Read workspace file            |
| PUT    | `/api/v1/workspace/files/content` | Modify workspace file          |

Not every endpoint must be implemented on day one.

The actual MVP implementation should follow the roadmap and requirements.

---

# 58. Endpoint Addition Rule

A new endpoint must have a clear reason to exist.

Before adding an endpoint:

```text
Requirement
    ↓
Use case
    ↓
Resource/action identified
    ↓
Request/response defined
    ↓
Security reviewed
    ↓
Tests defined
    ↓
Endpoint approved
```

Do not create endpoints simply because an internal function exists.

---

# 59. API Evolution

Breaking changes require explicit documentation.

Examples:

```text
changing required fields
changing response semantics
removing endpoints
changing authorization behavior
changing error codes
```

If a breaking change is necessary, update:

```text
OpenAPI
frontend client
tests
documentation
versioning strategy
```

---

# 60. Final Principle

The API is not merely a collection of URLs.

It is a controlled contract between the RUACH interface and the application.

The fundamental rule is:

```text
Frontend
   ↓
API Contract
   ↓
Application
   ↓
Security Boundary
   ↓
Controlled Capability
```

The frontend may request.

The application may evaluate.

The security layer may authorize.

The tool engine may execute.

The operating system must never be exposed directly to the browser or the model.

> **A clean API contract prevents the frontend, AI, and operating system from becoming accidentally coupled.**
