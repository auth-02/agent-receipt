# Agent Receipt

A Claude Code plugin that prints a **thermal-receipt session summary** when a
coding session ends — the way a till prints a receipt when you check out.

It hooks the session lifecycle, reconstructs what happened from the session
transcript and git, and "prints" a receipt: the task, duration, token usage, and
what the session *would* cost — stamped **SHIPPED**, with a scannable Code 128
barcode of the resume command.

**About the cost.** Most people run Claude Code on a flat-fee plan (Pro / Max /
Team), so a session isn't actually billed per token. The receipt's figure is a
*hypothetical* — "what this session would cost if your agent were on
pay-as-you-go API pricing" — computed at API rates and labelled **not charged
to your plan**. That contrast is the point: it shows the value your flat plan is
absorbing, not a bill.

```
╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱

          AGENT RECEIPT
         SESSION SUMMARY
  anthropic.com / claude / code

┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
Receipt no.·······AR-2608-3942
Date·······12 Aug 2026 · 20:17
Workspace···········~/src/orbit-api
...
IF BILLED PAY-AS-YOU-GO····$0.18
    Estimated API cost · USD
    not charged to your plan

           [ SHIPPED ]
```

The design comes from the *Agent Receipt* concept in Claude Design; this plugin
is the working implementation of it.

## What it produces

Every time a session ends the plugin:

1. **Prints the ANSI thermal receipt right in the terminal** — no browser, no
   extra step. It writes to the real terminal (`/dev/tty`) and feeds the
   receipt out line by line, like paper off a thermal printer (falls back to a
   plain print if no terminal is attached).
2. Saves a self-contained **HTML receipt** in the Broadsheet look (Source
   Serif 4, paper ground, cyan/magenta press accents, a real barcode) and a
   plain-text receipt to `~/.claude/agent-receipt/receipts/`.

The terminal receipt is text + ANSI color (that's all any terminal can draw);
the HTML is the framed version with the full print animation, for when you want
to keep or share one.

## How it works

Two lifecycle hooks plus one on-demand command, all pure standard-library
Python 3 (no dependencies):

| Piece | Script | Job |
| --- | --- | --- |
| `SessionStart` hook | `scripts/session_start.py` | Records the start time and the git `HEAD` before any work — the two things only knowable at the start. |
| `SessionEnd` hook | `scripts/session_end.py` | Rebuilds the session and prints/saves the receipt. |
| `/agent-receipt` command | `scripts/receipt_now.py` | Prints a receipt for the *current* session on demand, mid-session. |

The receipt is recovered from the session **transcript** (`transcript_path` in
the hook payload):

- **Model / agent version** — from the assistant messages.
- **Tokens & hypothetical cost** — summed `usage` fields, priced per model at
  **API pay-as-you-go rates** from the table in `_receipt.py` (`claude-opus-4-8`
  → Opus rates, etc.), with a family fallback. `Subtotal` prices every token at
  the input rate; `Cache discount` is the saving from cached reads; the total is
  what the session *would* cost on the API — explicitly **not** a charge to a
  flat Pro/Max/Team plan.
- **Task** — Claude Code's own session title (the `ai-title`), falling back to
  the first user prompt.

Three sections are **opt-in** (off by default — flip a constant to include them):

- **Files changed** (`+`/`−` per file, from git: committed-since-start plus
  staged and unstaged) — `SHOW_FILES`.
- **Tools used** (counted from `tool_use` blocks) — `SHOW_TOOLS`.
- **Started / Ended** times (Duration always shows) — `SHOW_TIMES`.

If the transcript is missing, or a section's data isn't available, the receipt
still prints — it just drops what it can't fill.

## The `/agent-receipt` command

Type `/agent-receipt` any time during a session to print its receipt-so-far
without ending the session. It finds the current project's transcript, reuses
the live SessionStart state for an accurate start time, prints to the terminal,
and saves an HTML/TXT copy. A mid-session receipt is stamped **ONGOING**
instead of **SHIPPED**.

## Install

**As a plugin (recommended) — zero further config.** The plugin directory
doubles as a single-plugin marketplace. Once installed, the hooks in
`hooks/hooks.json` activate automatically the moment the plugin is enabled — you
never touch `settings.json`, and every session from then on prints its receipt.

```
/plugin marketplace add /Users/user/agents/agent-receipt
/plugin install agent-receipt@agent-receipt-marketplace
```

**Or wire the hooks directly** in `~/.claude/settings.json` (no plugin system):

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
        "command": "python3 \"/Users/user/agents/agent-receipt/scripts/session_start.py\"" } ] }
    ],
    "SessionEnd": [
      { "hooks": [ { "type": "command",
        "command": "python3 \"/Users/user/agents/agent-receipt/scripts/session_end.py\"" } ] }
    ]
  }
}
```

Requires `python3` and (for the git section) `git` on `PATH`.

## Configuration

The flags live in code — edit the constants at the top of `scripts/_receipt.py`:

```python
SHOW_FILES = False       # include the "Files changed" section (needs git)
SHOW_TOOLS = False       # include the "Tools used" section
SHOW_TIMES = False       # include Started / Ended rows (Duration always shows)
PRINT_SPEED = "Slow"     # animation speed: "Slow" | "Normal" | "Instant"
ANIMATE = True           # feed the terminal receipt out line by line
CLEAR_SCREEN = False     # clear the screen before printing the terminal receipt
```

Two things stay environment variables (they're not receipt options):

- `AGENT_RECEIPT_DIR` — where receipts are saved (default
  `~/.claude/agent-receipt/receipts`).
- `NO_COLOR` / `AGENT_RECEIPT_NO_COLOR` — disable ANSI color in the terminal
  receipt.

## The receipt animation

The saved HTML reproduces the design's "printing" animation: the paper rolls
down under a moving print-head, each line inks in a beat after the last, and the
stamp lands at the end. It's all CSS (`assets/receipt.css`) driven off one
`--pr` speed variable, and it honours `prefers-reduced-motion`. Structure, style
and behaviour are kept in separate files — the markup links `receipt.css` and
`receipt.js`, both copied next to each saved receipt so it stays portable.

`assets/receipt.js` **auto-scrolls the page** in lockstep with the animation, so
the receipt feeds out of view like paper off a printer rather than printing
below the fold; it reads the real animation timing from the CSS and bows out the
moment you scroll by hand. (The terminal receipt animates as it feeds out; the
HTML has the full CSS version.)

The terminal animation writes each line to the real terminal (`/dev/tty`) and
resets any scroll region the host TUI left set, so a normal terminal scrolls to
follow the print. Inside a live TUI a subprocess can't fully control scrolling,
so this is most reliable at real session end (when the TUI has stood down); the
browser receipt is the guaranteed-smooth one.

## Layout

```
agent-receipt/
├── .claude-plugin/
│   ├── plugin.json         plugin manifest
│   └── marketplace.json    single-plugin marketplace
├── hooks/
│   └── hooks.json          SessionStart + SessionEnd wiring
├── commands/
│   └── agent-receipt.md     the /agent-receipt slash command
├── assets/
│   ├── receipt.css         standalone stylesheet for the HTML receipt
│   └── receipt.js          auto-scroll behaviour for the HTML receipt
└── scripts/
    ├── _receipt.py         shared logic: parse, price, render (ANSI/HTML/TXT)
    ├── session_start.py    SessionStart hook
    ├── session_end.py      SessionEnd hook
    └── receipt_now.py      engine for /agent-receipt (on-demand)
```
