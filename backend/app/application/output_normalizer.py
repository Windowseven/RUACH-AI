"""Model-output normalization (P17 §10/§11).

The single boundary where raw model text becomes application-safe text.
Nothing downstream may see model control tokens; nothing upstream needs
to know a runtime's token quirks.

Design:
- Stop sequences are sent TO the runtime first (llama-server truncates on
  them) - structured stop information is preferred over post-hoc edits.
- What still leaks through as literal characters (small models happily
  emit "</s>" as ordinary tokens mid-text) is removed here, once.
- Reasoning blocks (<think>) are dropped: docs/06 §18 forbids exposing
  them.
- Degenerate repetition is DETECTED here so callers can resample instead
  of showing loops to users.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Control/special tokens observed across Qwen3/ChatML-class models plus the
# generic llama.cpp set. Ordered longest-first so multi-char tokens strip
# completely before shorter prefixes could split them.
CONTROL_TOKENS: tuple[str, ...] = (
    "<|endoftext|>",
    "<|im_end|>",
    "<|im_start|>",
    "<|eos|>",
    "<|eot|>",
    "[/INST]",
    "[INST]",
    "<<SYS>>",
    "<</SYS>>",
    "</s>",
    "<s>",
)

# Sent to llama-server as structured stop strings: generation halts at the
# FIRST occurrence, so the normalizer below is a safety net, not the plan.
STOP_SEQUENCES: tuple[str, ...] = CONTROL_TOKENS

_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>")
_THINK_OPEN = re.compile(r"<think>[\s\S]*")
# Standalone section-header lines (e.g. "### OUTPUT ###") are PROTOCOL
# artifacts: small models copy the header style of the surrounding context
# format. Whole-line matches are stripped; inline text is never touched.
_HEADER_LINE = re.compile(r"^\s*#{2,4}\s*[A-Z][A-Za-z0-9 _-]{0,30}\s*#{2,4}\s*$")


def _strip_header_lines(text: str) -> str:
    kept = [
        line for line in text.splitlines() if not _HEADER_LINE.match(line)
    ]
    return "\n".join(kept)

_RUNS_OF_BLANK = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class NormalizedOutput:
    text: str
    control_tokens_removed: int

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def _strip_reasoning(text: str) -> str:
    stripped = _THINK_BLOCK.sub("", text)
    if "<think>" in stripped:  # unterminated block: reasoning never closed
        stripped = _THINK_OPEN.sub("", stripped)
    return stripped


def normalize(raw: str) -> NormalizedOutput:
    """Raw model output -> user-facing text. Idempotent."""
    removed = sum(raw.count(token) for token in CONTROL_TOKENS)
    cleaned = raw
    for token in CONTROL_TOKENS:
        cleaned = cleaned.replace(token, "")
    cleaned = _strip_reasoning(cleaned)
    cleaned = _strip_header_lines(cleaned)
    # A reasoning block that swallowed everything leaves nothing usable.
    cleaned = _RUNS_OF_BLANK.sub("\n\n", cleaned).strip()
    return NormalizedOutput(text=cleaned, control_tokens_removed=removed)


def is_degenerate(text: str, *, min_lines: int = 4, max_unique: int = 2) -> bool:
    """Detect lock-in loops (template echo, endless fences, token spam).

    Deliberately conservative: only flags when there are enough lines and
    almost no variety. Safe failures stay safe - callers must treat every
    degenerate verdict as 'resample or refuse', never as content.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < min_lines:
        return False
    return len(set(lines)) <= max_unique
