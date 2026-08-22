# RUACH — UI/UX Architecture

**Document:** `09_UI_UX_ARCHITECTURE.md`  
**Version:** 0.1  
**Status:** Draft for approval  
**Scope:** RUACH MVP

---

# 1. Purpose

This document defines the user experience, visual language, interaction model, animation system, and frontend architecture of RUACH MVP.

The purpose is to ensure that RUACH does not become a generic AI web application.

RUACH must feel like:

- a local computing environment
- a personal AI workspace
- technically precise
- visually intentional
- calm
- responsive
- intelligent
- trustworthy

The UI must communicate that RUACH is a system running locally on the user's device.

---

# 2. Core UX Principle

RUACH is not a SaaS dashboard.

It is a:

> **Local AI workspace.**

Therefore the primary user experience is:

```text
Start RUACH
    ↓
System initialization
    ↓
Workspace
    ↓
Conversation
    ↓
Actions
```

The user should not have to navigate through unnecessary application layers before reaching the AI.

---

# 3. Primary User Flow

The default flow is:

```text
ruach start
     ↓
Backend initialization
     ↓
Browser opens
     ↓
Boot Experience
     ↓
Workspace Ready
     ↓
Chat
```

For an already-configured installation:

```text
ruach start
     ↓
Browser
     ↓
Boot / readiness transition
     ↓
Chat Workspace
```

There is no traditional login screen in MVP.

There is no separate dashboard landing page.

The Chat Workspace is the primary application surface.

---

# 4. First-Run Flow

On first launch:

```text
Start
  ↓
First-run detection
  ↓
Welcome
  ↓
Basic configuration
  ↓
Model configuration
  ↓
Security defaults
  ↓
Workspace
```

The first-run experience must be short.

Avoid asking for unnecessary information.

---

# 5. First-Run Welcome

The initial screen should communicate:

```text
RUACH

Your local AI workspace.

Private by default.
Local by design.

[ Begin Setup ]
```

The screen must remain visually minimal.

Do not include:

* feature grids
* pricing
* marketing sections
* testimonials
* social proof
* "10x productivity" claims

RUACH is not a marketing website.

---

# 6. Boot Experience

The boot experience is a signature part of RUACH.

When the browser opens, the user should see a deliberate initialization sequence rather than an empty loading screen.

Conceptually:

```text
                    RUACH

                      ◉

               LOCAL INTELLIGENCE

        ─────────────────────────────

        CORE................... READY
        STORAGE................ READY
        INFERENCE.............. READY
        TOOLS................. LOCKED
        SECURITY............... READY

        ─────────────────────────────

                 INITIALIZING
```

---

# 7. Boot Animation Principle

Boot animation must represent real application state.

The frontend must not display arbitrary fake progress.

For example:

```text
Backend connected
      ↓
Configuration loaded
      ↓
Database ready
      ↓
Inference runtime ready
      ↓
Model available
      ↓
Tool registry loaded
      ↓
Security policy loaded
      ↓
Workspace ready
```

Each state may produce a visual transition.

---

# 8. Boot State Model

The frontend should conceptually support:

```text
BOOTING
CONNECTING
INITIALIZING
READY
DEGRADED
ERROR
```

Example:

```text
BOOTING
   ↓
CONNECTING
   ↓
INITIALIZING
   ↓
READY
```

If a dependency is unavailable:

```text
INITIALIZING
   ↓
DEGRADED
```

The UI should explain what is unavailable.

---

# 9. Boot Failure

If initialization fails, do not show a generic:

```text
Something went wrong.
```

Instead:

```text
RUACH

Unable to initialize inference.

The local model runtime is unavailable.

[ Retry ]

[ View Diagnostics ]
```

Errors should be understandable without exposing internal secrets.

---

# 10. Boot Completion

The transition from boot screen to workspace should be smooth.

Preferred behavior:

```text
Boot
 ↓
final status
 ↓
subtle fade / spatial transition
 ↓
workspace
```

Avoid:

* flashy zoom effects
* excessive particle effects
* screen shaking
* neon effects

Motion should feel like a system becoming ready.

---

# 11. Visual Identity

RUACH must have a distinctive visual identity.

The design language is:

```text
Quiet
Technical
Editorial
Minimal
Cinematic
Precise
Warm
Local
```

The interface should feel designed rather than generated from a UI template.

---

# 12. Anti-Vibe-Coding Rules

The following patterns are prohibited unless explicitly justified:

```text
❌ Purple-blue AI gradients
❌ Generic "AI" neon aesthetics
❌ Excessive glassmorphism
❌ Decorative floating blobs
❌ Excessive rounded cards
❌ Excessive drop shadows
❌ Generic SaaS dashboards
❌ Fake productivity metrics
❌ Unnecessary feature cards
❌ Random glowing borders
❌ Excessive emoji usage
❌ Decorative animations with no purpose
❌ "AI-powered" badges everywhere
```

The UI must not resemble a generated startup landing page.

---

# 13. Color Philosophy

RUACH should use a restrained color system.

Primary visual categories:

```text
Background
Foreground
Muted
Border
Accent
Success
Warning
Danger
```

The interface should use one primary accent rather than multiple competing accent colors.

---

# 14. Color Restrictions

Do not default to:

```text
blue + purple gradient
```

Do not use gradients merely because they are visually fashionable.

Gradients may only be introduced when they have a deliberate design purpose.

---

# 15. Dark Mode

Dark mode should be the primary RUACH visual environment.

The default background should be near-black or deep charcoal rather than pure black everywhere.

Example conceptual hierarchy:

```text
Background
    ↓
Surface
    ↓
Elevated Surface
    ↓
Border
    ↓
Primary Text
    ↓
Secondary Text
```

Depth should primarily come from:

* spacing
* contrast
* borders
* typography

rather than heavy shadows.

---

# 16. Light Mode

Light mode may be supported later.

It must preserve the same visual identity.

Light mode must not become a completely different design language.

---

# 17. Typography

Typography is a major component of RUACH's identity.

The system should use distinct roles:

```text
Display
UI
Body
Technical
```

Technical/system information should use a monospace font.

Examples:

```text
~/projects
runtime: local
status: ready
permission: denied
```

---

# 18. Typography Hierarchy

The interface should communicate hierarchy through typography rather than decorative containers.

Preferred hierarchy:

```text
Page / Workspace title
      ↓
Section title
      ↓
Body
      ↓
Secondary information
      ↓
Metadata
```

Avoid making every element visually loud.

---

# 19. Spacing

Spacing should be systematic.

Use a consistent spacing scale.

Conceptually:

```text
xs
sm
md
lg
xl
2xl
```

Components should not use arbitrary spacing values without reason.

Whitespace is part of the visual identity.

---

# 20. Shape Language

RUACH should avoid excessive rounding.

Use:

```text
small radius
moderate radius
sharp corners
```

based on component purpose.

Not every element should be a pill or highly rounded card.

---

# 21. Borders

Borders should be subtle.

Use borders to establish structure rather than decoration.

Examples:

```text
sidebar boundary
input boundary
tool event boundary
approval boundary
settings sections
```

Avoid glowing borders.

---

# 22. Shadows

Shadows should be restrained.

The preferred hierarchy is:

```text
spacing
+
contrast
+
border
```

before:

```text
large shadow
```

---

# 23. Primary Application Layout

The main RUACH workspace consists of:

```text
┌────────────────────────────────────────────────────┐
│ Top Bar                                             │
├───────────────┬────────────────────────────────────┤
│               │                                    │
│ Sidebar       │        Conversation Area           │
│               │                                    │
│               │                                    │
│               │                                    │
│               │                                    │
│               ├────────────────────────────────────┤
│               │        Composer / Input            │
└───────────────┴────────────────────────────────────┘
```

---

# 24. Sidebar

The sidebar provides navigation.

Primary items:

```text
+ New Chat

Conversations

Today
Yesterday
Previous
```

Secondary items:

```text
Settings
System Status
```

The sidebar should remain visually quiet.

---

# 25. Sidebar Behavior

The sidebar should support:

```text
expanded
collapsed
mobile drawer
```

Desktop:

```text
Sidebar + Chat
```

Small screens:

```text
Chat
 +
drawer
```

---

# 26. Conversation History

Conversation history should be organized chronologically.

Example:

```text
TODAY

Build RUACH API
Python setup
System architecture

YESTERDAY

Linux permissions
Termux tools
```

Avoid excessive metadata.

---

# 27. New Chat

The New Chat action should be immediately accessible.

When selected:

```text
Current conversation
       ↓
New conversation
       ↓
Empty chat state
```

The user should not encounter an unnecessary confirmation dialog.

---

# 28. Empty Chat State

The empty workspace should be minimal.

Example:

```text
                    RUACH

             What are we working on?

        ┌───────────────────────────────┐
        │ Ask Ruach...                  │
        └───────────────────────────────┘
```

Optional suggestions may appear:

```text
Explore my files
Explain something
Help me build
Inspect the project
```

Suggestions must not dominate the screen.

---

# 29. Chat Composer

The message composer is one of the most important components.

It should support:

```text
text input
send
multiline input
keyboard shortcuts
disabled state
loading state
```

Potential future capabilities:

```text
attachments
tool context
model selection
```

These should not clutter the MVP composer.

---

# 30. Composer Design

The composer should feel like a workspace instrument.

Avoid making it look like a generic:

```text
"Ask AI anything..."
```

marketing input.

The interface should prioritize:

```text
space
typing
clarity
send action
```

---

# 31. Message Design

User and assistant messages should be visually distinct without relying on giant cards.

Prefer:

```text
User
────────────────────────

message

RUACH
────────────────────────

response
```

rather than:

```text
┌───────────────┐
│ User message  │
└───────────────┘

┌───────────────┐
│ AI response   │
└───────────────┘
```

The conversation should feel editorial and readable.

---

# 32. Assistant State

RUACH should visually communicate:

```text
idle
thinking
streaming
tool request
tool execution
complete
error
```

---

# 33. Thinking State

Avoid generic animated bouncing dots when possible.

A subtle RUACH system indicator may be used.

Conceptually:

```text
idle:
◉

thinking:
◌

streaming:
◉

tool:
◉ →

error:
◉ !
```

Animation should remain subtle.

---

# 34. Streaming

When the model streams a response:

```text
assistant message
      ↓
content appears progressively
```

The UI should not jump around as text arrives.

Reserve enough layout stability to avoid excessive movement.

---

# 35. Tool Request UI

Tool requests must be visually distinct from normal conversation.

Example:

```text
┌─────────────────────────────────────┐
│ TOOL REQUEST                        │
│                                     │
│ filesystem.list_directory           │
│                                     │
│ ~/projects                          │
│                                     │
│ Status: awaiting policy             │
└─────────────────────────────────────┘
```

---

# 36. Tool Execution UI

After approval:

```text
TOOL

filesystem.list_directory

~/projects

EXECUTING...
```

Then:

```text
COMPLETED
42ms
```

Tool execution should feel like a system operation.

---

# 37. Tool Approval UI

Dangerous actions require explicit approval.

Example:

```text
┌──────────────────────────────────────────┐
│ ACTION REQUIRES APPROVAL                 │
│                                          │
│ shell.execute                            │
│                                          │
│ rm ./old-project                         │
│                                          │
│ RISK                                     │
│ HIGH                                     │
│                                          │
│ This action may permanently delete data. │
│                                          │
│ [ DENY ]                 [ APPROVE ]     │
└──────────────────────────────────────────┘
```

The UI must clearly communicate:

* tool
* operation
* target
* risk
* consequence
* available action

---

# 38. Approval Principle

The approval UI must not manipulate the user into approving an action.

Avoid:

```text
[ Continue ]
```

when the actual meaning is:

```text
Approve dangerous operation
```

Use explicit language.

---

# 39. Denial State

When denied:

```text
ACTION DENIED

The requested operation was not executed.
```

The interface must never imply that the action partially succeeded.

---

# 40. Tool Failure

Example:

```text
TOOL FAILED

filesystem.read_file

Reason:
Permission denied.

No changes were made.
```

Where known, communicate whether any side effects occurred.

---

# 41. Security Status

RUACH should expose a simple security status.

Example:

```text
LOCAL
● SECURE
```

or:

```text
TOOLS
RESTRICTED
```

The indicator must not falsely claim that the entire system is "secure" merely because security features exist.

---

# 42. System Status

A system status view may display:

```text
RUACH STATUS

API             READY
DATABASE        READY
INFERENCE       READY
MODEL           READY
TOOLS           RESTRICTED
SECURITY        READY
```

This is useful for a local application because the user may need to diagnose their own installation.

---

# 43. Settings

Settings should be organized by responsibility.

Recommended:

```text
Settings

General
Model
Inference
Tools
Security
Storage
About
```

---

# 44. General Settings

Possible MVP settings:

```text
Display
Theme
Language
Startup behavior
```

Avoid excessive personalization controls in MVP.

---

# 45. Model Settings

Model settings may show:

```text
Model
Runtime
Context length
Temperature
```

The UI must distinguish between:

```text
configured
available
loaded
```

These are not necessarily the same state.

---

# 46. Inference Settings

Potential information:

```text
Runtime
Model path
Context
Threads
Temperature
Token limits
```

Advanced settings should be visually separated from normal settings.

---

# 47. Tool Settings

Tools should have explicit states.

Example:

```text
Filesystem
RESTRICTED

Shell
DISABLED

Network
DISABLED
```

Do not use ambiguous toggles such as:

```text
AI power
ON
```

---

# 48. Security Settings

Security settings must clearly communicate consequences.

Example:

```text
Tool approvals
Required

Filesystem access
Restricted

Network access
Disabled

Shell execution
Disabled
```

Security should not be hidden in a generic "Advanced" menu.

---

# 49. Storage Settings

Potential information:

```text
Database location
Database size
Conversation count
Model storage
```

Actions:

```text
Export data
Backup
Clear conversation
```

Destructive actions require confirmation.

---

# 50. Destructive Confirmation

Do not use:

```text
Are you sure?
```

alone.

Use:

```text
DELETE CONVERSATION?

This permanently removes the selected conversation.

[ Cancel ] [ Delete ]
```

For highly destructive operations, require explicit confirmation.

---

# 51. Notifications

RUACH should avoid notification spam.

Use notifications only for:

```text
important system state
tool completion where useful
critical errors
```

Avoid:

```text
"AI is thinking..."
```

toast notifications.

---

# 52. Loading States

Every asynchronous UI operation should have an intentional loading state.

Examples:

```text
Booting
Loading conversation
Sending
Streaming
Executing tool
Saving
```

Avoid generic indefinite spinners where a more meaningful state can be communicated.

---

# 53. Skeletons

Skeleton loading may be used for content-heavy interfaces.

However:

> Do not use skeletons simply because modern web apps use them.

For RUACH's compact local interface, simple state transitions may often be better.

---

# 54. Error States

Errors should answer:

```text
What happened?
What does it mean?
What can I do?
```

Example:

```text
MODEL UNAVAILABLE

RUACH could not reach the local inference runtime.

Check that the runtime is installed and running.

[ Retry ]

[ View Diagnostics ]
```

---

# 55. Offline State

If the browser loses connection to the local backend:

```text
RUACH OFFLINE

The local server is unavailable.

Your existing conversations remain available locally where cached.

[ Reconnect ]
```

The UI should distinguish:

```text
internet unavailable
```

from:

```text
local RUACH backend unavailable
```

These are different conditions.

---

# 56. Accessibility

Accessibility is mandatory.

The UI should support:

```text
keyboard navigation
visible focus
semantic HTML
screen-reader labels
sufficient contrast
reduced motion
```

---

# 57. Reduced Motion

If the operating system requests reduced motion:

```text
prefers-reduced-motion
```

RUACH should reduce or disable non-essential animation.

Important state transitions must remain understandable without animation.

---

# 58. Keyboard First

RUACH is a developer-oriented local tool.

Keyboard interaction should be first-class.

Potential shortcuts:

```text
Enter
Send

Shift + Enter
New line

Cmd/Ctrl + K
Focus search / command interface

Cmd/Ctrl + N
New chat

Esc
Close drawer / modal
```

Exact shortcuts should be finalized during implementation.

---

# 59. Responsive Design

RUACH must work on:

```text
desktop
tablet
mobile
```

The primary target remains the local browser on the user's device.

---

# 60. Mobile Layout

On mobile:

```text
┌───────────────────────────┐
│ RUACH              ☰      │
├───────────────────────────┤
│                           │
│       Conversation        │
│                           │
│                           │
│                           │
├───────────────────────────┤
│ Ask Ruach...          ↑   │
└───────────────────────────┘
```

The sidebar becomes a drawer.

---

# 61. Touch Interaction

Touch targets must be sufficiently large.

Avoid tiny controls that are difficult to use on Android.

---

# 62. Animation Philosophy

Animation must communicate:

```text
state
relationship
progress
feedback
```

Animation must not exist merely to impress.

---

# 63. Animation Rules

Preferred:

```text
fade
slide
opacity transition
small scale transition
typing/streaming motion
state morphing
```

Avoid:

```text
large bouncing elements
constant floating animations
parallax everywhere
particle backgrounds
excessive blur
```

---

# 64. Animation Timing

Animations should generally be short and purposeful.

Conceptual ranges:

```text
micro interaction:
100–180ms

normal transition:
180–300ms

major transition:
300–500ms
```

Long animations should be rare.

---

# 65. Boot Animation Timing

Boot timing must follow actual backend readiness.

If initialization is fast:

```text
do not artificially delay startup for aesthetics
```

If initialization takes time:

```text
show meaningful progress/state
```

User experience must not be slowed purely to make the animation look impressive.

---

# 66. Motion Hierarchy

Motion should have levels:

```text
Level 1
micro interaction

Level 2
component transition

Level 3
system state transition
```

Level 3 motion should be rare and meaningful.

---

# 67. Visual Feedback

Every important user action should produce feedback.

Examples:

```text
Send
 ↓
message appears

Save
 ↓
saved indicator

Approve
 ↓
tool begins execution

Deny
 ↓
tool blocked

Retry
 ↓
system reconnecting
```

---

# 68. No Fake Activity

The interface must never pretend to perform work that the backend is not performing.

Do not display:

```text
Analyzing...
Searching...
Thinking...
```

unless the system is actually performing the corresponding operation.

---

# 69. Locality as a UX Concept

RUACH's local-first architecture should be visible in the UX.

The user should be able to understand:

```text
Where is my data?
Where is inference happening?
What can access my files?
Is network access enabled?
```

without reading source code.

---

# 70. Privacy Indicator

The UI may provide a subtle indication:

```text
LOCAL
```

or:

```text
LOCAL INFERENCE
```

when inference is local.

If remote inference is ever introduced:

> The UI must explicitly distinguish remote from local inference.

---

# 71. No Dark Patterns

RUACH must never use UI patterns that encourage unsafe actions.

Especially for:

```text
tool approval
filesystem access
network access
shell execution
data deletion
```

The safest action should not be visually hidden.

---

# 72. Component Philosophy

Components should be created based on repeated behavior.

Do not create a component for every tiny visual fragment.

Good candidates:

```text
BootScreen
Workspace
Sidebar
ConversationList
Message
Composer
ToolRequest
ApprovalDialog
SystemStatus
SettingsPanel
```

---

# 73. Component Boundaries

A component should have:

```text
clear responsibility
clear inputs
clear outputs
predictable state
```

Avoid giant components containing the entire application.

---

# 74. Frontend State

Frontend state should be divided conceptually into:

```text
UI State
Server State
Conversation State
Connection State
System State
```

Do not place everything into one global state object.

---

# 75. Connection State

The frontend should know whether the backend is:

```text
connecting
connected
disconnected
reconnecting
error
```

This is especially important because RUACH is a local web application.

---

# 76. API Boundary

Frontend communicates through the API contract.

The frontend must not directly access:

```text
SQLite
filesystem
Python
Termux
model runtime
```

---

# 77. Frontend Security

Never trust frontend state as a security boundary.

For example:

```text
frontend says:
tool approved
```

does NOT mean:

```text
backend may execute tool
```

The backend must independently verify authorization.

---

# 78. Tool Approval Security

The frontend approval action should communicate intent to the backend.

The backend must verify:

```text
approval exists
approval belongs to request
approval is not expired
approval is valid
policy still permits execution
```

before execution.

---

# 79. Data Persistence

The frontend should not become the primary source of truth for conversations.

Primary persistence belongs to the backend/database.

Frontend caching may exist for UX.

---

# 80. Design Tokens

The UI should define centralized design tokens.

Conceptually:

```text
colors
spacing
typography
radius
borders
motion
z-index
```

Components should consume tokens rather than inventing values.

---

# 81. Design Token Example

Conceptual structure:

```text
--color-background
--color-surface
--color-surface-elevated
--color-text
--color-text-muted
--color-border
--color-accent
--color-success
--color-warning
--color-danger
```

Exact values belong to implementation.

---

# 82. CSS Philosophy

CSS should prioritize:

```text
clarity
consistency
maintainability
responsive behavior
```

Avoid excessive utility-class complexity if it makes the visual system difficult to understand.

---

# 83. Frontend Framework Rule

A frontend framework may be introduced only if it meaningfully improves:

```text
state management
component architecture
routing
testing
maintainability
```

The framework must not dictate the UX.

---

# 84. No Premature Design System

RUACH should not build a 200-component design system for MVP.

Build only the components actually needed.

---

# 85. Visual Testing

Important UI states should be manually inspected.

At minimum:

```text
first run
boot
ready
empty chat
conversation
streaming
tool request
approval
denial
tool failure
backend disconnected
settings
mobile layout
```

---

# 86. Browser Compatibility

The frontend should prioritize modern browsers available on the target device.

Do not introduce unnecessary compatibility layers unless required.

---

# 87. Performance

The UI should remain lightweight.

Avoid:

```text
large JavaScript libraries
heavy animation frameworks
unnecessary image assets
large background videos
excessive client-side state
```

The interface should load quickly on mobile hardware.

---

# 88. Asset Philosophy

RUACH should use a small number of intentional assets.

Avoid:

```text
stock illustrations
generic AI robot images
random abstract gradients
decorative 3D blobs
```

Typography, spacing, and motion should provide most of the visual identity.

---

# 89. Logo / Mark

RUACH should have a simple visual mark.

The mark should work:

```text
large
small
favicon
sidebar
boot screen
```

It should not depend on complex gradients or detailed illustrations.

---

# 90. Iconography

Use one consistent icon family.

Icons should:

```text
communicate function
remain subtle
have consistent stroke/weight
```

Avoid mixing unrelated icon styles.

---

# 91. Empty States

Empty states should be useful but quiet.

Example:

```text
No conversations yet.

Start with a question, idea, or task.
```

Do not fill empty states with promotional copy.

---

# 92. Success States

Success feedback should be restrained.

Example:

```text
Saved
```

or:

```text
Completed · 42ms
```

Avoid giant celebratory animations for routine operations.

---

# 93. Error Severity

Errors should have severity levels:

```text
INFO
WARNING
ERROR
CRITICAL
```

Visual intensity should correspond to actual severity.

---

# 94. System Events

System events may appear in the conversation timeline when relevant.

Example:

```text
SYSTEM

Inference runtime restarted.
```

They should be visually distinct from user and assistant messages.

---

# 95. Conversation Continuity

When reopening RUACH:

```text
Start
 ↓
Boot
 ↓
last active workspace
```

The user should not lose context unnecessarily.

---

# 96. Startup Behavior

After the initial setup, startup should normally open directly into:

```text
last active conversation
```

or:

```text
new chat
```

depending on configuration.

Default should favor continuity.

---

# 97. No Mandatory Dashboard

RUACH MVP does not require:

```text
Dashboard
Overview
Analytics
Statistics
Usage charts
```

unless a future requirement explicitly introduces them.

The conversation workspace is the primary home.

---

# 98. Information Hierarchy

The UI hierarchy should be:

```text
1. Current task
2. Conversation
3. System state
4. Available actions
5. Configuration
6. Diagnostics
```

Do not prioritize decorative information over the user's current task.

---

# 99. UX for AI Uncertainty

When RUACH is uncertain, the UI should allow the assistant to communicate uncertainty naturally.

Example:

```text
I'm not certain which project you mean.

Did you mean:

lespikius-dev
ruach
linux-buddy
```

Do not fabricate certainty through UI language.

---

# 100. UX for Tool Intent

When RUACH wants to use a tool, the UI should make the transition understandable:

```text
User request
     ↓
RUACH interpretation
     ↓
Tool request
     ↓
Policy decision
     ↓
Approval if required
     ↓
Execution
     ↓
Result
```

This creates transparency.

---

# 101. Tool Transparency

When a tool is used, the user should be able to see:

```text
which tool
what operation
target
result
```

where disclosure is safe.

---

# 102. Conversation vs System UI

Normal conversation:

```text
User
RUACH
```

System operations:

```text
TOOL
SYSTEM
SECURITY
```

should have distinguishable visual treatment.

This prevents the user from confusing AI-generated text with actual system state.

---

# 103. Security-Critical UI

Security-critical actions must use explicit visual hierarchy.

Example:

```text
SECURITY ACTION

Network access requested.

Destination:
example.com

Risk:
MEDIUM

[ DENY ] [ APPROVE ]
```

The UI must never obscure the target.

---

# 104. Network State

Because RUACH is local-first, network state should be visible where relevant.

Possible states:

```text
NETWORK
DISABLED

NETWORK
AVAILABLE

NETWORK
IN USE
```

Do not imply that "local" means the application cannot communicate externally if network tools are enabled.

---

# 105. Model State

Model status may be represented as:

```text
MODEL
READY
```

or:

```text
MODEL
NOT LOADED
```

or:

```text
MODEL
UNAVAILABLE
```

The user should understand whether RUACH can currently answer requests.

---

# 106. Degraded Mode

RUACH may remain usable when optional components are unavailable.

Example:

```text
Inference:
READY

Tools:
DISABLED
```

The UI should communicate degraded functionality rather than completely failing when possible.

---

# 107. Architecture Principle

The frontend is a presentation and interaction layer.

It must not become the source of:

```text
security policy
business rules
tool authorization
database authority
inference authority
```

---

# 108. UI/UX Development Workflow

Frontend implementation should follow:

```text
UX requirement
   ↓
Wireframe
   ↓
Interaction definition
   ↓
Design tokens
   ↓
Component
   ↓
State handling
   ↓
Accessibility
   ↓
Responsive behavior
   ↓
Visual review
```

---

# 109. AI Coding Agent UI Rules

When OpenCode implements frontend work, it must:

1. Read this document first.
2. Reuse existing design tokens.
3. Inspect existing components before creating new ones.
4. Avoid introducing unnecessary dependencies.
5. Avoid generic AI visual patterns.
6. Implement loading and error states.
7. Implement responsive behavior.
8. Preserve accessibility.
9. Test important interaction states.
10. Report visual assumptions.

---

# 110. UI Acceptance Criteria

A frontend feature is not complete until:

```text
[ ] Functional behavior works
[ ] Loading state exists
[ ] Error state exists where applicable
[ ] Empty state exists where applicable
[ ] Mobile behavior is considered
[ ] Keyboard behavior works
[ ] Accessibility is considered
[ ] Animation is intentional
[ ] Design tokens are reused
[ ] No unnecessary visual noise
[ ] No generic AI gradient aesthetic
```

---

# 111. Visual Quality Gate

Before accepting a significant UI change, ask:

```text
Does this look like RUACH?
```

If removing the RUACH logo makes the interface look like any generic AI application:

> The design is not distinctive enough.

---

# 112. Anti-Generic Test

A design should survive this test:

> "If I replace the RUACH name with another AI product name, does the interface still look exactly the same?"

If yes:

> Reconsider the design.

RUACH should have its own visual language.

---

# 113. Performance vs Beauty

Visual quality must not come at the expense of usability.

Priority:

```text
Function
   ↓
Clarity
   ↓
Performance
   ↓
Accessibility
   ↓
Visual polish
```

All five matter.

---

# 114. Final UX Philosophy

RUACH should feel:

```text
quiet when idle
alive when working
clear when asking
precise when acting
obvious when failing
serious when dangerous
```

It should not constantly demand attention.

---

# 115. Final Principle

RUACH is not trying to look futuristic.

It is trying to look:

> **intentional.**

The interface should communicate intelligence through:

```text
clarity
motion
feedback
typography
spacing
system transparency
```

not through:

```text
gradients
glows
cards
badges
marketing language
```

The final visual principle is:

> **Less decoration. More character.**

---

# 116. UI/UX Invariants

Unless explicitly changed through an architecture decision:

1. Chat is the primary RUACH workspace.
2. There is no mandatory login in MVP.
3. There is no separate dashboard landing page.
4. First-run setup is lightweight.
5. Browser startup includes a meaningful boot/readiness experience.
6. Boot progress reflects real system state.
7. Dark mode is the primary visual environment.
8. The color palette remains restrained.
9. Purple-blue AI gradients are not the default visual language.
10. Animation must communicate meaningful state.
11. Accessibility is mandatory.
12. Security-sensitive actions require explicit UI communication.
13. Tool execution must be visually distinguishable from normal conversation.
14. The frontend is not a security boundary.
15. The frontend does not directly access system resources.
16. UI components must follow centralized design tokens.
17. Mobile usability is required.
18. Visual complexity must not be introduced without purpose.
19. RUACH must maintain a distinctive visual identity.
20. The interface must prioritize clarity over decoration.

---

# 117. Final Design Statement

RUACH should open like a system.

It should behave like a workspace.

It should communicate like an assistant.

It should act like a controlled computer interface.

And it should look like nothing else we have built before.

> **RUACH is not another AI dashboard.**
>
> **It is a local intelligence workspace.**
