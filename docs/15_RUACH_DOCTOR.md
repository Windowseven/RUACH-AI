
# RUACH Doctor Specification

**Document:** RUACH Doctor Specification  
**Status:** Approved for Implementation  
**Version:** 1.0  
**Audience:** RUACH Principal Engineer, Contributors, OpenCode Agent  
**Scope:** Device discovery, capability analysis, hybrid runtime selection, guided setup, installation planning, and verification

---

# 1. Purpose

RUACH Doctor is the device-aware intelligence layer responsible for determining how RUACH should be installed and operated on a particular device.

Doctor MUST NOT assume that a device is supported or unsupported based solely on:

- CPU architecture
- RAM
- Android version
- Python availability
- package availability
- presence or absence of a single dependency

Instead, Doctor MUST evaluate the device as a collection of capabilities and constraints.

The primary responsibility of Doctor is:

> Discover → Evaluate → Select → Plan → Install → Verify.

Doctor therefore acts as both:

1. A diagnostic subsystem.
2. A runtime architecture selector and installation orchestrator.

---

# 2. Core Design Principle

RUACH is capability-driven, not platform-driven.

The following assumption is forbidden:

```text
ARMv7 → unsupported
````

The correct model is:

```text
ARMv7
+
available compiler
+
available memory
+
available storage
+
Python capability
+
native runtime capability
+
dependency compatibility
+
inference capability
        ↓
determine the best viable RUACH architecture
```

A device that cannot support one implementation path MUST NOT automatically be classified as incapable of running RUACH.

Doctor MUST search for alternative execution paths.

---

# 3. Hybrid-First Principle

RUACH Doctor MUST be designed around a hybrid-first architecture.

Hybrid-first means:

> Prefer combining specialized runtimes when this provides better compatibility, performance, reliability, or resource usage.

Hybrid-first DOES NOT mean:

> Always install every runtime.

Doctor MUST select the smallest viable combination of components that provides the best RUACH experience for the device.

Example:

```text
Python
    ↓
orchestration / management

Native runtime
    ↓
AI inference

Lightweight HTTP layer
    ↓
local browser/API access
```

This allows RUACH to avoid forcing Python to perform work better suited to native code.

---

# 4. Doctor Responsibilities

Doctor MUST perform the following lifecycle:

```text
SCAN
  ↓
NORMALIZE
  ↓
ANALYZE
  ↓
SELECT PROFILE
  ↓
GENERATE INSTALLATION PLAN
  ↓
REQUEST USER CONFIRMATION
  ↓
INSTALL
  ↓
VERIFY
  ↓
REPORT
```

Doctor MUST support running the scan independently from installation.

Example:

```bash
./ruach doctor
```

must NOT modify the system.

Installation must be explicit:

```bash
./ruach setup
```

---

# 5. Discovery Layers

Doctor MUST collect information in independent discovery layers.

## 5.1 Platform Discovery

Detect:

* operating system
* Android version
* Termux environment
* kernel version
* device manufacturer when safely available
* device model when safely available
* architecture
* ABI
* 32-bit/64-bit execution mode

Example:

```text
OS: Android
Environment: Termux
Architecture: ARMv7
ABI: armeabi-v7a
Execution mode: 32-bit
```

---

# 6. CPU Discovery

Doctor MUST detect:

* architecture
* ABI
* CPU core count
* CPU model where available
* supported instruction features where available

CPU information MUST be treated as capability information rather than merely descriptive information.

Example:

```text
Architecture: ARMv7
Cores: 8
Instruction features: detected
```

Doctor MUST tolerate systems where some CPU information is inaccessible.

Failure to read optional CPU metadata MUST NOT cause Doctor to crash.

---

# 7. Memory Discovery

Doctor MUST detect:

* total RAM
* available RAM
* free RAM where available
* cached memory where available
* swap visibility
* swap total where available
* swap availability where available

Doctor MUST distinguish:

```text
RAM total
RAM currently available
configured swap
usable swap
```

These values MUST NOT be treated as interchangeable.

For example:

```text
SwapTotal: 2 GB
```

does NOT automatically mean:

```text
2 GB usable swap
```

Doctor MUST report uncertainty when Android permissions prevent verification.

---

# 8. Storage Discovery

Doctor MUST detect:

* available storage for the RUACH installation location
* available storage for models
* available storage for temporary build artifacts

System partitions MUST NOT be confused with the Termux/RUACH writable filesystem.

Example:

```text
System filesystem:
    irrelevant to RUACH installation

Termux filesystem:
    31 GB available

RUACH model storage:
    sufficient
```

Doctor MUST identify the actual filesystem backing:

```bash
$HOME
$PREFIX
RUACH installation directory
RUACH model directory
```

---

# 9. Toolchain Discovery

Doctor MUST detect the availability and version of:

* clang
* gcc where applicable
* make
* cmake
* ninja
* git
* rustc
* cargo

Example:

```text
clang: PASS
cmake: PASS
make: PASS
ninja: PASS
git: PASS
rustc: MISSING
cargo: MISSING
```

Missing Rust MUST NOT automatically classify the device as unsupported.

It only affects capabilities that require Rust.

---

# 10. Python Runtime Discovery

Doctor MUST detect:

* Python executable
* Python version
* pip version
* Python platform
* Python architecture
* ABI
* supported wheel tags
* virtual environment capability

Doctor MUST recognize Android Python environments explicitly.

Example:

```text
Python:
    3.14.6

Platform:
    android

Architecture:
    armv7l

Python:
    32-bit

Wheel platform:
    android_armeabi_v7a
```

---

# 11. Python Dependency Capability

Doctor MUST distinguish between:

```text
package exists on PyPI
```

and:

```text
package can actually be installed on this device
```

The following states MUST be supported:

```text
AVAILABLE_WHEEL
SOURCE_BUILD_REQUIRED
SOURCE_BUILDABLE
SOURCE_BUILD_BLOCKED
UNAVAILABLE
UNKNOWN
```

Example:

```text
pydantic:
    package available

pydantic-core:
    compatible wheel unavailable

pydantic-core:
    source build required

Rust:
    unavailable

Result:
    Python API dependency path constrained
```

Doctor MUST NOT classify the entire RUACH runtime as unsupported because of one Python dependency.

---

# 12. Native Runtime Capability

Doctor MUST treat native inference as a first-class runtime path.

The native runtime is expected to provide the performance-critical inference functionality.

Potential implementation:

```text
C/C++
    ↓
llama.cpp
    ↓
GGUF model
```

Doctor MUST distinguish between:

```text
native source available
native source compilable
native binary executable
native runtime functional
native inference functional
```

These are separate capability levels.

---

# 13. Inference Capability Levels

Doctor MUST eventually support the following inference states:

```text
NOT_TESTED
SOURCE_AVAILABLE
BUILDABLE
EXECUTABLE
MODEL_LOADABLE
INFERENCE_FUNCTIONAL
INFERENCE_DEGRADED
INFERENCE_FAILED
```

A successful compilation MUST NOT be interpreted as successful inference.

---

# 14. Runtime Profiles

Doctor MUST support multiple runtime profiles.

Profiles MUST be extensible.

Initial profiles:

```text
HYBRID-NATIVE
HYBRID-PYTHON
NATIVE
PYTHON
MINIMAL
UNSUPPORTED
```

---

# 15. HYBRID-NATIVE

Recommended when:

* native inference is viable
* Python is available but constrained
* Python native dependencies are problematic
* device resources favor native execution

Architecture:

```text
Python
    ↓
control / orchestration

Native runtime
    ↓
inference

Model manager
    ↓
GGUF models
```

This is the primary target profile for constrained Android/Termux devices.

---

# 16. HYBRID-PYTHON

Recommended when:

* Python ecosystem is healthy
* Python API dependencies are installable
* native inference is available
* device resources are sufficient

Architecture:

```text
Python API
    ↓
RUACH control layer
    ↓
Native inference adapter
    ↓
llama.cpp
```

---

# 17. NATIVE

Recommended when:

* native runtime is functional
* Python is unnecessary or undesirable
* device resources are highly constrained

Architecture:

```text
CLI / lightweight API
        ↓
Native RUACH runtime
        ↓
llama.cpp
        ↓
GGUF
```

---

# 18. PYTHON

Recommended when:

* Python dependencies are fully compatible
* native inference is still available through an adapter
* Python provides meaningful advantages on the device

Python MUST NOT be assumed to be the inference engine.

---

# 19. MINIMAL

Minimal mode MUST provide the smallest viable RUACH installation.

Possible components:

```text
RUACH CLI
Native inference
Model management
Basic configuration
```

Optional services MUST NOT be installed unless requested or required.

Minimal mode exists for constrained devices.

---

# 20. UNSUPPORTED

Doctor MUST select UNSUPPORTED only when all known viable execution strategies fail.

Example:

```text
No supported architecture
+
No executable native runtime
+
No compatible Python runtime
+
No alternative execution path
```

A single dependency failure is NOT sufficient.

---

# 21. Capability Scoring

Doctor MAY use a scoring system internally, but final profile selection MUST be explainable.

Example conceptual scoring:

```text
Native inference functional       +40
Native compilation available     +15
Python compatible                +15
HTTP capability                  +10
RAM sufficient                   +10
Storage sufficient               +10
```

However, hard constraints MUST override scores.

Example:

```text
native runtime cannot execute
```

must prevent selection of a profile that requires native inference.

Scores MUST NOT hide mandatory requirements.

---

# 22. Capability Graph

Doctor SHOULD internally represent the device as a capability graph.

Example:

```text
Device
  │
  ├── Architecture
  │
  ├── Memory
  │
  ├── Storage
  │
  ├── Python
  │     └── Dependencies
  │
  ├── Native Toolchain
  │
  ├── Native Runtime
  │
  └── Inference
```

This graph allows Doctor to reason about alternative execution paths.

---

# 23. Runtime Selection

Doctor MUST generate:

```text
CapabilityReport
RuntimeDecision
InstallationPlan
```

Example:

```json
{
  "profile": "HYBRID-NATIVE",
  "reason": [
    "Native compilation available",
    "Native inference path viable",
    "Python available",
    "Python native dependency path constrained"
  ]
}
```

---

# 24. Guided CLI

The setup process MUST be understandable to a normal user.

Command:

```bash
./ruach setup
```

Example:

```text
╭──────────────────────────────────────────────╮
│              RUACH SYSTEM DOCTOR             │
╰──────────────────────────────────────────────╯

Scanning device...

✓ Android detected
✓ Termux detected
✓ ARMv7 detected
✓ 1.87 GB RAM detected
✓ 31 GB storage available
✓ Clang available
✓ CMake available
✓ Ninja available
⚠ Python native dependency limitation detected

Analyzing runtime options...

Recommended profile:

    HYBRID-NATIVE

Reason:

    Native inference is the preferred execution path.
    Python remains available for orchestration.
    Some Python native dependencies cannot currently
    be satisfied on this device.

Continue? [Y/n]
```

Doctor MUST explain technical failures in human-readable language.

---

# 25. Installation Planning

Doctor MUST generate an installation plan before modifying the system.

Example:

```text
Installation Plan

[1] Create RUACH directories
[2] Prepare native runtime
[3] Prepare model directory
[4] Install compatible Python components
[5] Configure hybrid bridge
[6] Generate runtime configuration
[7] Run health checks
```

The plan MUST be inspectable.

Optional command:

```bash
./ruach setup --plan
```

MUST show the plan without executing it.

---

# 26. Installation Safety

Doctor MUST NOT:

* overwrite user files without confirmation
* modify Android system partitions
* require root
* modify unrelated Termux configuration
* install unnecessary dependencies
* download unverified binaries
* execute arbitrary remote scripts

Every downloaded artifact MUST have a known source.

Where possible, artifacts MUST be verified using checksums.

---

# 27. Installation Idempotency

Running:

```bash
./ruach setup
```

multiple times MUST be safe.

Doctor MUST detect already-installed components.

Example:

```text
✓ Native runtime already installed
✓ Model directory already exists
✓ Configuration already exists
→ No action required
```

Repeated setup MUST NOT rebuild or redownload components unnecessarily.

---

# 28. Installation Failure Recovery

If installation fails:

```text
FAILED
  ↓
identify failed step
  ↓
preserve useful completed work
  ↓
report reason
  ↓
suggest recovery
```

Doctor MUST NOT leave the system in an unknowable state.

Installation steps SHOULD be transactional where practical.

---

# 29. Verification

After installation, Doctor MUST verify the selected runtime.

Verification levels:

```text
Environment
Toolchain
Runtime
Model
Inference
API
```

Example:

```text
Environment ........ PASS
Native runtime ..... PASS
Model loading ...... PASS
Inference .......... PASS
HTTP interface ..... PASS
```

---

# 30. Degraded Operation

Doctor MUST support degraded runtime states.

Example:

```text
RUACH READY — DEGRADED

Available:
✓ Native inference
✓ CLI
✓ Model manager

Unavailable:
⚠ Python API
⚠ Optional web service
```

A degraded runtime MUST remain usable where possible.

---

# 31. Machine-Readable Output

Doctor MUST support JSON output.

Example:

```bash
./ruach doctor --json
```

Output MUST contain structured information suitable for:

* installer automation
* tests
* debugging
* bug reports
* telemetry-free local diagnostics
* future GUIs

No cloud service is required.

---

# 32. Human-Readable Output

Default Doctor output MUST be optimized for humans.

Example:

```text
Status: READY
Profile: HYBRID-NATIVE
Inference: AVAILABLE
API: OPTIONAL
Model storage: 31 GB available
Warnings: 1
```

Detailed output MAY be available through:

```bash
./ruach doctor --verbose
```

---

# 33. Offline-First Requirement

Doctor MUST work without cloud connectivity for all local detection tasks.

The following MUST NOT require internet:

* hardware detection
* RAM detection
* storage detection
* architecture detection
* toolchain detection
* Python detection
* profile selection based on known rules
* local runtime verification

Network access MAY be required for:

* downloading source code
* downloading models
* downloading missing packages
* retrieving remote metadata

Network failure MUST NOT crash Doctor.

---

# 34. Model Management

Model installation MUST be separated from runtime installation.

Doctor MUST determine:

```text
runtime capability
```

before recommending a model.

Model selection SHOULD consider:

* available RAM
* architecture
* model size
* quantization
* storage
* expected context size

Doctor MUST NOT automatically download a large model onto a constrained device.

---

# 35. Security

Doctor MUST follow least privilege.

RUACH MUST NOT require root for normal operation.

Doctor MUST avoid:

```bash
curl ... | sh
```

style installation.

Remote artifacts MUST be:

1. Explicitly identified.
2. Downloaded from trusted sources.
3. Verified where possible.
4. Stored in controlled directories.

---

# 36. Logging and Audit

Doctor MUST maintain local logs for important operations.

Logs SHOULD record:

```text
timestamp
operation
component
result
error
selected profile
installation step
verification result
```

Logs MUST NOT contain:

* passwords
* API keys
* tokens
* unnecessary personal information

---

# 37. ARMv7 Reference Case

The current reference device has approximately:

```text
Architecture: ARMv7
Execution: 32-bit
Android: 15
RAM: ~1.87 GB
Available RAM: ~594 MB at test time
Storage: ~31 GB available
Python: 3.14.6
Clang: 21.1.8
CMake: 4.4.2
Make: 4.4.1
Ninja: 1.13.2
Git: 2.55.0
Rust: unavailable
Cargo: unavailable
```

Observed Python dependency constraint:

```text
pydantic-core
```

A compatible binary wheel was not available for the tested environment.

Source installation attempted to require Rust/maturin and failed because the required Rust target/toolchain was unavailable.

This MUST be treated as:

```text
Python dependency-path constraint
```

NOT:

```text
RUACH device unsupported
```

This device is therefore a primary test target for the HYBRID-NATIVE architecture.

---

# 38. Testing Strategy

Doctor MUST be testable independently from real hardware.

Tests MUST include:

```text
Unit tests
Integration tests
Capability rule tests
Profile selection tests
Installation planning tests
CLI tests
```

Synthetic device fixtures SHOULD represent:

```text
Android ARMv7 low-memory
Android ARM64 constrained
Android ARM64 capable
Linux ARM64
Linux x86_64
macOS development environment
```

---

# 39. Real Device Validation

Synthetic tests MUST NOT replace real-device validation.

The project MUST maintain a real-device validation matrix.

Example:

| Device Class      | Architecture |      RAM | Native        | Python      | Profile       |
| ----------------- | ------------ | -------: | ------------- | ----------- | ------------- |
| Reference Android | ARMv7        | ~1.87 GB | TBD/validated | constrained | HYBRID-NATIVE |
| Android capable   | ARM64        |   4–8 GB | TBD           | compatible  | HYBRID-PYTHON |
| Desktop           | x86_64       |    8+ GB | supported     | supported   | HYBRID-PYTHON |

The matrix MUST be updated as real devices are tested.

---

# 40. Doctor Extensibility

New capabilities MUST be addable without rewriting Doctor.

Future detectors MAY include:

```text
GPU
NPU
OpenCL
Vulkan
NNAPI
hardware acceleration
thermal constraints
battery state
background execution restrictions
SELinux constraints
```

These MUST be optional capabilities.

Doctor MUST continue functioning if they cannot be detected.

---

# 41. Architecture Boundaries

Doctor MUST NOT contain the actual inference implementation.

Doctor determines:

```text
WHAT CAN RUN
```

and:

```text
WHAT SHOULD RUN
```

Runtime components determine:

```text
HOW IT RUNS
```

Therefore:

```text
Doctor
   ↓
Runtime Plan
   ↓
Runtime Manager
   ↓
Inference Adapter
   ↓
Native/Python implementation
```

This separation is mandatory.

---

# 42. Doctor Does Not Own Business Logic

Doctor MUST NOT become a general-purpose RUACH application layer.

It is responsible for:

* environment discovery
* capability analysis
* runtime selection
* installation orchestration
* verification

It MUST NOT contain:

* chat logic
* model prompting logic
* conversation storage
* user application logic
* UI business logic

---

# 43. Acceptance Criteria

Doctor implementation is considered complete only when all of the following are true:

### Discovery

* [ ] Detects Android/Termux.
* [ ] Detects architecture and ABI.
* [ ] Detects RAM.
* [ ] Detects storage.
* [ ] Detects Python.
* [ ] Detects compiler/toolchain.
* [ ] Detects relevant dependency capabilities.

### Decision

* [ ] Produces a capability report.
* [ ] Selects a runtime profile.
* [ ] Explains why the profile was selected.
* [ ] Supports hybrid profiles.
* [ ] Does not reject devices based on one failed dependency.

### Installation

* [ ] Generates installation plan.
* [ ] Shows plan before execution.
* [ ] Requests confirmation.
* [ ] Performs idempotent installation.
* [ ] Handles failures safely.

### Verification

* [ ] Verifies installed runtime.
* [ ] Verifies model loading.
* [ ] Verifies inference where available.
* [ ] Reports degraded operation.

### CLI

* [ ] `./ruach doctor`
* [ ] `./ruach doctor --verbose`
* [ ] `./ruach doctor --json`
* [ ] `./ruach setup`
* [ ] `./ruach setup --plan`

### Testing

* [ ] Unit tests exist.
* [ ] Profile-selection tests exist.
* [ ] Synthetic device fixtures exist.
* [ ] Reference ARMv7 device is tested.

---

# 44. Final Design Rule

The most important rule of RUACH Doctor is:

> **Never confuse failure of one implementation with failure of the platform.**

If:

```text
Python path fails
```

Doctor should investigate:

```text
Native path
Hybrid path
Lightweight path
Minimal path
```

If:

```text
Native path fails
```

Doctor should investigate:

```text
Python path
Hybrid path
```

Only when all viable execution strategies fail should RUACH report:

```text
UNSUPPORTED
```

The goal is not to make every device run the exact same RUACH stack.

The goal is:

> **Make every capable device run the best RUACH architecture that its actual capabilities allow.**

---

# 45. Engineering Principle

RUACH Doctor is therefore not merely:

```text
system checker
```

It is:

```text
CAPABILITY DISCOVERY
        +
RUNTIME ARCHITECTURE SELECTION
        +
INSTALLATION ORCHESTRATION
        +
POST-INSTALL VERIFICATION
```

In one sentence:

> **RUACH Doctor converts device capabilities into a verified RUACH runtime.**

---

**END OF SPECIFICATION**

```

