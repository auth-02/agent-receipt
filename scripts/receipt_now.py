#!/usr/bin/env python3
"""On-demand receipt for the current Claude Code session."""

import os
import sys
import glob
import json
import subprocess

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


def _present(path):
    presenter = os.path.join(os.path.dirname(os.path.abspath(__file__)), "present_receipt.py")
    try:
        return subprocess.run(
            [sys.executable, presenter, path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
        ).stdout.strip()
    except Exception:
        return "unavailable"


def main():
    cwd = os.getcwd()
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

    out_dir = R.receipt_out_dir()
    base = os.path.join(out_dir, "agent-receipt-" + ctx["receipt_no"])
    html_path = base + ".html"
    try:
        with open(html_path, "w") as f:
            f.write(R.render_html(ctx))
    except Exception as e:
        sys.stderr.write(f"agent-receipt: could not save receipt: {e}\n")
        return

    method = _present(html_path)
    if method == "unavailable":
        sys.stderr.write(f"Agent Receipt: receipt unavailable. Saved at {html_path}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"agent-receipt: {e}\n")
    sys.exit(0)
