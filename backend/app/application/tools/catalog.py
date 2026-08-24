"""Centralized capability catalog (P17 §6).

ONE authoritative description per registered capability: purpose, when to
use, when NOT to use, argument semantics, failure behavior. The system
prompt renders from here, and tests pin catalog completeness against
CAPABILITY_RISK so a new capability cannot ship undescribed.

Descriptions must generalize ("never invent a filename from ordinary
conversational text") - they are not tuned to any specific failing prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.tools.policy import CAPABILITY_RISK


@dataclass(frozen=True)
class CapabilityDoc:
    capability: str
    summary: str  # purpose + when to use
    avoid: str  # when NOT to use
    arguments: str  # argument semantics
    failure: str  # failure behavior


CAPABILITIES: dict[str, CapabilityDoc] = {
    "filesystem.read": CapabilityDoc(
        capability="filesystem.read",
        summary=(
            "Read the contents of an existing file inside the workspace when "
            "the user explicitly asks for that file's contents."
        ),
        avoid=(
            "Never use it for greetings, casual conversation, questions about "
            "yourself, or general knowledge. Never invent a filename from "
            "ordinary conversational text."
        ),
        arguments='{"path": "relative/path.txt"} - relative to the user\'s '
        "workspace; the file must already exist.",
        failure=(
            "Fails if the file does not exist or is unreadable; the failure "
            "is reported honestly to the user."
        ),
    ),
    "filesystem.list": CapabilityDoc(
        capability="filesystem.list",
        summary=(
            "List the files in a workspace folder when the user explicitly "
            "asks what files exist there."
        ),
        avoid=(
            "Never use it for conversation or questions that do not involve "
            "the user's actual files."
        ),
        arguments='{"path": "."} - folder path relative to the workspace; '
        '"." lists the workspace root.',
        failure="Fails if the folder does not exist.",
    ),
    "filesystem.write": CapabilityDoc(
        capability="filesystem.write",
        summary=(
            "Create or overwrite a workspace file with content when the user "
            "explicitly requests creating or changing that file."
        ),
        avoid=(
            "Never use it unless the user asked to create, save, or change a "
            "file. Never invent writes to 'answer' conversational messages."
        ),
        arguments='{"path": "relative/path.txt", "content": "text to write"} '
        "- existing files at that path are overwritten.",
        failure="Fails if the path is invalid or unwritable.",
    ),
    "filesystem.delete": CapabilityDoc(
        capability="filesystem.delete",
        summary=(
            "Delete an existing workspace file when the user explicitly "
            "requests deleting that file."
        ),
        avoid=(
            "Never use it unless the user explicitly asked for deletion; "
            "deletion always requires explicit human approval."
        ),
        arguments='{"path": "relative/path.txt"} - the file must exist.',
        failure=(
            "Fails if the file does not exist. Requires human approval "
            "before execution."
        ),
    ),
}


def render_capability_guidance() -> str:
    """Render the catalog as model-facing tool guidance."""
    blocks = []
    for name in sorted(CAPABILITIES):
        doc = CAPABILITIES[name]
        approval_note = (
            " Requires human approval." if _needs_approval(name) else ""
        )
        blocks.append(
            f"- {name}{approval_note}\n"
            f"  Purpose/use: {doc.summary}\n"
            f"  Do NOT use: {doc.avoid}\n"
            f"  Arguments: {doc.arguments}\n"
            f"  Failure behavior: {doc.failure}"
        )
    return "\n".join(blocks)


def _needs_approval(capability: str) -> bool:
    from app.application.tools.schemas import RiskLevel

    return CAPABILITY_RISK.get(capability, RiskLevel.SENSITIVE) >= RiskLevel.DESTRUCTIVE
