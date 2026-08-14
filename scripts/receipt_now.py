#!/usr/bin/env python3
"""On-demand receipt for the current session — the engine behind /agent-receipt."""

import os
import sys
import glob
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _receipt as R


def _first_line_cwd(path):
    try:
        with open(path, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    return json.loads(line).get("cwd")
    except Exception:
        return None
    return None


def find_by_session_id():
    """Authoritative: locate THIS session's transcript by its id.

    Claude Code exports the current session id on every command it runs
    (CLAUDE_CODE_SESSION_ID); AGENT_RECEIPT_SESSION_ID lets a caller override.
    This is independent of the working directory, so it never mis-targets a
    sibling session the way the cwd heuristic can when the receipt is run from
    a subdirectory of the session root.
    """
    sid = os.environ.get("AGENT_RECEIPT_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        return None
    root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    hits = glob.glob(os.path.join(root, "*", sid + ".jsonl"))
    return hits[0] if hits else None


def find_transcript(cwd):
    root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(root):
        return None
    encoded = cwd.replace(os.sep, "-").replace(".", "-")
    for cand in (os.path.join(root, encoded), os.path.join(root, "-" + encoded.lstrip("-"))):
        hits = glob.glob(os.path.join(cand, "*.jsonl"))
        if hits:
            return max(hits, key=os.path.getmtime)
    all_hits = sorted(glob.glob(os.path.join(root, "*", "*.jsonl")),
                      key=os.path.getmtime, reverse=True)
    for path in all_hits:
        if _first_line_cwd(path) == cwd:
            return path
    return all_hits[0] if all_hits else None


def main():
    cwd = os.getcwd()
    # Prefer the session id Claude Code exports (cwd-independent); fall back to
    # the cwd heuristic only when it is absent.
    transcript = find_by_session_id() or find_transcript(cwd)
    if not transcript:
        sys.stderr.write("agent-receipt: no session transcript found for this project.\n")
        return

    session_id = os.path.splitext(os.path.basename(transcript))[0]
    ctx = R.build_context({
        "session_id": session_id,
        "transcript_path": transcript,
        "cwd": cwd,
        "ongoing": True,
    })

    no_color = bool(os.environ.get("NO_COLOR") or os.environ.get("AGENT_RECEIPT_NO_COLOR"))

    printed_tty = False
    if R.ANIMATE:
        try:
            tty = open("/dev/tty", "w")
            R.animate_ansi(ctx, tty, color=not no_color, clear=R.CLEAR_SCREEN)
            tty.flush()
            tty.close()
            printed_tty = True
        except Exception:
            printed_tty = False
    if not printed_tty:
        color = (not no_color) and sys.stdout.isatty()
        sys.stdout.write("\n".join(R.build_ansi(ctx, color)) + "\n")

    out_dir = R.receipt_out_dir()
    base = os.path.join(out_dir, "agent-receipt-" + ctx["receipt_no"])
    try:
        with open(base + ".html", "w") as f:
            f.write(R.render_html(ctx))
        with open(base + ".txt", "w") as f:
            f.write(R.render_text(ctx))
        for src in (R.css_asset_path(), R.js_asset_path()):
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(out_dir, os.path.basename(src)))
        sys.stdout.write(f"\nSaved: {base}.html\n")
    except Exception as e:
        sys.stderr.write(f"agent-receipt: could not save files: {e}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"agent-receipt: {e}\n")
    sys.exit(0)
