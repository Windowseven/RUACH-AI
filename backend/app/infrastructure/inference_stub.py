import json
import re

from app.application.inference import InferenceHealth

_SENTINEL = "### USER MESSAGE ###"
_READ = re.compile(r"^\s*(?:please\s+)?(?:read|show me|open)\s+(\S+)\s*$", re.IGNORECASE)
_DELETE = re.compile(r"^\s*(?:please\s+)?delete\s+(\S+)\s*$", re.IGNORECASE)


def _proposal(capability: str, path: str) -> str:
    payload = json.dumps(
        {
            "tool": "filesystem",
            "capability": capability,
            "arguments": {"path": path},
        }
    )
    return f"<tool_request>{payload}</tool_request>"


class StubInference:
    """Deterministic protocol test double for the orchestrator contract.

    Recognises a tiny command grammar in the user message and answers with
    well-formed tool proposals, so the full orchestration loop can be tested
    without a model server. Any other input is echoed as plain prose.
    """

    def complete(self, prompt: str) -> str:
        if "(continuation)" in prompt.splitlines()[0]:
            return "Here is what happened: the action completed as requested."
        if _SENTINEL not in prompt:
            return f"[stub] You said: {prompt}"
        user_text = prompt.rsplit(_SENTINEL, 1)[1].strip()
        match = _READ.match(user_text)
        if match is not None:
            return _proposal("filesystem.read", match.group(1))
        match = _DELETE.match(user_text)
        if match is not None:
            return _proposal("filesystem.delete", match.group(1))
        return f"[stub] You said: {user_text}"

    def health(self) -> InferenceHealth:
        return "ready"
