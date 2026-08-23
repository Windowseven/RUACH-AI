"""Unit coverage for degenerate-proposal detection (P4 hardening)."""

from app.application.orchestrator import _looks_like_broken_proposal


def test_template_echo_loop_is_flagged() -> None:
    assert _looks_like_broken_proposal(
        "### \n\n### FOLLOW THE RULES\n### \n\n### FOLLOW THE EXAMPLES\n### "
    )


def test_repeated_short_lines_are_flagged() -> None:
    assert _looks_like_broken_proposal("ok ok ok\n ok ok ok\n ok ok ok\n ok ok ok")


def test_normal_reply_is_not_flagged() -> None:
    assert not _looks_like_broken_proposal("Here is a normal reply.")
