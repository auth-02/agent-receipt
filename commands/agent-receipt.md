---
description: Print an Agent Receipt for the current Claude Code session
---

Generate the Agent Receipt for the current session by running the plugin's
on-demand script, then show me the result and where it was saved.

Run this exactly (it finds this session's transcript, prints the receipt to the
terminal, and saves the HTML/TXT copy). Passing the session id Claude Code
exports pins the receipt to *this* session even when the command is run from a
subdirectory of the session root — without it the script falls back to a
working-directory guess that can mis-target a sibling session:

```bash
AGENT_RECEIPT_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/receipt_now.py"
```

Optional flags the user may have mentioned — set them on that command if asked:
`AGENT_RECEIPT_SHOW_FILES=1` (include Files changed), `AGENT_RECEIPT_SHOW_TOOLS=1`
(include Tools used), `AGENT_RECEIPT_PRINT_SPEED=Slow|Normal|Instant`,
`AGENT_RECEIPT_CLEAR=1` (clear the screen first).

After it runs, tell me the saved path and mention I can open the `.html` in a
browser for the animated version.
