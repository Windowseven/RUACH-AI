Twende kaka 😂🔥. Hii ndiyo **next MD** — copy/paste moja kwa moja.

````md
# RUACH — Guided CLI UX Specification

**Document:** `XX_GUIDED_CLI_UX.md`  
**Status:** Draft  
**Version:** 1.0  
**Owner:** RUACH Principal Engineering  
**Audience:** RUACH implementation agents, developers, maintainers  
**Scope:** Guided CLI installation, Doctor, setup, repair, runtime selection, model setup

---

# 1. Purpose

RUACH must provide a guided command-line experience that is simple for beginners while remaining powerful for advanced users.

The CLI must not behave like a traditional diagnostic utility that prints large amounts of technical information and expects the user to understand it.

Instead, RUACH should behave like an intelligent installation assistant.

The user should be guided through the process one decision at a time.

The system may perform many internal checks, but the user should only see information relevant to the current step.

---

# 2. Core UX Principle

> RUACH should diagnose deeply, but communicate simply.

The internal system may perform dozens of diagnostics.

The default user experience must progressively reveal information.

Bad:

```text
ERROR: pydantic-core wheel unavailable
maturin build failed
rustc target unsupported
SOABI mismatch
C compiler configuration...
````

Preferred:

```text
⚠ One Python component cannot run natively on this device.

RUACH has another option.

Choose:

1. Use hybrid mode ⭐ Recommended
2. Try native Python mode
3. Skip this component
4. Show technical details

Select [1-4]:
```

---

# 3. UX Goals

The guided CLI must optimize for:

* simplicity
* speed
* clarity
* confidence
* recoverability
* progressive disclosure
* device awareness
* automation
* minimal user typing
* actionable errors
* intelligent defaults

The user should rarely need to type long commands or technical configuration.

---

# 4. Interaction Model

RUACH supports four primary interaction styles.

## 4.1 Yes / No

Use for confirmation.

```text
Continue? [Y/n]
```

Default action should normally be the recommended action.

Examples:

```text
Continue? [Y/n]

Install recommended configuration? [Y/n]

Retry? [Y/n]
```

---

# 4.2 Number Selection

Use when multiple actions are available.

```text
What would you like to do?

1. Retry
2. Use fallback
3. Skip
4. Show details
5. Exit

Select [1-5]:
```

Numbers must always be stable and predictable.

---

# 4.3 Short Text Input

Use only when unavoidable.

Examples:

```text
Enter model path:
>
```

or:

```text
Enter model name:
>
```

Avoid asking the user to type commands when RUACH can provide a menu.

---

# 4.4 Advanced Commands

Experienced users must be able to bypass the guided UI.

Examples:

```bash
ruach doctor
ruach doctor --verbose
ruach doctor --repair
ruach doctor --json
ruach setup --non-interactive
```

The guided interface and advanced interface must use the same underlying engine.

---

# 5. Progressive Disclosure

The CLI must reveal information progressively.

### Level 1 — User-facing summary

```text
⚠ RUACH found a compatibility issue.
```

### Level 2 — Explanation

```text
This device cannot use one of the recommended
Python native components directly.
```

### Level 3 — Recommended solution

```text
RUACH recommends Hybrid Mode.
```

### Level 4 — Technical details

Only if requested:

```text
Python:
  3.14.6

Architecture:
  armv7l

ABI:
  android_armeabi_v7a

Missing native wheel:
  pydantic-core

Build backend:
  maturin

Rust:
  unavailable
```

### Level 5 — Raw diagnostics

Available through:

```bash
ruach doctor --verbose
```

or:

```text
Show technical details? [y/N]
```

---

# 6. First Launch Experience

The first interaction should feel intentional.

Example:

```text
╭──────────────────────────────────────────────╮
│                                              │
│                  RUACH                       │
│            Local AI Assistant                │
│                                              │
╰──────────────────────────────────────────────╯

Welcome 👋

Let's prepare RUACH for this device.

We'll check your system and choose the
best execution strategy automatically.

This will take a few steps.

Ready? [Y/n]
```

After confirmation:

```text
Great. Let's begin.
```

---

# 7. Guided Progress

The system should show progress.

Example:

```text
[1/8] Understanding your device...
✓ Done

[2/8] Checking memory...
```

After successful completion:

```text
✓ Memory check complete.

6 steps remaining.
```

The system must avoid flooding the terminal.

---

# 8. Progress Messages

Progress messages should be short.

Good:

```text
Checking Python...
✓ Python is ready.
```

Bad:

```text
Python subsystem diagnostic has completed successfully
after executing multiple compatibility checks against the
current interpreter and environment...
```

---

# 9. Encouragement

The CLI should periodically reassure the user.

Examples:

```text
✓ Good. Your device is compatible with Hybrid Mode.

Only 3 steps remaining.
```

```text
✓ Almost there.

Two steps remaining.
```

```text
✓ Final step.
```

Do not overuse motivational messages.

They should feel natural, not childish.

---

# 10. Device Classification

Doctor must classify the device before deciding installation strategy.

Example:

```text
[1/8] Understanding your device...

✓ Android 15
✓ ARMv7 32-bit
✓ 8 CPU cores
✓ ~1.8 GB RAM
✓ 31 GB available storage

Device profile:

ARM32-LIMITED

Recommended strategy:

HYBRID

Continue? [Y/n]
```

---

# 11. Architecture Selection

The user should not manually understand architecture internals.

Doctor should make the decision.

Possible execution strategies:

```text
NATIVE
HYBRID
LIGHTWEIGHT
REMOTE
UNSUPPORTED
```

The exact strategy depends on device capabilities.

Example:

```text
RUACH analyzed your device.

Recommended mode:

⭐ HYBRID

Why?

Your device can run the control layer,
but some native Python dependencies are
not available as compatible binaries.

RUACH can move those responsibilities
to a native inference runtime.

Use Hybrid Mode? [Y/n]
```

---

# 12. Hybrid Mode UX

Hybrid mode separates responsibilities.

```text
RUACH
│
├── Python Control Plane
│   ├── API
│   ├── configuration
│   ├── orchestration
│   ├── model management
│   └── device management
│
└── Native AI Plane
    ├── inference runtime
    └── GGUF model
```

The user should not need to understand this architecture.

The CLI may explain it briefly:

```text
Python will manage RUACH.

The native runtime will handle AI inference.

This configuration is optimized for your device.

Continue? [Y/n]
```

---

# 13. Installation Planning

Before installing anything substantial, Doctor must present a short plan.

Example:

```text
RUACH has prepared an installation plan.

Plan:

  ✓ Python control layer
  ✓ Lightweight API
  ✓ Native inference runtime
  ✓ Model manager
  ✓ Hybrid launcher

Estimated storage: 420 MB

Install this configuration? [Y/n]
```

The estimate must be based on actual selected components where possible.

---

# 14. Installation Execution

Installation must be incremental.

Example:

```text
[1/5] Preparing Python environment...
✓ Done

[2/5] Preparing native runtime...
✓ Done

[3/5] Preparing model manager...
✓ Done

[4/5] Configuring Hybrid Mode...
✓ Done

[5/5] Running final verification...
```

Do not print complete compiler output by default.

---

# 15. Failure Handling

Every failure must produce an actionable decision.

Never end with:

```text
ERROR
```

Instead:

```text
⚠ RUACH could not complete this step.

What would you like to do?

1. Retry
2. Use alternative
3. Skip
4. Show technical details
5. Exit

Select [1-5]:
```

---

# 16. Retry

Retry should be safe.

If a failed operation is retryable:

```text
The operation may succeed if we try again.

Retry? [Y/n]
```

Doctor must avoid repeatedly retrying deterministic failures.

---

# 17. Alternative Strategy

When the preferred strategy fails, Doctor should evaluate alternatives.

Example:

```text
The native runtime could not be prepared.

RUACH found an alternative.

Alternative:

Lightweight compatibility mode

Would you like to use it? [Y/n]
```

---

# 18. Skip

Optional components may be skipped.

Example:

```text
The model is optional at this stage.

Choose:

1. Download model
2. Use existing model
3. Skip model setup

Select [1-3]:
```

Skipping must not be allowed for components that are mandatory for the selected mode.

---

# 19. Technical Details

Technical information must always remain available.

Example:

```text
Show technical details? [y/N]
```

If selected:

```text
Technical diagnostics

Architecture:
  armv7l

Python:
  3.14.6

Platform:
  android

ABI:
  android_armeabi_v7a

Native compiler:
  clang 21.1.8

CMake:
  4.4.2

Ninja:
  1.13.2

Rust:
  unavailable

Failed component:
  pydantic-core

Reason:
  compatible binary wheel unavailable;
  source build requires Rust/maturin.
```

Full logs should be stored separately.

---

# 20. Log Management

Logs must not dominate the interactive UI.

Store detailed logs under:

```text
~/.ruach/logs/
```

Suggested structure:

```text
~/.ruach/logs/
├── doctor/
├── setup/
├── runtime/
├── model/
└── install/
```

Each operation should have a timestamped log.

---

# 21. Resume Support

If installation is interrupted, RUACH should remember progress.

Example:

```text
RUACH setup was interrupted previously.

Progress:

✓ Device analysis
✓ Python environment
✓ Runtime
○ Model
○ Final verification

Resume installation? [Y/n]
```

The user should not need to start over.

---

# 22. Cancellation

The user must always be able to stop safely.

For long-running operations:

```text
Press Ctrl+C to cancel.
```

RUACH should distinguish between:

* safe cancellation
* cancellation requiring cleanup
* dangerous interruption

After cancellation:

```text
Setup cancelled safely.

Your completed components have been preserved.

Resume later with:

ruach setup
```

---

# 23. Back Navigation

Menus should support going back when practical.

Example:

```text
1. Native mode
2. Hybrid mode
3. Lightweight mode
4. Back

Select [1-4]:
```

State must not become inconsistent when moving backwards.

---

# 24. Doctor Responsibilities

Doctor is not merely a checker.

Doctor must:

1. inspect the device
2. detect capabilities
3. detect constraints
4. identify compatibility problems
5. determine possible execution strategies
6. recommend the best strategy
7. explain the recommendation
8. offer repair actions
9. execute selected repairs
10. verify results
11. persist diagnostic results

---

# 25. Doctor Internal Architecture

Doctor should be separated into components.

```text
Doctor
│
├── Probes
│   ├── DeviceProbe
│   ├── MemoryProbe
│   ├── StorageProbe
│   ├── PythonProbe
│   ├── WheelProbe
│   ├── CompilerProbe
│   ├── CMakeProbe
│   ├── NinjaProbe
│   ├── RustProbe
│   ├── RuntimeProbe
│   └── ModelProbe
│
├── Decision Engine
│
├── Strategy Selector
│
├── Repair Engine
│
├── Verification Engine
│
└── Guided UI
```

---

# 26. Separation of Concerns

The UI must never directly implement system diagnostics.

Bad:

```text
CLI menu → shell command → decision
```

Preferred:

```text
Probe
  ↓
Diagnostic Result
  ↓
Decision Engine
  ↓
Recommendation
  ↓
Guided UI
  ↓
User Decision
  ↓
Action
  ↓
Verification
```

This makes Doctor testable.

---

# 27. Diagnostic Result Model

Every probe should produce structured information.

Conceptually:

```text
DiagnosticResult

status:
  PASS
  WARN
  FAIL
  UNKNOWN

severity:
  INFO
  LOW
  MEDIUM
  HIGH
  CRITICAL

capability:
  <capability name>

message:
  <short human-readable explanation>

technical_reason:
  <technical explanation>

recommended_actions:
  <available actions>
```

The UI should render the human-facing fields.

---

# 28. Decision Engine

Doctor must not simply report failures.

It must convert diagnostics into decisions.

Example:

```text
Input:

ARM32
+
1.8 GB RAM
+
Python available
+
pydantic-core wheel unavailable
+
Rust unavailable

Decision:

HYBRID
```

The decision engine should evaluate:

* architecture
* ABI
* CPU
* RAM
* storage
* Python version
* available wheels
* compiler availability
* native runtime availability
* model requirements
* network availability
* Android/Termux restrictions

---

# 29. Strategy Priority

The general preference order is:

```text
1. Native
2. Hybrid
3. Lightweight
4. Alternative
5. Unsupported
```

However, the actual order must be determined by capability.

Example:

```text
Device A:
Native

Device B:
Hybrid

Device C:
Lightweight

Device D:
Unsupported
```

The system must not force Native mode when Hybrid is safer.

---

# 30. ARM32 / Low-Memory Devices

ARM32 devices must not automatically be classified as unsupported.

Instead, Doctor should determine whether a reduced or hybrid architecture can work.

Example:

```text
ARMv7 detected.

Native Python AI stack:
  Limited

Native inference:
  Possible

Recommended:
  Hybrid Mode
```

The exact decision must be based on actual tests.

---

# 31. Model Selection

Model selection must be device-aware.

Doctor should consider:

* available RAM
* architecture
* model size
* quantization
* storage
* inference runtime compatibility

Example:

```text
Recommended model:

Qwen 3 0.6B — Q8

Why?

✓ Fits device memory profile
✓ Compatible model format
✓ Suitable for local inference

Use recommended model? [Y/n]
```

---

# 32. User Experience During Long Operations

Long operations must provide visible progress.

Example:

```text
Building native runtime...

██████████████░░░░░░ 70%

This may take a few minutes.

You can cancel with Ctrl+C.
```

The exact progress mechanism depends on the operation.

---

# 33. Non-Interactive Mode

All important operations must support automation.

Example:

```bash
ruach setup --non-interactive
```

or:

```bash
ruach doctor --json
```

Non-interactive mode must:

* never ask questions
* use deterministic defaults
* return meaningful exit codes
* write logs
* produce machine-readable output where requested

---

# 34. JSON Output

Example:

```bash
ruach doctor --json
```

should produce structured diagnostic information suitable for scripts.

The JSON schema must remain separate from the human CLI presentation layer.

---

# 35. Advanced Mode

Advanced users may request more detail.

Examples:

```bash
ruach doctor --verbose
ruach doctor --debug
ruach setup --verbose
```

Default mode remains concise.

---

# 36. Error Philosophy

Every error should answer:

1. What happened?
2. Does it matter?
3. What can RUACH do?
4. What does RUACH recommend?
5. What can the user choose?

Example:

```text
⚠ Native Python dependency unavailable.

This does not prevent RUACH from running.

Recommended:

⭐ Hybrid Mode

Choose:

1. Use Hybrid Mode
2. Try building from source
3. Skip
4. Show details
```

---

# 37. Success Philosophy

Success messages should be concise.

Good:

```text
✓ Runtime ready.

3 steps remaining.
```

Bad:

```text
The runtime installation procedure has successfully
completed all required operations...
```

---

# 38. Final Completion Screen

Example:

```text
╭──────────────────────────────────────────────╮
│                                              │
│              RUACH IS READY 🚀               │
│                                              │
╰──────────────────────────────────────────────╯

Your device has been configured successfully.

Configuration:

  Architecture : ARMv7
  Mode         : Hybrid
  Runtime      : Native
  Model        : Qwen 3 0.6B

Start RUACH:

  ruach chat

Doctor:

  ruach doctor

Setup:

  ruach setup
```

---

# 39. UX Safety Rules

The guided CLI must:

* never silently delete user data
* never overwrite models without confirmation
* never modify unrelated system files
* never require root unless explicitly necessary
* clearly explain privileged operations
* preserve existing configuration where possible
* support cancellation
* maintain logs

---

# 40. No Information Dump Rule

The default CLI must never dump large technical output unless:

* the user explicitly requests it
* debug mode is enabled
* the operation requires it for safety
* the user is reviewing a failed command

Technical logs belong in log files.

---

# 41. Smart Defaults

The recommended option must normally be the default.

Example:

```text
Use Hybrid Mode? [Y/n]
```

instead of:

```text
Choose:

1. Hybrid
2. Native
```

when Hybrid is clearly recommended.

Menus should still be used when the decision is genuinely ambiguous.

---

# 42. User Effort Budget

The installation experience should minimize:

* typing
* repeated confirmations
* technical decisions
* unnecessary navigation
* repeated diagnostics

The system should perform safe automatic actions without asking unnecessarily.

Ask the user only when:

* a meaningful choice exists
* data may be affected
* installation may consume significant resources
* a strategy choice materially changes behavior

---

# 43. Guided CLI State Machine

The installation flow should conceptually follow:

```text
WELCOME
   ↓
DEVICE_SCAN
   ↓
CLASSIFY
   ↓
PLAN
   ↓
CONFIRM
   ↓
INSTALL
   ↓
VERIFY
   ↓
MODEL_SETUP
   ↓
FINAL_VERIFY
   ↓
READY
```

Failure paths:

```text
INSTALL
   ↓
FAILURE
   ↓
RETRY / ALTERNATIVE / SKIP / DETAILS / EXIT
   ↓
VERIFY
```

---

# 44. Doctor State Machine

```text
START
  ↓
SCAN
  ↓
ANALYZE
  ↓
CLASSIFY
  ↓
RECOMMEND
  ↓
USER DECISION
  ↓
REPAIR
  ↓
VERIFY
  ↓
READY
```

---

# 45. Testing Requirements

The Guided CLI must be tested against at least:

### Fully capable device

Expected:

```text
NATIVE
```

### ARM64 constrained device

Expected:

```text
HYBRID or LIGHTWEIGHT
```

### ARM32 low-memory device

Expected:

```text
HYBRID / LIGHTWEIGHT
```

### Missing compiler

Doctor should offer alternatives.

### Missing Python wheel

Doctor should detect the issue before attempting unnecessary installation.

### No network

Doctor should detect offline state and offer local alternatives.

### Interrupted installation

Doctor should resume safely.

### Existing installation

Doctor should detect and avoid unnecessary reinstallations.

---

# 46. Acceptance Criteria

The Guided CLI is acceptable only if:

* the first-run experience is interactive
* installation is step-by-step
* user input is minimal
* technical output is hidden by default
* every failure provides an action
* retry is supported
* alternatives are supported
* optional components can be skipped
* progress is visible
* installation can resume
* Ctrl+C is handled safely
* advanced users can use non-interactive commands
* Doctor and Setup share the same diagnostic engine
* device capabilities influence installation strategy
* ARM32 devices are evaluated for hybrid operation
* hybrid mode is a first-class architecture
* logs are preserved
* final verification is mandatory

---

# 47. Engineering Principle

The Guided CLI is not a cosmetic layer.

It is part of RUACH's system architecture.

The CLI is responsible for translating complex system decisions into simple human decisions.

Therefore:

```text
Complexity belongs inside RUACH.

Clarity belongs in front of the user.
```

---

# 48. Final Principle

RUACH should make the user feel:

```text
"I don't need to understand everything.

RUACH understands my device,
explains what matters,
gives me a choice,
and helps me finish."
```

The goal is not merely to install software.

The goal is to make local AI deployment feel approachable.

---
