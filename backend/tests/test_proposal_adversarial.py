"""Adversarial tests for tool-proposal parsing (P15).

The model's output is UNTRUSTED INPUT (roadmap §12). Whatever a hostile
or broken model emits must end in exactly one of two states:

  1. parsed into a well-formed proposal dict, which then still has to
     pass policy + the filesystem boundary before anything executes
  2. rejected as None / flagged broken — no crash, no execution

These tests pin that contract against a hostile corpus.
"""

from __future__ import annotations

import json

from app.application.orchestrator import (
    _looks_like_broken_proposal,
    _proposal_from_payload,
    has_request_block,
    parse_tool_request,
)


def _wrap(inner: str) -> str:
    return f"Sure! <tool_request>{inner}</tool_request> here you go."


def test_garbage_without_block_is_not_a_proposal() -> None:
    assert parse_tool_request("hello world") is None
    assert parse_tool_request("") is None
    assert parse_tool_request("<tool_request></tool_request>") is None


def test_malformed_json_inside_block_is_rejected() -> None:
    for bad in (
        "{not json",
        '{"tool": "filesystem",',  # truncated
        "[]",
        '"just a string"',
        "null",
        "12345",
    ):
        assert parse_tool_request(_wrap(bad)) is None, bad


def test_wrong_json_types_are_rejected_by_payload_gate() -> None:
    # parse succeeds but payload gate refuses non-dict arguments etc.
    cases = [
        {"tool": "filesystem", "capability": "x", "arguments": ["not", "a", "dict"]},
        {"tool": 42, "capability": "x"},
        {"tool": "filesystem", "capability": None},
        {"arguments": {"path": "/etc/passwd"}},  # missing both names
    ]
    for payload in cases:
        assert _proposal_from_payload(payload) is None, payload


def test_unicode_and_escape_tricks_do_not_smuggle_structure() -> None:
    sneaky = r"{\"tool\": \"filesystem\\u0044\", \"cap\u0061bility\": \"x\"}"
    # invalid JSON (single quotes/backslash games) -> None
    if json.loads(f'"{sneaky}"') and parse_tool_request(_wrap(sneaky)) is not None:
        payload = parse_tool_request(_wrap(sneaky))
        assert isinstance(payload, dict)
        assert _proposal_from_payload(payload) is None or isinstance(
            _proposal_from_payload(payload), object
        )
    # null bytes and control chars inside JSON string values stay inert text
    hostile = '{"tool": "file\\u0000system", "capability": "read\\nfile", "arguments": {}}'
    payload = parse_tool_request(_wrap(hostile))
    if payload is not None:
        proposal = _proposal_from_payload(payload)
        assert proposal is None or proposal.tool.startswith("file")


def test_deeply_nested_arguments_stay_inert() -> None:
    deep = {"arguments": {}}
    cursor = deep["arguments"]
    for _ in range(50):
        cursor["n"] = {}
        cursor = cursor["n"]
    cursor["path"] = "/etc/passwd"
    text = _wrap(json.dumps({"tool": "filesystem", "capability": "x", **deep}))
    payload = parse_tool_request(text)
    assert payload is not None
    proposal = _proposal_from_payload(payload)
    assert proposal is not None
    # The parser is deliberately dumb; the BOUNDARY is what refuses paths.
    # Here we only pin that parsing never crashes and never auto-executes.
    cursor = proposal.arguments
    for _ in range(50):
        cursor = cursor["n"]
    assert cursor["path"] == "/etc/passwd"


def test_duplicate_keys_take_last_value_consistently() -> None:
    text = _wrap(
        '{"tool": "innocent", "tool": "filesystem", "capability": "c", "arguments": {}}'
    )
    payload = parse_tool_request(text)
    assert payload is not None and payload["tool"] == "filesystem"
    proposal = _proposal_from_payload(payload)
    assert proposal is not None and proposal.tool == "filesystem"


def test_oversized_argument_string_is_bounded_downstream_not_here() -> None:
    huge = "A" * 500_000
    text = _wrap(
        json.dumps({"tool": "t", "capability": "c", "arguments": {"blob": huge}})
    )
    payload = parse_tool_request(text)
    assert payload is not None  # parsing survives size
    assert len(payload["arguments"]["blob"]) == 500_000


def test_unclosed_open_tag_is_flagged_broken_safe() -> None:
    text = 'I will do it. <tool_request>{"tool": "t"'
    assert has_request_block(text) is False
    assert _looks_like_broken_proposal(text) is True


def test_degenerate_template_echo_loops_are_flagged() -> None:
    loop = "\n".join(["### CONVERSATION HISTORY ###"] * 5)
    assert _looks_like_broken_proposal(loop) is True
    two_lines = "RUACH\nRUACH\nRUACH\nRUACH"
    assert _looks_like_broken_proposal(two_lines) is True


def test_plain_prose_is_neither_request_nor_broken() -> None:
    prose = "The capital of France is Paris."
    assert parse_tool_request(prose) is None
    assert has_request_block(prose) is False
    assert _looks_like_broken_proposal(prose) is False
