---
description: Print an Agent Receipt for the current Claude Code session
---

Generate the Agent Receipt for the current session by running the plugin's
on-demand script. The script presents the interactive HTML receipt and saves it.

First, write a **task summary**: one or two short sentences, in plain natural
language, describing what *this* session has actually been about — the real
work and outcome, from your own memory of the conversation. Keep it under ~200
characters, no markdown, no slash-command names, no tool chatter. Example:
"Fixed the agent-receipt plugin so the on-demand receipt targets the correct
session and the task line reads as a plain-language summary; shipped as v1.0.x."

Then run this exactly, substituting your summary for `<SUMMARY>`. Passing the
session id Claude Code exports pins the receipt to *this* session even when the
command is run from a subdirectory of the session root; `AGENT_RECEIPT_TASK`
sets the task line to your summary (and persists it so the automatic end-of-
session receipt reuses it):

```bash
AGENT_RECEIPT_SESSION_ID="$CLAUDE_CODE_SESSION_ID" \
  AGENT_RECEIPT_TASK="<SUMMARY>" \
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/receipt_now.py"
```

Configuration is read from `~/.claude/agent-receipt/config.json`. For one-off
experiments, environment overrides such as `AGENT_RECEIPT_SHOW_FILES=1`,
`AGENT_RECEIPT_SHOW_TOOLS=1`, `AGENT_RECEIPT_PRINT_SPEED=Slow|Normal|Instant`,
and `AGENT_RECEIPT_VIEWER=browser` may be used.

After it runs, tell me the saved path and mention I can open the `.html` in a
browser for the animated version.
