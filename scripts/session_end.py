#!/usr/bin/env python3
"""SessionEnd hook — saves and presents the interactive HTML receipt."""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _receipt as R



def _present(path, mode):
    presenter = os.path.join(os.path.dirname(os.path.abspath(__file__)), "present_receipt.py")
    try:
        # The native viewer is a detached process. If native presentation is not
        # available, the presenter opens the saved HTML in the browser.
        return subprocess.run(
            [sys.executable, presenter, path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
            env={**os.environ, "AGENT_RECEIPT_VIEWER": mode},
        ).stdout.strip()
    except Exception:
        return "unavailable"


def main():
    hook = R.read_hook_input()
    ctx = R.build_context(hook)

    # Save the canonical receipt before attempting presentation. SessionEnd has
    # a short lifecycle budget, so presentation must never be allowed to block
    # receipt persistence.
    out_dir = R.receipt_out_dir()
    base = os.path.join(out_dir, "agent-receipt-" + ctx["receipt_no"])
    html_path = base + ".html"
    saved = False
    try:
        with open(html_path, "w") as f:
            f.write(R.render_html(ctx))
        saved = True
    except Exception as e:
        sys.stderr.write(f"agent-receipt: could not save receipt: {e}\n")

    # State is no longer needed after the final receipt has been reconstructed.
    try:
        os.remove(R.state_path(ctx["session_id"]))
    except Exception:
        pass

    if not saved:
        return

    if not ctx.get("open_on_end", True):
        return

    method = _present(html_path, ctx.get("viewer_mode", "native"))
    if method == "unavailable":
        # The terminal is deliberately not used as a receipt fallback. Keep the
        # failure message tiny because the receipt itself is still saved.
        sys.stderr.write(
            "Agent Receipt: receipt unavailable. "
            f"Saved at {html_path}\n"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"agent-receipt: {e}\n")
    sys.exit(0)
