#!/usr/bin/env python3
"""SessionEnd hook — prints and saves the session receipt. Never blocks."""

import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _receipt as R


def _copy_assets(out_dir):
    for src in (R.css_asset_path(), R.js_asset_path()):
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(out_dir, os.path.basename(src)))


def main():
    hook = R.read_hook_input()
    ctx = R.build_context(hook)

    no_color = bool(os.environ.get("NO_COLOR") or os.environ.get("AGENT_RECEIPT_NO_COLOR"))

    # --- Save files FIRST ---------------------------------------------------
    # On /exit (and other graceful shutdowns) Claude Code tears the process
    # down shortly after invoking this hook. Writing the receipt to disk before
    # printing guarantees the HTML/TXT always land, even if the terminal print
    # is cut off by teardown or wiped by the fullscreen (alt-screen) TUI.
    out_dir = R.receipt_out_dir()
    base = os.path.join(out_dir, "agent-receipt-" + ctx["receipt_no"])
    saved = False
    try:
        with open(base + ".html", "w") as f:
            f.write(R.render_html(ctx))
        with open(base + ".txt", "w") as f:
            f.write(R.render_text(ctx))
        _copy_assets(out_dir)
        saved = True
    except Exception as e:
        sys.stderr.write(f"\n  (could not save receipt files: {e})\n\n")

    # State no longer needed once the receipt is rendered.
    try:
        os.remove(R.state_path(ctx["session_id"]))
    except Exception:
        pass

    # --- Then print (instant, never animated on the exit path) --------------
    # Animation is intentionally skipped here: its per-line sleeps can outlast
    # the shutdown grace window, and fullscreen restore wipes the output on exit
    # anyway. The on-demand /agent-receipt command still animates normally.
    stream, own_tty = sys.stderr, False
    try:
        stream = open("/dev/tty", "w")
        own_tty = True
    except Exception:
        stream, own_tty = sys.stderr, False

    color = (not no_color) and (own_tty or stream.isatty())
    try:
        stream.write("\n" + "\n".join(R.build_ansi(ctx, color)) + "\n")
        if saved:
            stream.write(f"\n  Receipt saved:\n    {base}.html\n    {base}.txt\n\n")
        stream.flush()
    except Exception:
        sys.stderr.write("\n" + R.render_ansi(ctx) + "\n")

    if own_tty:
        try:
            stream.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"agent-receipt: {e}\n")
    sys.exit(0)
