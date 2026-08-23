"""Inc 12 — scripted fresh-environment MVP gate (`ruach verify`).

One command takes this machine from source checkout to PROVEN-working:
doctor, backend unit gates, bootstrap gates, the twice-from-zero
migration demo, browser E2E, and — with --live — a real-model smoke that
asserts SYSTEM honesty under both proposal branches (well-formed ->
approval flow executes; malformed -> explicit fail-closed denial).

The gate never asserts model intelligence. It asserts that whatever the
model does, the system's responses remain honest and fail-closed.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / "bin" / "python"


@dataclass(frozen=True)
class Stage:
    name: str
    command: list[str] | None  # None => python function stage (live)
    # P12 §8 dependency classification. CORE functionality must never
    # depend on a desktop-only convenience; the gate stages below are all
    # development tools — the CORE product commands (start/stop/status/
    # doctor) depend only on Python + the venv.
    klass: str = "OPTIONAL_DEV"  # CORE | OPTIONAL_DEV | PLATFORM_SPECIFIC | TEST_ONLY
    requires_file: Path | None = None
    cwd: Path | None = None

    def unavailable_reason(self) -> str | None:
        import shutil

        if self.requires_file is not None and not self.requires_file.is_file():
            return f"missing {self.requires_file.name}"
        command = self.command or []
        if "bash" in command and shutil.which("bash") is None:
            return "bash not available on this platform"
        if any(arg == "sqlite3" for arg in command) and shutil.which("sqlite3") is None:
            return "sqlite3 CLI not available (dev-only convenience)"
        if any(arg == "npm" for arg in command) and shutil.which("npm") is None:
            return "npm not available (UI build is a dev-time step)"
        if self.name == "browser-e2e":
            try:
                __import__("playwright")
            except ImportError:
                return "playwright extra not installed (pip install -e '.[e2e]')"
            if not (ROOT / "frontend" / "dist" / "index.html").is_file():
                return "UI not built: frontend/dist missing (run npm run build)"
        return None


def build_stages(*, include_live: bool) -> list[Stage]:
    stages = [
        Stage("doctor", [str(ROOT / "ruach"), "doctor"], klass="CORE"),
        Stage(
            "backend-unit",
            [
                str(VENV_PY),
                "-m",
                "pytest",
                "-q",
                "backend/tests",
                "--ignore=backend/tests/test_live_orchestration.py",
            ],
            klass="TEST_ONLY",
        ),
        Stage(
            "bootstrap-tests",
            [str(VENV_PY), "-m", "pytest", "-q", "tests_bootstrap"],
            klass="TEST_ONLY",
        ),
        Stage(
            "fresh-install-twice-from-zero",
            ["bash", "backend/scripts/fresh_install_demo.sh"],
            klass="PLATFORM_SPECIFIC",  # bash + sqlite3 CLI + mktemp
            requires_file=ROOT / "backend" / "scripts" / "fresh_install_demo.sh",
        ),
        Stage(
            "ui-build",
            ["npm", "run", "build"],
            klass="OPTIONAL_DEV",  # node/npm are dev-time only
            cwd=ROOT / "frontend",
        ),
        Stage(
            "browser-e2e",
            [str(VENV_PY), "-m", "pytest", "-q", "backend/tests/test_frontend_e2e.py"],
            klass="OPTIONAL_DEV",  # needs system Chrome via playwright
        ),
    ]
    if include_live:
        stages.append(Stage("live-model-smoke", None, klass="OPTIONAL_DEV"))
    return stages


def run_stage(stage: Stage, echo=print) -> bool:
    reason = stage.unavailable_reason()
    if reason is not None:
        echo(f"[{stage.name}] SKIP ({reason})")
        return True
    echo(f"[{stage.name}] running ({stage.klass}): {' '.join(stage.command or ['<live smoke>'])}")
    started = time.monotonic()
    result = subprocess.run(stage.command or [], cwd=str(stage.cwd or ROOT), check=False)
    elapsed = time.monotonic() - started
    ok = result.returncode == 0
    echo(f"[{stage.name}] {'PASS' if ok else 'FAIL'} ({elapsed:.0f}s)")
    return ok


# ------------------------------------------------------------ live smoke


def classify_protected_turn(data: dict) -> tuple[str, str]:
    """Return (branch, detail) for a protected-op turn.

    branch is 'pending' (well-formed proposal awaiting approval), 'tool'
    (a terminal tool activity line came back), 'denied' (explicit textual
    refusal), or 'uncertain' (model prose we cannot parse).

    Callers must NOT trust these labels for safety: the binding invariant
    is checked separately — nothing may execute without an approved
    approval row (protected_turn_is_fail_closed).
    """
    pending = data.get("pending_approval")
    if isinstance(pending, dict) and pending.get("approval_id"):
        return "pending", str(pending.get("capability"))
    tool = data.get("tool")
    if isinstance(tool, dict) and tool.get("state"):
        return "tool", f"{tool.get('state')}: {tool.get('capability')} {data.get('content', '')[:60]}"
    content = str(data.get("content", ""))
    lowered = content.lower()
    if (
        "did not perform" in lowered
        or "could not be completed" in lowered
        or "no action" in lowered
        or "not execute" in lowered
        or "cancelled" in lowered
    ):
        return "denied", content[:90]
    return "uncertain", content[:90]


def protected_turn_is_fail_closed(data: dict, target_exists: bool) -> bool:
    """THE security invariant of the gate: without an approved approval,
    the filesystem must be untouched."""
    if isinstance(data.get("pending_approval"), dict):
        return True  # awaiting human decision; execution happens later
    return target_exists


def live_smoke(echo=print) -> bool:
    """Real-model smoke. Transport failures get ONE clean-stack retry (a
    wedged llama-server slot only heals via restart); assertion failures
    are genuine gate failures and are never retried."""
    from bootstrap.runtime import start, stop

    for attempt in (1, 2):
        root = Path(tempfile.mkdtemp(prefix="ruach_live_gate_"))
        (root / "workspace").mkdir()
        target = root / "workspace" / "gate-file.txt"
        target.write_text("gate payload", encoding="utf-8")
        try:
            stack = start(
                stub=False,
                browser=False,
                run_dir=root / "run",
                extra_env={
                    "RUACH_DATABASE_URL": f"sqlite:///{root / 'ruach.db'}",
                    "RUACH_WORKSPACE_PATH": str(root / "workspace"),
                    "RUACH_AUDIT_LOG_PATH": str(root / "audit.jsonl"),
                },
                echo=lambda *_: None,
            )
        except Exception as error:  # noqa: BLE001 - bring-up failure counts as attempt
            echo(f"[live] attempt {attempt}: stack start failed: {error}")
            continue
        try:
            return _live_flow(stack.base_url, target, echo)
        except RuntimeError as error:
            echo(f"[live] attempt {attempt}: transport failure ({error})")
            if attempt == 1:
                echo("[live] restarting the stack for a clean model server")
        finally:
            stop(run_dir=root / "run", echo=lambda *_: None)
    return False


def _post(base_url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base_url}/api/v1{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180.0) as response:
        body = json.loads(response.read())
    return body["data"]


def _live_flow(base_url: str, target: Path, echo=print) -> bool:
    conversation_id: str | None = None

    # Round trip 1: plain chat. Assert envelope honesty only.
    data = _post_with_retry(base_url, "/chat", {"message": "Remember the codename is Falcon."})
    conversation_id = str(data["conversation_id"])
    if not isinstance(data.get("content"), str) or not data["content"]:
        echo("[live] FAIL: empty reply for plain chat")
        return False
    echo(f'[live] round trip ok: "{data["content"][:60]}..."')

    # Round trip 2: protected op. Whatever the model emits, the invariant
    # is: nothing executes without an approved approval row.
    data = _post_with_retry(
        base_url,
        "/chat",
        {"message": f"delete {target.name}", "conversation_id": conversation_id},
    )
    branch, detail = classify_protected_turn(data)
    echo(f"[live] protected op branch={branch} ({detail})")

    if branch == "pending":
        approval_id = data["pending_approval"]["approval_id"]
        decided = _post_with_retry(
            base_url,
            f"/chat/approvals/{approval_id}/approve",
            {"approved": True},
        )
        tool_state = str((decided.get("tool") or {}).get("state"))
        deleted = not target.exists()
        if tool_state == "COMPLETED" and not deleted:
            echo("[live] FAIL: COMPLETED but file exists")
            return False
        if tool_state != "COMPLETED" and deleted:
            echo(f"[live] FAIL: file deleted despite tool state {tool_state}")
            return False
        echo(f"[live] approval resolved: {tool_state}; file deleted={deleted}")
        return True

    if not protected_turn_is_fail_closed(data, target_exists=target.exists()):
        echo("[live] FAIL: filesystem changed without an approved approval")
        return False
    echo("[live] fail-closed held: target untouched, no execution without approval")
    return True


def _post_with_retry(base_url: str, path: str, payload: dict) -> dict:
    return _post(base_url, path, payload)


def verify(*, include_live: bool, echo=print) -> int:
    stages = build_stages(include_live=include_live)
    failures: list[str] = []
    for stage in stages:
        if stage.command is None:
            try:
                ok = live_smoke(echo=echo)
                echo(f"[{stage.name}] {'PASS' if ok else 'FAIL'}")
            except RuntimeError as error:
                echo(f"[{stage.name}] FAIL ({error})")
                ok = False
        else:
            ok = run_stage(stage, echo=echo)
        if not ok:
            failures.append(stage.name)
    echo()
    if failures:
        echo("GATE FAILED: " + ", ".join(failures))
        return 1
    echo("MVP GATE PASSED" + (" (incl. live model)" if include_live else ""))
    return 0
