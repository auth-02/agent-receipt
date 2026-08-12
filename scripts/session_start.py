#!/usr/bin/env python3
"""SessionStart hook — records start time + git HEAD for the end receipt. Never blocks."""

import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _receipt as R


def main():
    hook = R.read_hook_input()
    session_id = hook.get("session_id") or "unknown"
    cwd = hook.get("cwd") or os.getcwd()

    state = {
        "session_id": session_id,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "start_head": R.git(["rev-parse", "HEAD"], cwd) if R.is_git_repo(cwd) else None,
        "cwd": cwd,
    }
    try:
        with open(R.state_path(session_id), "w") as f:
            json.dump(state, f)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
