# 14 — Threat Model

Scope: RUACH as a single-user, on-device assistant. The model output is
UNTRUSTED INPUT (roadmap §12); the human is the authority for protected
actions; the local filesystem boundary is the asset.

## Assets & boundaries

| Asset | Boundary defender |
|---|---|
| Workspace files | `WorkspaceBoundary` dirfd walk, O_NOFOLLOW everywhere (P11B) |
| Approval integrity | CAS transitions in `PersistentApprovalStore` (P15) |
| Audit evidence | append-only JSONL + rotation, `AuditWriteError` fail-closed (P11A) |
| Anything OUTSIDE workspace | policy DENY by default; approvals bind capability+args |

## Threats → controls

| Threat | Control | Verified by |
|---|---|---|
| Model proposes path escape (`../`, absolute, symlink) | string-level refusal + kernel-level re-check at open time; ELOOP → denial | test_paths_security.py |
| Symlink swapped AFTER policy check (TOCTOU) | final components opened O_NOFOLLOW; unlinks never follow | test_paths_security swap-race test |
| Root renamed between validation and execution | root fd pinned at construction | root-pinning test |
| Malformed/hostile proposal text | parser returns None / payload gate refuses; nothing executes | test_proposal_adversarial.py |
| Degenerate echo loops treated as proposals | broken-proposal detector + bounded resampling | test_proposal_guard.py |
| Double-approve race executes twice | atomic CAS UPDATE WHERE status='PENDING' | concurrency race tests (P15) |
| Approve/reject cross race double-outcome | single-winner CAS; loser = non-executing outcome | concurrency race tests |
| Stale approvals linger forever | TTL expiry sweep at startup + lazy read expiry | approval persistence tests |
| Model-supplied "approved" fields self-authorize | stripped in `_validate`; only human endpoint approves | engine validate + API tests |
| Audit write fails silently (unlogged action) | `AuditWriteError` raised → classified SYSTEM_ERROR, action does not proceed | audit retention tests |
| Hostile extra fields smuggled via chat API | request models ignore unknown fields; tools only originate from parsed proposals | hostile-extra-fields test |

## Accepted residuals (documented, not hidden)

1. **Approvals bind argument strings, not inodes.** A file swapped
   between approval and execution still cannot leave the workspace
   (kernel checks), but the CONTENT may differ from what the user
   pictured. Mitigation would require inode pinning of arbitrary targets.
2. **Hardlink escapes** require an out-of-model hardlink already present
   inside the workspace; creating one needs filesystem access we do not
   give the model. Out of scope until evidence says otherwise.
3. **Real-directory swaps** stay contained by construction but can change
   which directory a relative path resolves to mid-session.
4. **Prompt injection via workspace file contents** may steer PROPOSALS;
   it cannot grant capabilities: every protected action still requires a
   human decision, and refusals are enforced below the model layer.
5. **Runtime logs are diagnostics**, not evidence — rotated with one
   backup generation (unlike audit segments).

## Non-goals

Multi-user authz, network exposure hardening (server binds loopback by
design), cryptographic audit sealing. Revisit only if the deployment
model changes.
