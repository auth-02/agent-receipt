# Agent Receipt

A Claude Code plugin that turns the end of a coding session into a **thermal receipt** — printed as a small animated receipt directly on your screen.

It reconstructs the session from the transcript and git, then shows what you worked on, how long it took, token usage, hypothetical API cost, changes, tools and a resume barcode.

The receipt is deliberately **not a dashboard**. It is a checkout moment for AI-assisted coding.

```text
╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱

          AGENT RECEIPT
         SESSION SUMMARY
  anthropic.com / claude / code

┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
Receipt no.·······AR-2608-3942
Date·······12 Aug 2026 · 20:17
Workspace···········~/src/orbit-api
Agent···············Claude Code
Model···············claude-opus-4-8
Task················Implement session persistence

┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄

◷  DURATION                         27m 14s

◈  USAGE
   Input tokens····················18,732
   Output tokens·················· 7,512
   Cache read tokens··············12,104
   ─────────────────────────────────────
   Total tokens···················26,244

▣  COMPUTE (IF BILLED PAY-AS-YOU-GO)
   Input··························  $0.12
   Output·························  $0.06
   Cache discount················· -$0.00
   ─────────────────────────────────────
   Estimated API cost·············· $0.18
   Not charged to your plan

   CHANGES       🔧 TOOLS USED
   Files changed  8       Total tool calls  37
   Insertions   +421       Unique tools      12
   Deletions     -87

             [ SHIPPED ]

          Great work. Ship more.

                 ║║║║║║║║║║║
             Resume with:
          claude --resume AR-2608-3942
```

## What happens when a session ends

```text
Claude Code
    │
    ├── SessionStart → record start + git HEAD
    │
    ├── work normally
    │
    └── SessionEnd
          │
          ├── reconstruct session
          ├── save one standalone HTML receipt
          └── present receipt
                 │
                 ├── native on-screen viewer (macOS)
                 ├── browser fallback
                 └── "Receipt unavailable" if neither works
```

The native viewer is a transparent, borderless window over the current screen. The receipt feeds out from a small print head, plays its ink/stamp animation, and then **stays visible until you close it**. Clicking outside or pressing `Esc` closes it.

There is intentionally **no terminal receipt fallback** and no alias required.

## Session lifecycle

Claude Code's `SessionEnd` event supplies a termination reason. The plugin preserves that reason instead of treating every exit as a successful shipment:

| Reason | Receipt stamp |
| --- | --- |
| `prompt_input_exit` | **SHIPPED** |
| `clear` | **CLEARED** |
| `resume` | **RESUMED** |
| `logout` | **LOGGED OUT** |
| `bypass_permissions_disabled` | **ENDED** |
| `other` | **ENDED** |

`/agent-receipt` remains a manual **ONGOING** snapshot. Interrupting an individual agent turn does not create a receipt unless Claude Code actually emits `SessionEnd`.

A session switched with `/resume` is treated as its own receipt. The resume barcode points back to the session ID so the receipt can be used as a continuation point.

## Receipt contents

The field order is intentionally stable and follows the physical-receipt design:

1. Receipt number, date, workspace, agent, model and task
2. Duration
3. Token usage
4. Hypothetical pay-as-you-go compute cost
5. Changes and tools used
6. Status stamp
7. Resume barcode

Files, tools, start/end timestamps, token usage, cost and barcode can be independently configured. The default configuration matches the full receipt shown above.

### About cost

Most Claude Code users are on a flat-fee plan, so this is **not a bill**. The amount is the hypothetical API value of the session if those tokens had been consumed through pay-as-you-go API pricing. It is explicitly labelled **Not charged to your plan**.

## Provider architecture

Claude Code is the only provider today, but provider-specific behavior is isolated behind a small adapter boundary:

```text
                    Receipt Engine
                         │
                 normalized session data
                         │
              ┌──────────┴──────────┐
              │                     │
       ClaudeCodeProvider       future provider
              │
        transcript parsing
        model pricing
        lifecycle mapping
        resume command
```

The receipt renderer, storage, native viewer and browser fallback do not know how a provider produced the session data.

Adding another agent later should mean adding a provider adapter rather than rewriting the receipt engine.

## Install

**As a Claude Code plugin:**

```text
/plugin marketplace add auth-02/agent-receipt
/plugin install agent-receipt@agent-receipt-marketplace
```

No alias or `settings.json` changes are required when installed as a plugin.

Requires Python 3. On macOS, the native viewer is compiled and warmed during `SessionStart`; the saved HTML is used directly if the native viewer cannot be launched.

## Configuration

Configuration lives at:

```text
~/.claude/agent-receipt/config.json
```

Example:

```json
{
  "receipt": {
    "show_files": true,
    "show_tools": true,
    "show_times": false,
    "show_tokens": true,
    "show_cost": true,
    "show_barcode": true,
    "print_speed": "Slow"
  },
  "viewer": {
    "mode": "native",
    "open_on_end": true
  }
}
```

`viewer.mode` can be `native`, `browser`, or `auto`.

The receipt is saved as a **single standalone HTML file** under:

```text
~/.claude/agent-receipt/receipts/
```

CSS and JavaScript are embedded into the saved receipt, so the file can be opened or shared without adjacent assets.

## `/agent-receipt`

During a live Claude Code session, run:

```text
/agent-receipt
```

It creates a snapshot without ending the session. The receipt is stamped **ONGOING** and uses the same presentation surface as the final receipt.

## Project layout

```text
agent-receipt/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── hooks/
│   └── hooks.json
├── commands/
│   └── agent-receipt.md
├── assets/
│   ├── receipt.css
│   └── receipt.js
├── viewer/
│   └── AgentReceiptViewer.swift
├── config.example.json
└── scripts/
    ├── providers/
    │   ├── base.py
    │   ├── claude_code.py
    │   └── __init__.py
    ├── _receipt.py
    ├── present_receipt.py
    ├── session_start.py
    ├── session_end.py
    └── receipt_now.py
```
