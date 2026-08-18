#!/usr/bin/env python3
"""Present a saved HTML receipt in a native viewer, then a browser fallback."""

import os
import platform
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER_SOURCE = os.path.join(ROOT, "viewer", "AgentReceiptViewer.swift")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "agent-receipt")
VIEWER_BINARY = os.path.join(CACHE_DIR, "AgentReceiptViewer")


def _native_viewer_available():
    return platform.system() == "Darwin" and shutil.which("swiftc") and os.path.exists(VIEWER_SOURCE)


def ensure_native_viewer():
    if not _native_viewer_available():
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        source_mtime = os.path.getmtime(VIEWER_SOURCE)
        if os.path.exists(VIEWER_BINARY) and os.path.getmtime(VIEWER_BINARY) >= source_mtime:
            return VIEWER_BINARY
        tmp = VIEWER_BINARY + ".tmp"
        cmd = [
            shutil.which("swiftc"), "-O",
            "-framework", "AppKit",
            "-framework", "WebKit",
            VIEWER_SOURCE,
            "-o", tmp,
        ]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if r.returncode != 0 or not os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
            return None
        os.replace(tmp, VIEWER_BINARY)
        os.chmod(VIEWER_BINARY, 0o755)
        return VIEWER_BINARY
    except Exception:
        return None


def open_native(html_path):
    binary = ensure_native_viewer()
    if not binary:
        return False
    try:
        proc = subprocess.Popen(
            [binary, os.path.abspath(html_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(0.08)
        return proc.poll() is None
    except Exception:
        return False


def open_browser(html_path):
    path = os.path.abspath(html_path)
    try:
        system = platform.system()
        if system == "Darwin":
            cmd = ["open", path]
        elif system == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        else:
            opener = shutil.which("xdg-open") or shutil.which("gio")
            if not opener:
                return False
            cmd = [opener, path] if os.path.basename(opener) == "xdg-open" else [opener, "open", path]
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=0.75)
        return r.returncode == 0
    except Exception:
        return False


def present(html_path, mode="native"):
    """Return (presented, method). Never raises."""
    if not html_path or not os.path.exists(html_path):
        return False, "missing"
    mode = (mode or "native").lower()
    if mode in ("native", "auto") and open_native(html_path):
        return True, "native"
    if mode in ("native", "auto", "browser") and open_browser(html_path):
        return True, "browser"
    return False, "unavailable"


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    ok, method = present(path, os.environ.get("AGENT_RECEIPT_VIEWER", "native"))
    print(method if ok else "unavailable")
    sys.exit(0 if ok else 1)
