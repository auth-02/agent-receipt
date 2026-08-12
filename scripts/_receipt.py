#!/usr/bin/env python3
"""Shared logic for the Agent Receipt plugin: parse a session, price it, render it."""

import os
import re
import sys
import json
import html
import hashlib
import subprocess
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────────────
SHOW_FILES = False       # include the "Files changed" section (needs git)
SHOW_TOOLS = False       # include the "Tools used" section
SHOW_TIMES = False       # include Started / Ended rows (Duration always shows)
PRINT_SPEED = "Slow"     # animation speed: "Slow" | "Normal" | "Instant"
ANIMATE = True           # feed the terminal receipt out line by line
CLEAR_SCREEN = False     # clear the screen before printing the terminal receipt
# ─────────────────────────────────────────────────────────────────────────────

STATE_DIR = os.path.join(os.path.expanduser("~"), ".claude", "agent-receipt", "state")


def _safe(name):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "unknown")


def state_path(session_id):
    os.makedirs(STATE_DIR, exist_ok=True)
    return os.path.join(STATE_DIR, _safe(session_id) + ".json")


def read_state(session_id):
    try:
        with open(state_path(session_id), "r") as f:
            return json.load(f)
    except Exception:
        return {}


def read_hook_input():
    try:
        data = sys.stdin.read()
        return json.loads(data) if data and data.strip() else {}
    except Exception:
        return {}


def receipt_out_dir():
    d = os.environ.get("AGENT_RECEIPT_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "agent-receipt", "receipts"
    )
    os.makedirs(d, exist_ok=True)
    return d


def git(args, cwd):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def is_git_repo(cwd):
    return git(["rev-parse", "--is-inside-work-tree"], cwd) == "true"


def _numstat(args, cwd, acc):
    out = git(["diff", "--numstat"] + args, cwd)
    if not out:
        return
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add, dele, path = parts
        add = 0 if add == "-" else int(add or 0)
        dele = 0 if dele == "-" else int(dele or 0)
        cur = acc.setdefault(path, [0, 0])
        cur[0] += add
        cur[1] += dele


def git_changes(cwd, start_head):
    acc = {}
    if start_head:
        _numstat([start_head + "..HEAD"], cwd, acc)
    _numstat(["--cached"], cwd, acc)
    _numstat([], cwd, acc)
    files = [(p, a, d) for p, (a, d) in acc.items()]
    files.sort(key=lambda f: (f[1] + f[2]), reverse=True)
    return files


PRICING = {
    "fable-5":    {"in": 10.0, "out": 50.0, "cw": 12.50, "cr": 1.00},
    "mythos-5":   {"in": 10.0, "out": 50.0, "cw": 12.50, "cr": 1.00},
    "opus-5":     {"in": 5.0,  "out": 25.0, "cw": 6.25,  "cr": 0.50},
    "sonnet-5":   {"in": 2.0,  "out": 10.0, "cw": 2.50,  "cr": 0.20},
    "haiku-4.5":  {"in": 1.0,  "out": 5.0,  "cw": 1.25,  "cr": 0.10},
    "opus-4.8":   {"in": 5.0,  "out": 25.0, "cw": 6.25,  "cr": 0.50},
    "opus-4.7":   {"in": 5.0,  "out": 25.0, "cw": 6.25,  "cr": 0.50},
    "opus-4.6":   {"in": 5.0,  "out": 25.0, "cw": 6.25,  "cr": 0.50},
    "opus-4.5":   {"in": 5.0,  "out": 25.0, "cw": 6.25,  "cr": 0.50},
    "sonnet-4.6": {"in": 3.0,  "out": 15.0, "cw": 3.75,  "cr": 0.30},
    "sonnet-4.5": {"in": 3.0,  "out": 15.0, "cw": 3.75,  "cr": 0.30},
    "opus-4.1":   {"in": 15.0, "out": 75.0, "cw": 18.75, "cr": 1.50},
    "opus-4":     {"in": 15.0, "out": 75.0, "cw": 18.75, "cr": 1.50},
    "sonnet-4":   {"in": 3.0,  "out": 15.0, "cw": 3.75,  "cr": 0.30},
    "haiku-3.5":  {"in": 0.80, "out": 4.0,  "cw": 1.00,  "cr": 0.08},
}

_FAMILY_FALLBACK = {
    "opus": "opus-5", "sonnet": "sonnet-5", "haiku": "haiku-4.5",
    "fable": "fable-5", "mythos": "mythos-5",
}
_FAMILIES = ("opus", "sonnet", "haiku", "fable", "mythos")


def normalize_model(model):
    parts = [p for p in (model or "").lower().replace("claude-", "").split("-") if p]
    if not parts:
        return "", ""
    family = next((p for p in parts if p in _FAMILIES), "")
    ver = [p for p in parts if p.isdigit() and len(p) <= 2]
    if not family:
        return "-".join(parts), ""
    return family + ("-" + ".".join(ver) if ver else ""), family


def price_for(model):
    key, family = normalize_model(model)
    if key in PRICING:
        return PRICING[key]
    if family in _FAMILY_FALLBACK:
        return PRICING[_FAMILY_FALLBACK[family]]
    return PRICING["sonnet-5"]


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _user_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "tool_result":
                    return None
                if b.get("type") == "text" and b.get("text"):
                    return b["text"].strip()
    return None


def parse_transcript(path):
    stats = {
        "model": None, "version": None, "title": None,
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
        "tools": {}, "first_user": None,
        "start": None, "end": None, "turns": 0,
    }
    if not path or not os.path.exists(path):
        return stats
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue

            t = parse_ts(e.get("timestamp"))
            if t:
                if stats["start"] is None or t < stats["start"]:
                    stats["start"] = t
                if stats["end"] is None or t > stats["end"]:
                    stats["end"] = t
            if e.get("version") and not stats["version"]:
                stats["version"] = e["version"]

            typ = e.get("type")
            if typ == "ai-title" and e.get("aiTitle"):
                stats["title"] = e["aiTitle"]
                continue

            msg = e.get("message") or {}
            if typ == "assistant":
                stats["turns"] += 1
                if msg.get("model"):
                    stats["model"] = msg["model"]
                u = msg.get("usage") or {}
                stats["input"] += u.get("input_tokens", 0) or 0
                stats["output"] += u.get("output_tokens", 0) or 0
                stats["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
                stats["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
                content = msg.get("content")
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            name = b.get("name", "?")
                            stats["tools"][name] = stats["tools"].get(name, 0) + 1
            elif typ == "user":
                if stats["first_user"] is None:
                    txt = _user_text(msg.get("content"))
                    if txt:
                        stats["first_user"] = txt
    return stats


def fmt_int(n):
    return f"{int(n):,}"


def fmt_dur(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def fmt_money(x):
    if x < 0:
        return f"-${abs(x):.2f}"
    return f"${x:.2f}"


def collapse_home(path):
    home = os.path.expanduser("~")
    if path and path.startswith(home):
        return "~" + path[len(home):]
    return path or ""


def cost(tokens, rate_per_mtok):
    return tokens * rate_per_mtok / 1_000_000.0


_C128 = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split(" ")


def code128_gradient(data, ink="#201e1d"):
    data = "".join(ch for ch in data if 32 <= ord(ch) <= 126) or "SESSION"
    codes = [104] + [ord(ch) - 32 for ch in data]
    checksum = 104 + sum(codes[i] * i for i in range(1, len(codes)))
    codes += [checksum % 103, 106]
    widths = [int(d) for c in codes for d in _C128[c]]
    total = sum(widths)
    stops, x = [], 0
    for i, w in enumerate(widths):
        a = x / total * 100
        b = (x + w) / total * 100
        color = ink if i % 2 == 0 else "transparent"
        stops.append(f"{color} {a:.4f}% {b:.4f}%")
        x += w
    return "linear-gradient(90deg, " + ", ".join(stops) + ")"


def build_context(hook):
    session_id = hook.get("session_id") or "unknown"
    transcript = hook.get("transcript_path")
    cwd = hook.get("cwd") or os.getcwd()

    state = read_state(session_id)
    stats = parse_transcript(transcript)

    start = parse_ts(state.get("start_time")) or stats["start"]
    end = stats["end"] or datetime.now(timezone.utc)
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    duration = (end - start).total_seconds() if start else 0

    files = []
    if SHOW_FILES and is_git_repo(cwd):
        files = git_changes(cwd, state.get("start_head"))
    files_plus = sum(f[1] for f in files)
    files_minus = sum(f[2] for f in files)

    p = price_for(stats["model"])
    total_tokens = stats["input"] + stats["output"] + stats["cache_read"] + stats["cache_write"]
    actual = (
        cost(stats["output"], p["out"])
        + cost(stats["input"], p["in"])
        + cost(stats["cache_write"], p["cw"])
        + cost(stats["cache_read"], p["cr"])
    )
    subtotal = cost(stats["output"], p["out"]) + cost(
        stats["input"] + stats["cache_write"] + stats["cache_read"], p["in"]
    )
    discount = subtotal - actual

    local_end = end.astimezone()
    local_start = start.astimezone() if start else local_end

    digits = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 10000
    receipt_no = f"AR-{local_end:%y%m}-{digits:04d}"

    task = stats["title"] or stats["first_user"] or "—"
    task = re.sub(r"\s+", " ", task).strip()
    if len(task) > 240:
        task = task[:237].rstrip() + "…"

    session_name = state.get("session_name")
    resume_target = session_name or session_id
    resume_cmd = "claude --resume " + resume_target
    ongoing = bool(hook.get("ongoing"))
    reason = hook.get("reason") or ("in progress" if ongoing else "session ended")

    return {
        "ongoing": ongoing,
        "stamp": "Ongoing" if ongoing else "Shipped",
        "receipt_no": receipt_no,
        "date_str": f"{local_end:%d %b %Y} · {local_end:%H:%M}",
        "workspace": collapse_home(cwd),
        "session_id": session_id,
        "session_name": session_name,
        "reason": reason,
        "agent": "Claude Code" + (f" {stats['version']}" if stats["version"] else ""),
        "model": stats["model"] or "unknown",
        "show_times": SHOW_TIMES,
        "started": f"{local_start:%H:%M:%S}",
        "ended": f"{local_end:%H:%M:%S}",
        "duration": fmt_dur(duration),
        "printed": f"{local_end:%H:%M:%S}",
        "task": task,
        "show_files": SHOW_FILES,
        "files": files,
        "files_plus": files_plus,
        "files_minus": files_minus,
        "show_tools": SHOW_TOOLS,
        "tools": sorted(stats["tools"].items(), key=lambda kv: kv[1], reverse=True),
        "tok_in": stats["input"],
        "tok_out": stats["output"],
        "tok_cr": stats["cache_read"],
        "tok_cw": stats["cache_write"],
        "tok_total": total_tokens,
        "subtotal": subtotal,
        "discount": discount,
        "total": actual,
        "resume_cmd": resume_cmd,
        "resume_target": resume_target,
    }


W = 42


def _ansi_enabled():
    if os.environ.get("NO_COLOR") or os.environ.get("AGENT_RECEIPT_NO_COLOR"):
        return False
    return sys.stderr.isatty()


def build_ansi(ctx, color):

    def c(code, s):
        return f"\033[{code}m{s}\033[0m" if color else s

    DIM, BOLD, CYAN, MAG = "2", "1", "36", "35"
    lines = []

    def center(s):
        s = s[:W]
        return " " * ((W - len(s)) // 2) + s

    def rule(ch="┄"):
        return c(DIM, ch * W)

    def kv(label, value):
        value = str(value)
        space = W - len(label) - len(value)
        if space < 1:
            value = value[: max(0, W - len(label) - 2)] + "…"
            space = W - len(label) - len(value)
        return f"{label}{c(DIM, '·' * max(1, space))}{value}"

    lines.append(c(DIM, ("╱" * (W // 2))[:W]))
    lines.append("")
    lines.append(c(BOLD, center("AGENT RECEIPT")))
    lines.append(c(DIM, center("SESSION SUMMARY")))
    lines.append(c(DIM, center("anthropic.com / claude / code")))
    lines.append("")
    lines.append(rule())
    lines.append(kv("Receipt no.", ctx["receipt_no"]))
    lines.append(kv("Date", ctx["date_str"]))
    lines.append(kv("Workspace", ctx["workspace"]))
    lines.append(rule())
    lines.append("")
    lines.append(c(DIM, "AGENT"))
    lines.append(kv("Agent", ctx["agent"]))
    lines.append(kv("Model", ctx["model"]))
    if ctx.get("show_times"):
        lines.append(kv("Started", ctx["started"]))
        lines.append(kv("Ended", ctx["ended"]))
    lines.append(kv("Duration", ctx["duration"]))
    lines.append("")
    lines.append(c(DIM, "TASK"))
    for wl in _wrap(ctx["task"], W):
        lines.append(c("3", wl) if color else wl)

    if ctx.get("show_files"):
        lines.append("")
        lines.append(c(DIM, "FILES CHANGED"))
        if ctx["files"]:
            for path, add, dele in ctx["files"][:12]:
                churn = f"+{add} -{dele}"
                name = _elide(path, W - len(churn) - 1)
                space = W - len(name) - len(churn)
                lines.append(name + " " * max(1, space) + c(DIM, churn))
            if len(ctx["files"]) > 12:
                lines.append(c(DIM, f"  … +{len(ctx['files']) - 12} more"))
            lines.append(kv(f"{len(ctx['files'])} files",
                            f"+{ctx['files_plus']} -{ctx['files_minus']}"))
        else:
            lines.append(c(DIM, "  (no tracked changes)"))

    if ctx.get("show_tools") and ctx["tools"]:
        lines.append("")
        lines.append(c(DIM, "TOOLS USED"))
        row = ""
        for name, n in ctx["tools"]:
            cell = f"{name} ×{n}"
            piece = ("   " + cell) if row else cell
            if len(row) + len(piece) > W:
                lines.append(row)
                row = cell
            else:
                row += piece
        if row:
            lines.append(row)

    lines.append("")
    lines.append(c(DIM, "TOKENS"))
    lines.append(kv("Input", fmt_int(ctx["tok_in"])))
    lines.append(kv("Output", fmt_int(ctx["tok_out"])))
    lines.append(kv("Cache read", fmt_int(ctx["tok_cr"])))
    lines.append(kv("Cache write", fmt_int(ctx["tok_cw"])))
    lines.append(kv("Total tokens", fmt_int(ctx["tok_total"])))
    lines.append(rule())
    lines.append(kv("Subtotal", fmt_money(ctx["subtotal"])))
    lines.append(kv("Cache discount", fmt_money(-ctx["discount"])))
    lines.append(c(BOLD, kv("IF BILLED PAY-AS-YOU-GO", fmt_money(ctx["total"]))))
    lines.append(c(DIM, center("Estimated API cost · USD")))
    lines.append(c(DIM, center("not charged to your plan")))
    lines.append("")
    lines.append(c(MAG, center(f"[ {ctx['stamp'].upper()} ]")))
    lines.append("")
    lines.append(c(DIM, center("scan or run to resume:")))
    lines.append(c(CYAN, center(ctx["resume_cmd"])))
    lines.append("")
    lines.append(c(DIM, center("thank you for shipping")))
    lines.append(c(DIM, center("no refunds on merged commits")))
    lines.append("")
    lines.append(c(DIM, ("╲" * (W // 2))[:W]))
    return lines


def render_ansi(ctx):
    return "\n".join(build_ansi(ctx, _ansi_enabled()))


def print_speed_factor():
    return {"slow": 2.4, "normal": 1.0, "instant": 0.0}.get(PRINT_SPEED.lower(), 2.4)


def animate_ansi(ctx, stream, color=True, clear=False):
    import time
    per_line = 0.045 * print_speed_factor()
    ctrl = "\033[r"
    if clear:
        ctrl += "\033[2J\033[3J\033[H"
    try:
        stream.write(ctrl)
        stream.write("\n")
        stream.flush()
    except Exception:
        pass
    for ln in build_ansi(ctx, color):
        stream.write(ln + "\n")
        stream.flush()
        d = per_line * (7 if ("SHIPPED" in ln or "ONGOING" in ln) else 1)
        if d:
            time.sleep(d)


def _wrap(text, width):
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + (1 if line else 0) > width:
            if line:
                out.append(line)
            line = w
        else:
            line = (line + " " + w) if line else w
    if line:
        out.append(line)
    return out or [""]


def _elide(path, maxlen):
    if len(path) <= maxlen:
        return path
    return "…" + path[-(maxlen - 1):]


def render_text(ctx):
    dur = ctx["duration"]
    if ctx.get("show_times"):
        dur = f"{ctx['duration']} ({ctx['started']} → {ctx['ended']})"
    rows = [
        "AGENT RECEIPT — SESSION SUMMARY",
        f"Receipt no. {ctx['receipt_no']} · {ctx['date_str']} · {ctx['workspace']}",
        f"Session      {ctx['resume_target']}",
        "",
        f"Agent        {ctx['agent']}",
        f"Model        {ctx['model']}",
        f"Duration     {dur}",
        "",
        f"Task         {ctx['task']}",
        "",
    ]
    if ctx.get("show_files"):
        rows.append(f"Files        {len(ctx['files'])} files, "
                    f"+{ctx['files_plus']} -{ctx['files_minus']}")
    if ctx.get("show_tools"):
        tools = " · ".join(f"{n} {c}" for n, c in ctx["tools"]) or "—"
        rows.append(f"Tools        {tools}")
    rows += [
        f"Tokens       {fmt_int(ctx['tok_total'])} total "
        f"(in {fmt_int(ctx['tok_in'])} / out {fmt_int(ctx['tok_out'])})",
        f"API cost     {fmt_money(ctx['total'])} if billed pay-as-you-go (est.)",
        "             not charged to your plan — flat fee covers it",
        "",
        ("STATUS: ONGOING — session in progress." if ctx.get("ongoing")
         else "STATUS: SHIPPED — thank you for shipping."),
        "",
        f"Resume: {ctx['resume_cmd']}",
    ]
    return "\n".join(rows)


CSS_FILENAME = "receipt.css"
JS_FILENAME = "receipt.js"


def _asset_path(filename):
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", filename)
    )


def css_asset_path():
    return _asset_path(CSS_FILENAME)


def js_asset_path():
    return _asset_path(JS_FILENAME)


_HTML_HEAD = (
    '<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    "<title>Agent Receipt</title>\n"
    '<link rel="stylesheet" href="' + CSS_FILENAME + '">'
)


def _h_rows(rows):
    out = []
    for label, value, mono in rows:
        cls = ' class="num"' if mono else ""
        out.append(
            f'<div class="row"><span>{html.escape(label)}</span>'
            f'<span class="lead"></span>'
            f'<span{cls}>{html.escape(str(value))}</span></div>'
        )
    return "\n".join(out)


def render_html(ctx):
    speed = PRINT_SPEED.lower()
    speed_class = {"slow": " speed-slow", "normal": "", "instant": " speed-instant"}.get(
        speed, " speed-slow"
    )

    files_section = ""
    if ctx.get("show_files"):
        if ctx["files"]:
            rows = "".join(
                f'<div class="file"><span class="name">{html.escape(path)}</span>'
                f'<span class="churn">+{add} −{dele}</span></div>\n'
                for path, add, dele in ctx["files"][:14]
            )
        else:
            rows = '<div class="note">no tracked changes</div>'
        files_section = (
            '<div class="sec">Files changed</div>\n' + rows
            + '<div class="row sumrow"><span>' + str(len(ctx["files"]))
            + ' files</span><span class="grow"></span><span class="num">+'
            + str(ctx["files_plus"]) + ' −' + str(ctx["files_minus"]) + '</span></div>'
        )

    tools_section = ""
    if ctx.get("show_tools"):
        cells = "".join(
            f'<div><span>{html.escape(name)}</span><span class="num">× {n}</span></div>\n'
            for name, n in ctx["tools"]
        ) or "<div><span>—</span></div>"
        tools_section = '<div class="sec">Tools used</div>\n<div class="tools">' + cells + "</div>"

    agent_rows = [("Agent", ctx["agent"], False), ("Model", ctx["model"], False)]
    if ctx.get("show_times"):
        agent_rows += [("Started", ctx["started"], True), ("Ended", ctx["ended"], True)]
    agent_rows.append(("Duration", ctx["duration"], True))

    barcode = code128_gradient(ctx["resume_target"])

    body = f"""<div class="wrap{speed_class}">
  <div class="kicker"><span class="blip"></span><span>Claude Code — {html.escape(ctx['reason'])}</span></div>
  <div class="paperwrap"><div class="paper">
    <div class="printhead"></div>
    <div class="title">Agent Receipt</div>
    <div class="sub">Session Summary</div>
    <div class="dom">anthropic.com / claude / code</div>
    <div class="dash d1"></div>
    {_h_rows([
        ("Receipt no.", ctx["receipt_no"], True),
        ("Date", ctx["date_str"], True),
        ("Workspace", ctx["workspace"], False),
        ("Session", ctx["resume_target"], False),
    ])}
    <div class="dash d2"></div>
    <div class="sec">Agent</div>
    {_h_rows(agent_rows)}
    <div class="sec">Task</div>
    <p class="task">{html.escape(ctx['task'])}</p>
    {files_section}
    {tools_section}
    <div class="sec">Tokens</div>
    {_h_rows([
        ("Input", fmt_int(ctx["tok_in"]), True),
        ("Output", fmt_int(ctx["tok_out"]), True),
        ("Cache read", fmt_int(ctx["tok_cr"]), True),
        ("Cache write", fmt_int(ctx["tok_cw"]), True),
    ])}
    <div class="row sumrow">
      <span>Total tokens</span><span class="grow"></span>
      <span class="num">{fmt_int(ctx['tok_total'])}</span></div>
    <div class="dash d3"></div>
    {_h_rows([
        ("Subtotal", fmt_money(ctx["subtotal"]), True),
        ("Cache discount", fmt_money(-ctx["discount"]), True),
    ])}
    <div class="sec">If billed pay-as-you-go (API)</div>
    <div class="total"><span class="lbl">Est. cost</span><span class="grow"></span>
      <span class="amt">{fmt_money(ctx['total'])}</span></div>
    <div class="estimated">Estimated API cost · USD · not charged to your plan</div>
    <div class="stamp-wrap"><div class="stamp">{ctx['stamp']}</div></div>
    <div class="barcode" style="background-image:{barcode};"
      title="{html.escape(ctx['resume_cmd'])}"></div>
    <div class="cap">Scan or run <code>{html.escape(ctx['resume_cmd'])}</code> to resume</div>
    <div class="thanks">Thank you for shipping</div>
    <div class="cap">No refunds on merged commits.</div>
    <div class="foot"><span class="chk">✓</span><span>Printed {html.escape(ctx['printed'])}</span></div>
  </div></div>
</div>"""

    return ("<!DOCTYPE html>\n<html>\n<head>\n" + _HTML_HEAD
            + "\n</head>\n<body>\n" + body
            + '\n<script src="' + JS_FILENAME + '"></script>\n</body>\n</html>\n')
