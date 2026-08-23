"""Platform-aware URL launching (docs/12 P16 §15).

Desktop convenience, never a requirement: when no usable mechanism
exists (Termux without helpers, headless shells), the URL is simply
printed clearly. No macOS-only assumptions; Termux gets its native
opener when available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def is_termux(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else dict(os.environ)
    return bool(env.get("TERMUX_VERSION")) or "/com.termux/" in env.get("PREFIX", "")


def _gui_available(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else dict(os.environ)
    if sys.platform == "darwin" or os.name == "nt":
        return True
    return bool(env.get("DISPLAY"))


def launch_url(url: str, *, environ: dict[str, str] | None = None, echo=print) -> bool:
    """Try hard to open `url`; ALWAYS report the URL regardless. Returns
    True only when an opener actually ran."""
    env = environ if environ is not None else dict(os.environ)

    if is_termux(env):
        for helper in ("termux-open-url", "termux-open"):
            helper_path = shutil.which(helper)
            if helper_path:
                try:
                    subprocess.run([helper_path, url], check=False, timeout=10)
                    echo(f"[ui] opening in your browser: {url}")
                    return True
                except OSError:
                    break
        echo("[ui] Open this address in your browser:")
        echo(f"     {url}")
        return False

    if _gui_available(env):
        try:
            import webbrowser

            if webbrowser.open(url):
                echo(f"[ui] opened in your browser: {url}")
                return True
        except Exception:  # noqa: BLE001 - headless must never crash start
            echo("[ui] automatic browser launch failed; showing the address below")

    echo("[ui] Open this address in your browser:")
    echo(f"     {url}")
    return False
