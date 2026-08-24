# RUACH Doctor & Guided Installation Specification

**Project:** RUACH
**Document:** 11_DOCTOR_AND_GUIDED_INSTALLATION.md
**Status:** Design Specification
**Version:** 1.0
**Audience:** RUACH implementation engineer / OpenCode agent

---

# 1. Purpose

This document defines the design of the RUACH device diagnostic system,
installation planner, and guided CLI installation experience.

The system MUST NOT treat unsupported dependencies as an automatic
"device unsupported" condition.

Instead, RUACH MUST determine:

1. what the device can do,
2. what the device cannot do,
3. which RUACH features remain possible,
4. which runtime architecture is appropriate,
5. which installation strategy should be used.

The central principle is:

> RUACH should adapt to the device instead of forcing every device into
> the same architecture.

---

# 2. Components

The implementation SHALL contain three closely related components:

1. RUACH Doctor
2. Installation Planner
3. Guided CLI Installer

These components MUST share the same capability model.

Architecture:

```text
Device
  │
  ▼
Doctor
  │
  ▼
Capability Matrix
  │
  ▼
Installation Planner
  │
  ├── Native
  ├── Hybrid
  ├── Lightweight
  └── CLI-only
       │
       ▼
Guided Installer
       │
       ▼
Verification
3. Doctor Responsibilities

Doctor is a diagnostic and recommendation engine.

Doctor MUST NOT install packages by default.

Doctor MUST:

inspect hardware,
inspect operating system,
inspect architecture,
inspect ABI,
inspect memory,
inspect storage,
inspect Python,
inspect compiler availability,
inspect build tools,
inspect Rust availability,
inspect network capability,
inspect available inference runtimes,
inspect model compatibility,
inspect Python package compatibility where possible.

Doctor MUST produce machine-readable diagnostic information.

Doctor SHOULD also provide human-readable output.

4. Device Discovery

Doctor SHALL collect:

Hardware
CPU architecture
CPU core count
RAM
storage
available storage
device ABI
Operating System
OS
OS version
kernel version where available
Runtime
Python version
Python implementation
pip version
Build Toolchain
clang
gcc
cmake
make
ninja
rustc
cargo
Networking
network availability
DNS availability
HTTPS connectivity
package index accessibility
RUACH-specific capabilities
llama.cpp availability
existing model files
executable permissions
filesystem capabilities
5. Capability Matrix

Doctor SHALL convert raw discovery information into capabilities.

Example:

Capability                     Status

Python runtime                  PASS
ARM64                           FAIL
ARM32                           PASS
C compiler                      PASS
CMake                           PASS
Ninja                           PASS
Rust                            FAIL
Large native Python wheels      FAIL
llama.cpp compilation           UNKNOWN/PASS/FAIL
Model execution                UNKNOWN/PASS/FAIL

The system MUST distinguish:

AVAILABLE
UNAVAILABLE
UNKNOWN
RESTRICTED
NOT_REQUIRED

A missing capability MUST NOT automatically mean the entire RUACH
installation is impossible.

6. Hard Failures vs Soft Failures

Doctor MUST classify findings.

Hard failure

A hard failure means the required capability for the selected runtime
cannot be satisfied.

Example:

No supported Python runtime

or:

No possible inference runtime
Soft failure

A soft failure means one implementation path is unavailable but another
path may work.

Example:

Rust unavailable

This MUST NOT automatically produce:

RUACH UNSUPPORTED

Instead:

Native dependency path unavailable.

Alternative runtime architectures available.

Recommendation: HYBRID.
7. Installation Modes

RUACH SHALL support multiple installation modes.

7.1 Native Mode

Used when the device can support the complete native RUACH runtime.

Example:

64-bit ARM
adequate RAM
compatible Python
native dependencies available

Architecture:

RUACH
 │
 ├── Python backend
 ├── native dependencies
 └── llama.cpp
7.2 Hybrid Mode

Hybrid MUST be the primary fallback architecture.

Hybrid mode separates components according to device capability.

Example:

┌──────────────────────────┐
│ RUACH Application Layer  │
│ Python / lightweight API │
└─────────────┬────────────┘
              │
              ▼
┌──────────────────────────┐
│ Inference Adapter        │
└─────────────┬────────────┘
              │
              ▼
┌──────────────────────────┐
│ llama.cpp native runtime │
└──────────────────────────┘

The Python application MUST NOT require unnecessary Rust-based native
packages when a simpler implementation is available.

Hybrid mode MAY use:

lightweight Python HTTP server
standard library components
lightweight ASGI configuration
native llama.cpp executable
external model process
subprocess-based inference bridge

The exact implementation SHALL be selected by the capability matrix.

7.3 Lightweight Mode

Used on severely constrained devices.

Characteristics:

minimal Python dependencies
no unnecessary database stack
no unnecessary native extensions
CLI-first operation
llama.cpp or another available inference backend

The system SHOULD prioritize:

reliability > feature completeness
7.4 CLI-only Mode

CLI-only is NOT the default fallback for every unsupported device.

It SHALL be used when:

the API/server architecture cannot be supported,
memory is too limited,
required runtime components cannot coexist,
inference is possible but the service layer is impractical.

CLI-only mode MUST still provide:

ruach chat
ruach doctor
ruach status
ruach model
ruach config
8. Installation Planner

The planner converts Doctor results into an installation plan.

Input:

DeviceCapabilities

Output:

InstallationPlan

Example:

{
  "mode": "hybrid",
  "confidence": "high",
  "backend": "lightweight-python",
  "inference": "llama.cpp",
  "python_strategy": "minimal",
  "native_extensions": false,
  "database": "optional",
  "guided_installation": true
}
9. Planning Rules

The planner SHALL use deterministic rules.

Example:

IF native runtime fully supported
    -> NATIVE

ELSE IF inference runtime supported
     AND lightweight application runtime supported
    -> HYBRID

ELSE IF inference runtime supported
    -> LIGHTWEIGHT

ELSE
    -> UNSUPPORTED

CLI-only MAY be selected when the application layer is not viable but
inference remains viable.

10. ARM32 Strategy

ARM32 devices require special handling.

RUACH MUST NOT assume that modern Python packages provide compatible
native wheels for ARM32 Android.

The installer MUST avoid unnecessary native dependencies.

Particularly problematic dependencies may include packages requiring:

Rust
maturin
native compilation
unsupported ABI wheels

The installer SHOULD prefer:

pure Python
+
existing Termux packages
+
native standalone inference binaries

where technically appropriate.

11. Pydantic-core Strategy

Pydantic-core is a Rust-based native component.

Doctor MUST explicitly detect whether a compatible wheel exists.

The following result:

pydantic-core:
NO COMPATIBLE WHEEL

MUST NOT be interpreted as:

RUACH CANNOT RUN

Instead:

Full Pydantic/FastAPI dependency path unavailable.

Switching to lightweight runtime strategy.

The implementation SHALL provide a dependency profile that does not
require Pydantic-core when the selected runtime does not need it.

12. Uvicorn Strategy

RUACH MUST NOT blindly install:

uvicorn[standard]

on constrained devices.

The standard extra may introduce additional native dependencies.

The installer SHALL first attempt:

uvicorn

without optional native extras.

If even that path is unsuitable, the hybrid runtime MAY use another
lightweight HTTP/service mechanism.

13. Guided Installation

The installer SHALL be interactive when run manually.

Command:

./ruach setup

or:

ruach setup

The installer MUST show the detected device before making major changes.

Example:

╭────────────────────────────────────╮
│          RUACH SETUP                │
╰────────────────────────────────────╯

Device:
  Architecture : ARMv7
  ABI          : armeabi-v7a
  RAM          : 1.8 GB
  Python       : 3.14
  Compiler     : clang ✓
  CMake        : ✓
  Ninja        : ✓
  Rust         : ✗

Analyzing runtime compatibility...

Recommended installation:

  HYBRID RUNTIME

Why?

  • Native Python dependency stack is restricted
  • llama.cpp can provide the inference layer
  • lightweight application runtime is possible

Continue? [Y/n]
14. Installation Confirmation

Before performing destructive or significant actions, the installer
MUST request confirmation.

Example:

The following will be installed:

  ✓ RUACH runtime
  ✓ inference runtime
  ✓ configuration
  ✓ launcher
  ✓ required lightweight dependencies

Estimated storage:
  ~XXX MB

Continue? [Y/n]
15. Installation Steps

The installer SHALL expose progress.

Example:

[1/7] Checking device ............... ✓
[2/7] Selecting runtime ............. ✓
[3/7] Preparing directories ......... ✓
[4/7] Preparing inference runtime ... ✓
[5/7] Installing application layer . ✓
[6/7] Configuring RUACH ............. ✓
[7/7] Running verification .......... ✓

Failures MUST identify the actual cause.

Bad:

Installation failed.

Good:

[5/7] Installing application layer ... FAILED

Reason:
Required native wheel unavailable for ARMv7 Android.

Action:
Switching to HYBRID dependency profile.

Retrying...
16. Recovery

The installer MUST be resumable where possible.

If installation stops at step 5:

./ruach setup

SHOULD detect previously completed steps.

Example:

Existing installation detected.

[1/7] Device check ............. SKIP
[2/7] Runtime selection ........ SKIP
[3/7] Directories .............. ✓
[4/7] Inference runtime ........ ✓
[5/7] Application layer ........ RETRY
17. Doctor CLI

Required commands:

ruach doctor
ruach doctor --verbose
ruach doctor --json
ruach doctor --check-runtime
ruach doctor --check-inference
18. Setup CLI

Required commands:

ruach setup
ruach setup --non-interactive
ruach setup --mode hybrid
ruach setup --mode lightweight
ruach setup --mode cli

The installer MUST validate requested modes against capabilities.

Example:

ruach setup --mode native

on unsupported ARM32 hardware MUST produce:

Native mode is unavailable on this device.

Available modes:

  hybrid
  lightweight
  cli
19. Status Command

Required:

ruach status

Example:

RUACH STATUS

Runtime       : HYBRID
Backend       : READY
Inference     : READY
Model         : Qwen3-0.6B
API           : READY
Storage       : OK

Overall       : READY
20. Configuration

Doctor and installer SHALL share configuration.

Example:

~/.ruach/
├── config/
│   └── ruach.toml
├── models/
├── runtime/
├── logs/
├── cache/
└── state/

The configuration SHALL record:

installation mode
device classification
selected runtime
inference backend
model
dependency profile
installation version
21. Device Classification

RUACH SHALL classify devices into tiers.

Example:

TIER 1
High capability

TIER 2
Standard mobile

TIER 3
Constrained mobile

TIER 4
Minimal device

The exact tier MUST be derived from measured capabilities rather than
device brand alone.

22. Example: ARMv7 / 1.8GB Device

Expected Doctor result:

Architecture : ARMv7
ABI          : armeabi-v7a
RAM          : ~1.8GB

Compiler
  clang      ✓
  cmake      ✓
  make       ✓
  ninja      ✓
  rust       ✗

Python
  Python     ✓
  pip        ✓

Native Python dependency support
  restricted

Inference
  llama.cpp
  capability: TBD by runtime probe

Recommended mode:

  HYBRID

Confidence:

  HIGH

Doctor MUST NOT classify this device as:

UNSUPPORTED

until inference capability has also been proven impossible.

23. Runtime Probe

The installation system MUST perform a small runtime probe before
finalizing the architecture.

The probe SHOULD verify:

executable can start,
inference runtime can load,
model can be opened,
minimal inference can execute.

The probe MUST use the smallest supported model/configuration possible.

The probe MUST avoid exhausting device memory.

24. Memory Safety

RUACH MUST treat memory as a first-class capability.

The installer SHOULD consider:

available RAM
model size
context size
thread count
KV cache requirements
backend overhead

The installer SHOULD reduce resource usage automatically when necessary.

Example:

Low-memory device detected.

Adjusting:

  threads      -> reduced
  context      -> reduced
  model        -> lightweight
25. No Blind Installation

The installer MUST NOT perform:

pip install -r requirements.txt

blindly on every device.

Instead:

Doctor
  ↓
Capability Matrix
  ↓
Dependency Profile
  ↓
Installation

Dependency profiles SHALL be selected dynamically.

26. Dependency Profiles

At minimum:

profiles/
├── native
├── hybrid
├── lightweight
└── cli

The profile determines which dependencies are allowed.

Example:

HYBRID

Required:
  minimal Python runtime
  inference bridge

Avoid:
  unnecessary Rust extensions
  unnecessary native extras
27. Security Requirements

The installer MUST:

avoid executing arbitrary downloaded scripts,
verify downloaded artifacts,
verify SHA-256 hashes where available,
avoid silently modifying unrelated directories,
keep RUACH state under the RUACH directory,
clearly report downloaded artifacts,
never download executable code without verification.
28. Logging

Installation events SHALL be logged.

Example:

~/.ruach/logs/setup.log

Logs MUST include:

timestamp
step
command/category
result
error
runtime selection

Sensitive data MUST NOT be logged.

29. Machine-readable Doctor Output

The JSON output SHALL be suitable for automation.

Example:

{
  "device": {
    "arch": "armv7l",
    "abi": "armeabi-v7a",
    "ram_bytes": 1872060416
  },
  "toolchain": {
    "clang": true,
    "cmake": true,
    "make": true,
    "ninja": true,
    "rust": false
  },
  "python": {
    "available": true,
    "version": "3.14"
  },
  "capabilities": {
    "native_python_extensions": "restricted",
    "inference": "unknown"
  },
  "recommendation": {
    "mode": "hybrid",
    "confidence": "high"
  }
}
30. Architectural Principle

Doctor MUST answer:

"What can this device realistically run?"

NOT:

"Does this device match the developer's original environment?"

This distinction is fundamental to RUACH.

31. Acceptance Criteria

The implementation is complete when:

 Doctor detects CPU architecture.
 Doctor detects ABI.
 Doctor detects RAM.
 Doctor detects storage.
 Doctor detects Python.
 Doctor detects compiler.
 Doctor detects CMake.
 Doctor detects Ninja.
 Doctor detects Rust.
 Doctor detects network capability.
 Doctor detects inference runtime capability.
 Doctor distinguishes hard and soft failures.
 Doctor generates a capability matrix.
 Planner selects runtime mode.
 Hybrid mode exists.
 Lightweight mode exists.
 CLI mode exists.
 Guided installer exists.
 Installer shows progress.
 Installer supports recovery.
 Installer validates selected mode.
 Installer performs runtime verification.
 ruach doctor works.
 ruach doctor --json works.
 ruach setup works.
 ruach status works.
 Installation logs are generated.
 No blind global dependency installation occurs.
32. Final Design Goal

RUACH SHALL behave like an adaptive operating environment.

The user should not need to understand:

ARM ABI problems,
Python wheel compatibility,
Rust build systems,
native extensions,
memory constraints,
inference backend compatibility.

RUACH Doctor determines the constraints.

RUACH Planner determines the architecture.

RUACH Guided Installer performs the setup.

The user receives:

CHECK
  ↓
ANALYZE
  ↓
RECOMMEND
  ↓
CONFIRM
  ↓
INSTALL
  ↓
VERIFY
  ↓
READY

This is the official RUACH device-adaptation and installation model.


