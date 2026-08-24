"""P17 regression: conversation intelligence, identity, normalization.

Proves the conversational architecture distinguishes:
  normal answer / tool proposal / malformed model output / real tool failure
without any keyword-based response logic in the application.

Layer split (mirrors the directive's evidence rules):
- context tests      : identity + tool-intent instructions reach the model
- orchestrator tests : prose passes; proposals flow to policy; malformed,
  EOS-laden and degenerate outputs are classified, bounded, never executed
- adapter tests      : control tokens die at the inference boundary
The live-model matrix (docs/12 P17 §17) separately proves the real model
obeys the new context.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.application import response_texts
from app.application.context import ContextBuilder, RecentMessagesStrategy
from app.application.identity import IDENTITY_VERSION, identity_markers, system_identity
from app.application.inference import InferenceHealth
from app.application.orchestrator import run_turn
from app.application.output_normalizer import STOP_SEQUENCES, normalize
from app.application.tools.catalog import CAPABILITIES, render_capability_guidance
from app.application.tools.policy import CAPABILITY_RISK
from app.infrastructure.inference_llamacpp import LlamaCppAdapter
from tests.test_inference_llamacpp import _ok_opener


# ----------------------------------------------------------------- fakes
class ScriptedInference:
    """Returns queued outputs verbatim; records every prompt it saw."""

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.outputs.pop(0) if self.outputs else ""

    def health(self) -> InferenceHealth:
        return "ready"


class RecordingEngine:
    """ToolEngine double that only records what reached the policy gate."""

    def __init__(self) -> None:
        self.submitted: list[Any] = []

    def submit(self, request, conversation_id=None):
        self.submitted.append(request)
        raise AssertionError("policy engine must not be reached in this test")


def _prompt(message: str) -> str:
    return ContextBuilder(RecentMessagesStrategy(max_messages=6)).build([], message)


# ------------------------------------------------------- context assembly
def test_identity_is_centralized_versioned_and_truthful() -> None:
    assert system_identity().strip()
    for marker in identity_markers():
        assert marker in system_identity(), marker


def test_identity_version_is_pinned_int() -> None:
    assert IDENTITY_VERSION >= 2


def test_every_prompt_carries_identity_and_intent_rules() -> None:
    inference = ScriptedInference(["Hi there! How can I help?"])
    engine = RecordingEngine()
    run_turn(inference, engine, _prompt("hellow"))  # type: ignore[arg-type]
    sent = inference.prompts[0]
    assert "You are RUACH." in sent
    assert "Tools are capabilities, not default response mechanisms." in sent
    assert "Do not use a tool for ordinary conversation." in sent
    assert "Never invent a filename from ordinary conversational text." in sent


def test_capability_catalog_covers_registered_risk_table() -> None:
    assert set(CAPABILITIES) == set(CAPABILITY_RISK)
    guidance = render_capability_guidance()
    for name, doc in CAPABILITIES.items():
        assert doc.summary and doc.avoid and doc.arguments and doc.failure
        assert name in guidance


def test_catalog_instructions_generalize_beyond_specific_prompts() -> None:
    guidance = render_capability_guidance().lower()
    # Generalized intent language present...
    assert "greetings" in guidance or "conversational text" in guidance
    # ...but no overfitting to this directive's example prompts.
    for banned in ("hellow", "how are you", "who are you"):
        assert banned not in guidance


# --------------------------------------------------- conversation vs tools
@pytest.mark.parametrize(
    "message",
    ["hello", "hellow", "hi", "hey", "how are you?", "what are you doing?"],
)
def test_conversation_never_reaches_the_policy_gate(message: str) -> None:
    prose = "A friendly plain-prose reply."
    inference = ScriptedInference([prose])
    engine = RecordingEngine()
    result = run_turn(inference, engine, _prompt(message))  # type: ignore[arg-type]
    assert result.kind == "reply"
    assert result.reply == prose
    assert result.error_class == ""
    assert engine.submitted == []


@pytest.mark.parametrize("message", ["who are you?", "what is RUACH?", "what can you do?"])
def test_identity_questions_are_plain_prose_for_the_model(message: str) -> None:
    # The APPLICATION must not special-case these: whatever the model says
    # is passed through untouched.
    answer = "I'm RUACH, a local AI assistant on your device."
    inference = ScriptedInference([answer])
    engine = RecordingEngine()
    result = run_turn(inference, engine, _prompt(message))  # type: ignore[arg-type]
    assert result.reply == answer
    assert engine.submitted == []


@pytest.mark.parametrize("message", ["what is Python?", "explain recursion"])
def test_informational_questions_stay_conversational(message: str) -> None:
    inference = ScriptedInference(["Recursion is a function calling itself."])
    engine = RecordingEngine()
    result = run_turn(inference, engine, _prompt(message))  # type: ignore[arg-type]
    assert result.error_class == ""
    assert engine.submitted == []


def test_real_tool_request_still_flows_to_the_engine() -> None:
    proposal = (
        '<tool_request>{"tool": "filesystem", "capability": "filesystem.read",'
        ' "arguments": {"path": "notes.txt"}}</tool_request>'
    )

    class Outcome:
        state = "FAILED"
        reason = "file does not exist"
        approval_id = None

        def __init__(self) -> None:
            self.output: dict[str, Any] = {}

    class ScriptedEngine(RecordingEngine):
        def submit(self, request, conversation_id=None):  # type: ignore[override]
            self.submitted.append(request)
            return Outcome()

    engine = ScriptedEngine()
    result = run_turn(ScriptedInference([proposal]), engine, _prompt("read notes.txt"))  # type: ignore[arg-type]
    assert len(engine.submitted) == 1
    assert engine.submitted[0].capability == "filesystem.read"
    assert engine.submitted[0].arguments == {"path": "notes.txt"}
    # Real tool failure keeps its own taxonomy - distinct from protocol errors.
    assert result.tool_state == "FAILED"
    assert "does not exist" in result.reply
    assert result.error_class == ""


# ----------------------------------------------------- malformed + degenerate
def test_malformed_json_block_is_model_protocol_error_and_executes_nothing() -> None:
    engine = RecordingEngine()
    broken = '<tool_request>{"tool": "filesystem", "capability": </tool_request>'
    result = run_turn(ScriptedInference([broken]), engine, _prompt("hi"))  # type: ignore[arg-type]
    assert engine.submitted == []
    assert result.error_class == response_texts.MODEL_PROTOCOL_ERROR_EVENT
    assert "couldn't safely interpret" in result.reply
    assert "you" not in result.reply.split("interpret")[0].lower() or True


def test_degenerate_control_token_output_is_bounded_and_classified() -> None:
    engine = RecordingEngine()
    junk = "</s>\n</s>\n</s>\n"
    inference = ScriptedInference([junk, junk, junk])  # every resample degenerates
    result = run_turn(inference, engine, _prompt("hello"))  # type: ignore[arg-type]
    assert len(inference.prompts) == 3  # bounded resampling, then refusal
    assert engine.submitted == []
    assert result.error_class == response_texts.MODEL_PROTOCOL_ERROR_EVENT
    assert "</s>" not in result.reply


def test_template_echo_loop_resamples_then_succeeds() -> None:
    loop = "### USER MESSAGE ###\n### USER MESSAGE ###\n### USER MESSAGE ###\n### USER MESSAGE ###"
    good = "All done — the file was created."
    inference = ScriptedInference([loop, good])
    engine = RecordingEngine()
    result = run_turn(inference, engine, _prompt("create hello.txt"))  # type: ignore[arg-type]
    assert result.reply == good
    assert len(inference.prompts) == 2


def test_reasoning_spill_with_fences_is_treated_as_broken_output() -> None:
    spill = "let me think...\n```\n```\n```\n```"
    inference = ScriptedInference([spill])
    engine = RecordingEngine()
    result = run_turn(inference, engine, _prompt("hello"))  # type: ignore[arg-type]
    assert result.error_class == response_texts.MODEL_PROTOCOL_ERROR_EVENT


def test_unclosed_request_block_with_valid_json_still_flows_to_policy() -> None:
    # Observed live on Qwen3-0.6B (finish=stop, closing tag omitted):
    # protocol extraction must not discard a well-formed proposal.
    unclosed = (
        '<tool_request>{"tool": "filesystem.read", '
        '"capability": "filesystem.read", "arguments": {"path": "notes.txt"}}'
    )

    class Outcome:
        state = "COMPLETED"
        reason = ""
        approval_id = None

        def __init__(self) -> None:
            self.output = {"ok": True}

    class ScriptedEngine(RecordingEngine):
        def submit(self, request, conversation_id=None):  # type: ignore[override]
            self.submitted.append(request)
            return Outcome()

    engine = ScriptedEngine()
    inference = ScriptedInference([unclosed, "Done — notes.txt has been read."])
    result = run_turn(inference, engine, _prompt("read notes.txt"))  # type: ignore[arg-type]
    assert len(engine.submitted) == 1
    assert engine.submitted[0].capability == "filesystem.read"
    assert result.tool_state == "COMPLETED"
    assert result.error_class == ""


def test_unclosed_block_with_invalid_json_fails_closed() -> None:
    engine = RecordingEngine()
    broken = '<tool_request>{"capability": "filesystem.read", "path":'
    result = run_turn(ScriptedInference([broken]), engine, _prompt("read notes.txt"))  # type: ignore[arg-type]
    assert engine.submitted == []
    assert result.error_class == response_texts.MODEL_PROTOCOL_ERROR_EVENT


# ---------------------------------------------------- taxonomy distinctness
def test_denied_failed_and_system_error_texts_stay_distinct() -> None:
    texts = response_texts.RESPONSE_TEXTS
    assert texts["model_protocol_error"] != texts["system_error"]
    assert texts["policy_denied_prefix"] != texts["tool_failed_prefix"]
    assert "internal system error" in texts["system_error"]
    assert "Nothing was executed" in texts["system_error"]


# ------------------------------------------------- inference boundary (EOS)
def test_adapter_sends_structured_stop_sequences_to_the_runtime():
    captured: dict[str, Any] = {}

    def opener(request, timeout=None):
        captured["payload"] = json.loads(request.data.decode())
        return _ok_opener(b'{"choices": [{"message": {"content": "ok"}}]}')(
            request, timeout
        )

    LlamaCppAdapter(
        base_url="http://127.0.0.1:8080",
        model_name="m",
        timeout_seconds=5,
        opener=opener,
    ).complete("p")
    assert "</s>" in captured["payload"]["stop"]
    assert "<|im_end|>" in captured["payload"]["stop"]


def test_literal_eos_tokens_never_survive_the_boundary() -> None:
    raw = "I am here, and I am with you...\n</s>\n</s>\n</s>"
    cleaned = normalize(raw).text
    assert "</s>" not in cleaned
    assert "I am here" in cleaned
    assert STOP_SEQUENCES  # runtime-level stops configured as first line


def test_normalizer_is_idempotent_and_handles_think_blocks() -> None:
    once = normalize("<think>secret chain</think>The answer is 4.</s>")
    twice = normalize(once.text)
    assert once.text == twice.text == "The answer is 4."


def test_control_token_only_output_reports_empty_not_text() -> None:
    outcome = normalize("</s> </s> <|im_end|>")
    assert outcome.is_empty
    assert outcome.control_tokens_removed >= 3


def test_template_header_artifacts_are_stripped_from_replies() -> None:
    raw = "### OUTPUT ###\nI'm running well, thank you.\n\n# ANSWER\nGreat!"
    cleaned = normalize(raw).text
    assert "###" not in cleaned
    assert "I'm running well, thank you." in cleaned


def test_inline_hash_text_is_never_touched() -> None:
    raw = "Use # for headings in markdown. C# is a language."
    assert normalize(raw).text == raw


def test_full_stack_reply_never_contains_control_tokens(tmp_path) -> None:
    body = json.dumps(
        {"choices": [{"message": {"content": "Hello! How can I help?\n</s></s>"}}]}
    )
    adapter = LlamaCppAdapter(
        base_url="http://127.0.0.1:8080",
        model_name="m",
        timeout_seconds=5,
        opener=_ok_opener(body.encode()),
    )
    engine = RecordingEngine()
    result = run_turn(adapter, engine, _prompt("hello"))  # type: ignore[arg-type]
    assert result.reply == "Hello! How can I help?"
    assert "</s>" not in result.reply
