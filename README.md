# Agent Receipt

**When your Claude Code session ends, you get a receipt for the work.**

Agent Receipt is a Claude Code plugin that turns every coding session into a
delightful, animated **thermal-paper receipt** — printed right onto your screen.
It reconstructs the session from the transcript and git, then prints what you
worked on, how long it took, tokens used, the hypothetical pay-as-you-go cost,
files changed, tools run, and a resume barcode.

It is deliberately **not a dashboard**. It's a checkout moment for AI-assisted
coding: the paper rolls out of a printer, the ink appears, a stamp lands, and the
receipt hangs on screen until you're done with it.

<p align="center">
  <img src="demo/agent-receipt.gif" alt="Agent Receipt printing a session summary" width="440">
</p>

## Highlights

- 🧾 **A real receipt, not a report** — aged thermal paper, a printer with a
  glowing slot, a print-head that sweeps down the page, and a physical **SHIPPED**
  stamp.
- 🖐️ **Handle the paper** — drag to read a long receipt (no scrollbar), and
  **pull the top or bottom edge** to feed blank paper from the roll.
- 📋 **Copy the resume command** — click the `claude --resume …` chip to copy it.
- 🖼️ **Save & Print again** — export the receipt as a **PNG** (native save
  dialog) or replay the print animation.
- 🧮 **Honest accounting** — token usage and an *estimated* API cost, always
  labelled **Not charged to your plan**.
- 🔌 **Provider-agnostic core** — Claude Code today, behind a small adapter
  boundary so other agents can plug in later.
- 📦 **Self-contained output** — every receipt is one standalone HTML file with
  its CSS/JS inlined; open or share it with no adjacent assets.

## What happens when a session ends

```text
Claude Code
    │
    ├── SessionStart → record start time + git HEAD (and warm the viewer)
    │
    ├── …you work normally…
    │
    └── SessionEnd
          │
          ├── reconstruct the session (transcript + git)
          ├── save one standalone HTML receipt
          └── present it
                 ├── native on-screen viewer (macOS)
                 ├── browser fallback
                 └── "Receipt unavailable" — the file is still saved
```

The native viewer is a transparent, borderless window floating over your current
screen. The receipt feeds out from the print head, plays its animation, and then
**stays until you close it** — click outside, press <kbd>Esc</kbd>, or use the ×
in the corner. There is intentionally no terminal receipt fallback and no alias
to configure.

## Interacting with the receipt

| Action | How |
| --- | --- |
| Read a long receipt | **Drag** the paper up/down (with inertia — no scrollbar) |
| Feed paper from the roll | **Pull** the top or bottom edge; it springs back |
| Copy the resume command | **Click** the `claude --resume …` chip |
| Save as an image | **Save** → native dialog writes a PNG anywhere |
| Replay the print | **Print again** |
| Close | Click outside · <kbd>Esc</kbd> · the × button |

## Session outcomes

Claude Code's `SessionEnd` event carries a termination reason. The plugin honors
it instead of calling every exit a success:

| Reason | Stamp |
| --- | --- |
| `prompt_input_exit` | **SHIPPED** |
| `clear` | **CLEARED** |
| `resume` | **RESUMED** |
| `logout` | **LOGGED OUT** |
| `bypass_permissions_disabled` / `other` | **ENDED** |
| `/agent-receipt` (mid-session) | **ONGOING** |

A session switched with `/resume` becomes its own receipt, and the barcode
encodes the session handle so the receipt doubles as a continuation point.

## What's on the receipt

Printed in a stable, physical-receipt order:

1. **Header** — receipt no., date, workspace, agent, model
2. **Task** — a plain-language summary of the session
3. **Duration**
4. **Usage** — input / output / cache-read / cache-write, and a **total** that
   sums every row shown
5. **Compute** — estimated pay-as-you-go cost (input, output, cache discount)
6. **Changes** & **Tools used** (with the top tool)
7. *(optional)* **Changed-file list**, and a **Tests** / **Git** row
8. **Status stamp** and blessing
9. **Barcode**, **resume** command, and a printed-at line

Every section can be toggled from config; the defaults match the demo above.

### About the cost

Most Claude Code users are on a flat-fee plan, so this is **not a bill**. The
amount is the hypothetical API value of the session had those tokens been billed
at pay-as-you-go API pricing. It is always labelled **Not charged to your plan**.

## Install

```text
/plugin marketplace add auth-02/agent-receipt
/plugin install agent-receipt@agent-receipt-marketplace
```

Requires **Python 3**. On macOS the native viewer (Swift + WebKit) is compiled
and warmed during `SessionStart`; if it can't launch, the saved HTML opens in
your browser instead. No alias or `settings.json` changes are needed.

## `/agent-receipt`

Run it during a live session for an **ONGOING** snapshot without ending the
session. Claude writes a one-line task summary, and the same on-screen receipt is
presented and saved.

## Configuration

Config lives at `~/.claude/agent-receipt/config.json` (see
[`config.example.json`](config.example.json)):

```json
{
  "receipt": {
    "show_files": true,
    "show_tools": true,
    "show_tokens": true,
    "show_cost": true,
    "show_barcode": true,
    "show_git": true,
    "show_tests": false,
    "show_file_list": false,
    "show_printed": true,
    "print_speed": "Slow",
    "bend": 5,
    "leader": 60
  },
  "viewer": {
    "mode": "native",
    "open_on_end": true
  }
}
```

- `print_speed` — `Slow` · `Normal` · `Instant`
- `bend` — degrees of 3D paper bend (0 = flat; auto-flattens for long receipts)
- `leader` — px of blank paper you can pull from the slot
- `viewer.mode` — `native` · `browser` · `auto`

Every key also has an environment override for one-off runs, e.g.
`AGENT_RECEIPT_PRINT_SPEED=Instant`, `AGENT_RECEIPT_SHOW_FILE_LIST=1`,
`AGENT_RECEIPT_VIEWER=browser`, `AGENT_RECEIPT_BEND=0`.

Saved receipts land in `~/.claude/agent-receipt/receipts/` as standalone HTML.

## Provider architecture

Claude Code is the only provider today, but provider-specific behavior lives
behind a small adapter, so the receipt engine never learns agent details:

```text
                    Receipt Engine
                         │  (normalized session data)
              ┌──────────┴───────────┐
       ClaudeCodeProvider        future provider
              │
        transcript parsing · model pricing
        lifecycle → stamp · resume command
```

Adding another agent means adding a provider adapter — not rewriting the engine.

## Project layout

```text
agent-receipt/
├── .claude-plugin/        plugin.json · marketplace.json
├── hooks/                 hooks.json (SessionStart / SessionEnd)
├── commands/              agent-receipt.md (/agent-receipt)
├── assets/                receipt.css · receipt.js
├── viewer/                AgentReceiptViewer.swift (native macOS viewer)
├── scripts/
│   ├── providers/         base.py · claude_code.py · __init__.py
│   ├── _receipt.py        session → priced, rendered receipt
│   ├── present_receipt.py native / browser presentation
│   ├── session_start.py · session_end.py · receipt_now.py
├── tests/                 test_receipt.py
├── config.example.json
└── demo/                  agent-receipt.gif · .mp4
```

## Development

```bash
python3 -m unittest tests.test_receipt   # run the tests
```

The receipt HTML is fully self-contained — CSS and JS are inlined at render
time, so a saved receipt has no external dependencies (no CDN fonts or scripts).
