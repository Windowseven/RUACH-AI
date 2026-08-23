"""Browser E2E: the real UI against the real backend stack (P6).

Launches a fully isolated RUACH server (own SQLite DB via migrations, own
workspace, own audit log, stub model runtime for determinism) and drives
Google Chrome headless through Playwright. Proves what curl cannot:

- boot screen reflects REAL backend readiness before the workspace shows
- chat round trips through composer -> API -> context assembly -> reply
- approval cards appear for protected tools and APPROVE/DENY act on the
  filesystem for real
- conversation sidebar lists persisted conversations and reloads history
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, expect

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
PY = str(BACKEND_DIR.parent / ".venv" / "bin" / "python")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    """Isolated RUACH install + uvicorn process; yields base URL."""
    root = tmp_path_factory.mktemp("e2e_install")
    db = root / "ruach.db"
    workspace = root / "workspace"
    workspace.mkdir()
    (workspace / "report.txt").write_text("delete me")
    (workspace / "keepme.txt").write_text("keep me")

    import subprocess as sp

    env = dict(os.environ)
    env.update(
        {
            "RUACH_DATABASE_URL": f"sqlite:///{db}",
            "RUACH_WORKSPACE_PATH": str(workspace),
            "RUACH_AUDIT_LOG_PATH": str(root / "audit.jsonl"),
            "RUACH_MODEL_RUNTIME": "stub",
        }
    )

    # Migrate from zero: same path a stranger's machine takes.
    sp.run(
        [PY, "-m", "alembic", "-c", str(BACKEND_DIR / "alembic.ini"), "upgrade", "head"],
        env=env,
        cwd=str(BACKEND_DIR),
        check=True,
        capture_output=True,
    )

    port = _free_port()
    proc = sp.Popen(
        [
            PY,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        cwd=str(BACKEND_DIR),
        stdout=sp.DEVNULL,
        stderr=sp.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        import time

        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                urlopen(f"{base}/api/v1/health", timeout=1)
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("uvicorn died during startup")
                time.sleep(0.3)
        else:
            raise RuntimeError("uvicorn never became healthy")
        yield {"base": base, "workspace": workspace}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    # "chrome" drives a real system install (dev hosts); CI overrides with
    # RUACH_E2E_BROWSER_CHANNEL=chromium after `playwright install chromium`.
    channel = os.environ.get("RUACH_E2E_BROWSER_CHANNEL", "chrome")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=channel, headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, server) -> Page:
    context = browser.new_context(base_url=server["base"])
    pg = context.new_page()
    yield pg
    context.close()


def _open_workspace(page: Page) -> None:
    page.goto("/")
    expect(page.locator("#boot-screen")).to_be_hidden(timeout=15_000)
    expect(page.locator("#workspace")).to_be_visible()


def _send(page: Page, text: str) -> None:
    page.fill("#composer-input", text)
    page.click("#send-btn")


def test_boot_reflects_real_readiness_then_shows_workspace(page: Page) -> None:
    page.goto("/")
    # Boot checklist must show READY/AVAILABLE states driven by /ready.
    core = page.locator('[data-check="core"]')
    storage = page.locator('[data-check="storage"]')
    inference = page.locator('[data-check="inference"]')
    expect(core).to_have_attribute("data-state", "ok", timeout=10_000)
    expect(storage).to_have_attribute("data-state", "ok")
    expect(inference).to_have_attribute("data-state", "ok")
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#connection-badge .dot.dot-ok")).to_be_visible()


def test_chat_round_trip_and_memory_through_ui(page: Page) -> None:
    _open_workspace(page)
    _send(page, "My name is Amani")
    expect(
        page.locator(".message.user .body", has_text="My name is Amani")
    ).to_be_visible()
    reply = page.locator(".message.assistant .body").last
    expect(reply).to_contain_text("[stub] You said: My name is Amani")

    # Memory requires the ContextBuilder to have included the prior turn.
    _send(page, "what is my name?")
    answer = page.locator(".message.assistant .body").last
    expect(answer).to_have_text("Your name is Amani.")


def test_thinking_indicator_animates_while_awaiting_reply(page: Page) -> None:
    _open_workspace(page)

    # Hold the chat request at the network layer (no JS route callbacks:
    # those race with context teardown in the sync API).
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send(
        "Network.emulateNetworkConditions",
        {
            "offline": False,
            "latency": 2000,
            "downloadThroughput": -1,
            "uploadThroughput": -1,
        },
    )
    _send(page, "hello")

    dots = page.locator(".state-thinking .typing-dots .dot")
    expect(dots).to_have_count(3)
    animation = dots.first.evaluate(
        "el => getComputedStyle(el).animationName + ' ' + getComputedStyle(el).animationDuration"
    )
    assert animation.startswith("dot-rise"), f"indicator not animating: {animation}"
    assert animation != "dot-rise 0s", "animation has zero duration (static)"

    cdp.send(
        "Network.emulateNetworkConditions",
        {
            "offline": False,
            "latency": 0,
            "downloadThroughput": -1,
            "uploadThroughput": -1,
        },
    )
    # The delayed reply must still land after the indicator disappears.
    reply = page.locator(".message.assistant .body").last
    expect(reply).to_contain_text("[stub] You said: hello", timeout=15_000)
    expect(page.locator(".state-thinking")).to_have_count(0)


def test_approval_approve_executes_filesystem_for_real(page: Page, server) -> None:
    target = server["workspace"] / "report.txt"
    assert target.exists()

    _open_workspace(page)
    _send(page, "delete report.txt")
    card = page.locator(".approval-card")
    expect(card).to_be_visible(timeout=10_000)
    expect(card.locator(".approval-capability")).to_have_text("filesystem.delete")
    expect(card.locator(".approval-args")).to_contain_text("report.txt")

    card.locator(".btn-approve").click()
    expect(card).to_have_count(0)
    activity = page.locator(".tool-activity").last
    expect(activity).to_contain_text("filesystem.delete")
    expect(activity).to_contain_text("COMPLETED")
    outcome = page.locator(".message.assistant .body").last
    expect(outcome).to_contain_text("Here is what happened")
    assert not target.exists(), "approval must have executed the delete"


def test_approval_deny_leaves_file_untouched(page: Page, server) -> None:
    target = server["workspace"] / "keepme.txt"
    assert target.exists()

    _open_workspace(page)
    _send(page, "delete keepme.txt")
    card = page.locator(".approval-card")
    expect(card).to_be_visible(timeout=10_000)
    card.locator(".btn-deny").click()

    activity = page.locator(".tool-activity").last
    expect(activity).to_contain_text("filesystem.delete")
    expect(activity).to_contain_text("REJECTED")
    assert target.exists(), "denial must not touch the file"


def test_conversations_persist_and_reload_from_sidebar(page: Page) -> None:
    _open_workspace(page)
    _send(page, "My name is Zawadi")
    first_reply = page.locator(".message.assistant .body").last
    expect(first_reply).to_contain_text("[stub]")

    # Fresh page state: history comes back through GET /conversations + detail.
    page.reload()
    _open_workspace(page)
    item = page.locator("#conversation-list .conversation-item").first
    expect(item).to_be_visible()
    item.click()

    expect(page.locator(".message.user").first).to_be_visible()
    expect(
        page.locator(".message.user .body", has_text="My name is Zawadi")
    ).to_be_visible()
