import json
import re

from app.application.context import USER_SENTINEL
from app.application.inference import InferenceHealth

_READ = re.compile(r"^\s*(?:please\s+)?(?:read|show me|open)\s+(\S+)\s*$", re.IGNORECASE)
_DELETE = re.compile(r"^\s*(?:please\s+)?delete\s+(\S+)\s*$", re.IGNORECASE)
_NAME_SET = re.compile(r"my name is ([A-Za-z][\w-]*)", re.IGNORECASE)
_NAME_ASK = re.compile(r"what(?:'s| is) my name", re.IGNORECASE)
_PROJECT_FILE = re.compile(r"project file is ([\w.\-/]+)", re.IGNORECASE)
_RESULT = re.compile(r'"result":\s*"([^"]{0,120})')


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
    """Deterministic protocol + memory test double.

    Answers are derived ONLY from the prompt it receives, so every memory
    test proves that the ContextBuilder actually put the required history
    in front of the inference port. Rules:

    - "My name is X" in history + "what is my name?" -> replies X
    - "project file is Y" in history + "read the project file" ->
      well-formed filesystem.read proposal for Y
    - a tool result in history + "what did the file say?" -> quotes result
    - direct read/delete commands -> proposals (protocol check)
    - anything else -> echo (proves turn isolation of non-matching text)
    """

    def complete(self, prompt: str) -> str:
        if "(continuation)" in prompt.splitlines()[0]:
            return "Here is what happened: the action completed as requested."

        user_text = (
            prompt.rsplit(USER_SENTINEL, 1)[1].strip()
            if USER_SENTINEL in prompt
            else prompt
        )

        if _NAME_ASK.search(user_text):
            names = _NAME_SET.findall(prompt)
            if names:
                return f"Your name is {names[-1]}."
            return "I do not know your name."

        if "project file" in user_text.lower():
            match = _PROJECT_FILE.search(prompt)
            if match is not None and _READ.match(user_text) or (
                match is not None and "read" in user_text.lower()
            ):
                return _proposal("filesystem.read", match.group(1).rstrip("."))

        if _READ.match(user_text):
            return _proposal("filesystem.read", _READ.match(user_text).group(1))  # type: ignore[union-attr]
        if _DELETE.match(user_text):
            return _proposal("filesystem.delete", _DELETE.match(user_text).group(1))  # type: ignore[union-attr]

        if re.search(r"what did the file say", user_text, re.IGNORECASE):
            results = _RESULT.findall(prompt)
            if results:
                return f"The file said: {results[-1]}"
            return "I have no file contents to quote."

        return f"[stub] You said: {user_text}"

    def health(self) -> InferenceHealth:
        return "ready"
