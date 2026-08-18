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

from providers import get_provider

# ── Configuration ──────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".claude", "agent-receipt", "config.json")
_DEFAULT_CONFIG = {
    "receipt": {
        "show_files": True,
        "show_tools": True,
        "show_session": True,
        "show_tokens": True,
        "show_cost": True,
        "show_barcode": True,
        "show_git": True,
        "show_tests": False,
        "show_file_list": False,
        "show_printed": True,
        "print_speed": "Slow",
        "bend": 5,
        "leader": 60,
    },
    "viewer": {"mode": "native", "open_on_end": True},
}

def _load_config():
    cfg = json.loads(json.dumps(_DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r") as f:
            user = json.load(f)
        for section in ("receipt", "viewer"):
            if isinstance(user.get(section), dict):
                cfg[section].update(user[section])
    except Exception:
        pass
    env_bool = {
        "AGENT_RECEIPT_SHOW_FILES": ("receipt", "show_files"),
        "AGENT_RECEIPT_SHOW_TOOLS": ("receipt", "show_tools"),
        "AGENT_RECEIPT_SHOW_SESSION": ("receipt", "show_session"),
        "AGENT_RECEIPT_SHOW_TOKENS": ("receipt", "show_tokens"),
        "AGENT_RECEIPT_SHOW_COST": ("receipt", "show_cost"),
        "AGENT_RECEIPT_SHOW_BARCODE": ("receipt", "show_barcode"),
        "AGENT_RECEIPT_SHOW_GIT": ("receipt", "show_git"),
        "AGENT_RECEIPT_SHOW_TESTS": ("receipt", "show_tests"),
        "AGENT_RECEIPT_SHOW_FILE_LIST": ("receipt", "show_file_list"),
        "AGENT_RECEIPT_SHOW_PRINTED": ("receipt", "show_printed"),
        "AGENT_RECEIPT_OPEN_ON_END": ("viewer", "open_on_end"),
    }
    for env, (section, key) in env_bool.items():
        if env in os.environ:
            cfg[section][key] = os.environ[env].strip().lower() not in ("0", "false", "no", "off", "")
    if os.environ.get("AGENT_RECEIPT_PRINT_SPEED"):
        cfg["receipt"]["print_speed"] = os.environ["AGENT_RECEIPT_PRINT_SPEED"]
    if os.environ.get("AGENT_RECEIPT_VIEWER"):
        cfg["viewer"]["mode"] = os.environ["AGENT_RECEIPT_VIEWER"]
    for env, key in (("AGENT_RECEIPT_BEND", "bend"), ("AGENT_RECEIPT_LEADER", "leader")):
        if os.environ.get(env):
            try:
                cfg["receipt"][key] = float(os.environ[env])
            except ValueError:
                pass
    return cfg

CONFIG = _load_config()
SHOW_FILES = bool(CONFIG["receipt"]["show_files"])
SHOW_TOOLS = bool(CONFIG["receipt"]["show_tools"])
SHOW_SESSION = bool(CONFIG["receipt"]["show_session"])
SHOW_TOKENS = bool(CONFIG["receipt"]["show_tokens"])
SHOW_COST = bool(CONFIG["receipt"]["show_cost"])
SHOW_BARCODE = bool(CONFIG["receipt"]["show_barcode"])
SHOW_GIT = bool(CONFIG["receipt"]["show_git"])
SHOW_TESTS = bool(CONFIG["receipt"]["show_tests"])
SHOW_FILE_LIST = bool(CONFIG["receipt"]["show_file_list"])
SHOW_PRINTED = bool(CONFIG["receipt"]["show_printed"])
PRINT_SPEED = str(CONFIG["receipt"]["print_speed"])
BEND = float(CONFIG["receipt"]["bend"])
LEADER = float(CONFIG["receipt"]["leader"])
VIEWER_MODE = str(CONFIG["viewer"]["mode"])
OPEN_ON_END = bool(CONFIG["viewer"]["open_on_end"])

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


def write_state(session_id, updates):
    """Merge `updates` into the session's state file, preserving existing keys
    (start_time, start_head, cwd). Used to persist the Claude-authored task
    summary from an on-demand /agent-receipt run so the automatic SessionEnd
    receipt can reuse it. Best-effort; never raises."""
    try:
        state = read_state(session_id)
        state.update(updates)
        with open(state_path(session_id), "w") as f:
            json.dump(state, f)
    except Exception:
        pass


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


GIT_TIMEOUT = float(os.environ.get("AGENT_RECEIPT_GIT_TIMEOUT", "0.75"))

def git(args, cwd):
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT)
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


def git_summary(cwd, start_head):
    """Return (branch, commits_this_session) for the repo, or (None, None)."""
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch == "HEAD":  # detached
        branch = git(["rev-parse", "--short", "HEAD"], cwd)
    commits = None
    if start_head:
        out = git(["rev-list", "--count", start_head + "..HEAD"], cwd)
        if out is not None and out.isdigit():
            commits = int(out)
    return branch, commits


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


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
    provider = get_provider(hook.get("provider") or os.environ.get("AGENT_RECEIPT_PROVIDER") or "claude_code")

    state = read_state(session_id)
    stats = provider.parse_transcript(transcript)

    start = parse_ts(state.get("start_time")) or stats["start"]
    end = stats["end"] or datetime.now(timezone.utc)
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    duration = (end - start).total_seconds() if start else 0

    in_repo = is_git_repo(cwd)
    files = []
    if SHOW_FILES and in_repo:
        files = git_changes(cwd, state.get("start_head"))
    files_plus = sum(f[1] for f in files)
    files_minus = sum(f[2] for f in files)

    git_branch, git_commits = (None, None)
    if SHOW_GIT and in_repo:
        git_branch, git_commits = git_summary(cwd, state.get("start_head"))

    tools_sorted = sorted(stats["tools"].items(), key=lambda kv: kv[1], reverse=True)
    top_tool = tools_sorted[0][0] if tools_sorted else None

    p = provider.price_for(stats["model"])
    cost_available = p is not None
    # Total tokens is the sum of every row shown in the Usage section — input,
    # output, and cache read/write — so the displayed rows add up to the total.
    total_tokens = stats["input"] + stats["output"] + stats["cache_read"] + stats["cache_write"]
    if cost_available:
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
    else:
        actual = subtotal = discount = 0.0

    local_end = end.astimezone()

    digits = int(hashlib.md5(session_id.encode()).hexdigest(), 16) % 10000
    receipt_no = f"AR-{local_end:%y%m}-{digits:04d}"

    # Task line precedence, most-authoritative first:
    #   1. AGENT_RECEIPT_TASK — a natural-language summary Claude writes for the
    #      current session (the /agent-receipt command sets this); persisted to
    #      state so the automatic SessionEnd receipt reuses the same summary.
    #   2. state["task"] — that saved summary, on the hook path (no env var).
    #   3. ai-title — Claude Code's own generated title.
    #   4. first genuine user prompt (slash-command turns skipped).
    env_task = (os.environ.get("AGENT_RECEIPT_TASK") or "").strip()
    if env_task:
        write_state(session_id, {"task": env_task})
    task = (env_task or (state.get("task") or "").strip()
            or stats["title"] or provider.derive_title(stats["first_user"]) or "—")
    task = re.sub(r"\s+", " ", task).strip()
    if len(task) > 240:
        task = task[:237].rstrip() + "…"

    session_name = state.get("session_name")
    resume_target = session_name or session_id
    resume_cmd = provider.resume_command(resume_target)
    ongoing = bool(hook.get("ongoing"))
    reason = hook.get("reason") or ("in progress" if ongoing else "session ended")
    stamp = "Ongoing" if ongoing else provider.status_for_end(reason)

    return {
        "ongoing": ongoing,
        "stamp": stamp,
        "end_reason": reason,
        "receipt_no": receipt_no,
        "date_str": f"{local_end:%d %b %Y} · {local_end:%H:%M}",
        "workspace": collapse_home(cwd),
        "session_id": session_id,
        "session_name": session_name,
        "reason": reason,
        "provider": provider.id,
        "provider_brand": provider.brand_line(),
        "agent": provider.display_name(stats),
        "model": stats["model"] or "unknown",
        "show_session": SHOW_SESSION,
        "show_tokens": SHOW_TOKENS,
        "show_cost": SHOW_COST,
        "show_barcode": SHOW_BARCODE,
        "pricing": p,
        "cost_available": cost_available,
        "viewer_mode": VIEWER_MODE,
        "open_on_end": OPEN_ON_END,
        "bend": BEND,
        "leader": LEADER,
        "duration": fmt_dur(duration),
        "printed": f"{local_end:%H:%M:%S}",
        "show_printed": SHOW_PRINTED,
        "task": task,
        "show_files": SHOW_FILES,
        "show_file_list": SHOW_FILE_LIST,
        "files": files,
        "files_plus": files_plus,
        "files_minus": files_minus,
        "show_tools": SHOW_TOOLS,
        "tools": tools_sorted,
        "top_tool": top_tool,
        "show_git": SHOW_GIT,
        "git_branch": git_branch,
        "git_commits": git_commits,
        "show_tests": SHOW_TESTS,
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


def _html_head():
    try:
        with open(css_asset_path(), "r", encoding="utf-8") as f:
            css = f.read()
    except Exception:
        css = ""
    return (
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Agent Receipt</title>\n"
        '<style>\n' + css + '\n</style>'
    )


def _html_script():
    try:
        with open(js_asset_path(), "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


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


def _svg_icon(kind):
    icons = {
        "duration": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
        "usage": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h10v4H7zM5 8h14v11H5z"/><path d="M8 12h8M8 15h5"/></svg>',
        "compute": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/><path d="M9 9h6v6H9z"/></svg>',
        "changes": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 8l-4 4 4 4M16 8l4 4-4 4M14 4l-4 16"/></svg>',
        "tools": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 6.5a4 4 0 0 0-5.2 5.2L4 17a2.1 2.1 0 1 0 3 3l5.3-5.3a4 4 0 0 0 5.2-5.2l-2.6 2.6-2.4-.6-.6-2.4z"/></svg>',
        "tests": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/></svg>',
        "git": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="17" cy="9" r="2.4"/><path d="M6 8.4v7.2M17 11.4a5 5 0 0 1-5 5H8.4"/></svg>',
    }
    return icons.get(kind, "")


def _section_heading(label, kind=None):
    icon = _svg_icon(kind) if kind else ""
    return f'<div class="section-heading">{icon}<span>{html.escape(label)}</span></div>'


def render_html(ctx):
    speed = PRINT_SPEED.lower()
    speed_class = {"slow": " speed-slow", "normal": "", "instant": " speed-instant"}.get(
        speed, " speed-slow"
    )

    meta_rows = [
        ("Receipt no.", ctx["receipt_no"], True),
        ("Date", ctx["date_str"], True),
        ("Workspace", ctx["workspace"], False),
        ("Agent", ctx["agent"], False),
        ("Model", ctx["model"], False),
    ]

    files_tools = ""
    show_changes = bool(ctx.get("show_files"))
    show_tools = bool(ctx.get("show_tools"))
    if show_changes or show_tools:
        columns = []
        if show_changes:
            columns.append(
                f'''<div class="activity-column">{_section_heading("Changes", "changes")}
                <div class="activity-row"><span>Files changed</span><span class="num">{len(ctx["files"])}</span></div>
                <div class="activity-row"><span>Insertions</span><span class="num positive">+{fmt_int(ctx["files_plus"])}</span></div>
                <div class="activity-row"><span>Deletions</span><span class="num negative">−{fmt_int(ctx["files_minus"])}</span></div>
                </div>'''
            )
        if show_tools:
            top_tool_row = ""
            if ctx.get("top_tool"):
                top_tool_row = (
                    f'<div class="activity-row"><span>Top tool</span>'
                    f'<span class="num">{html.escape(ctx["top_tool"])}</span></div>'
                )
            columns.append(
                f'''<div class="activity-column">{_section_heading("Tools used", "tools")}
                <div class="activity-row"><span>Total tool calls</span><span class="num">{sum(n for _, n in ctx["tools"])}</span></div>
                <div class="activity-row"><span>Unique tools</span><span class="num">{len(ctx["tools"])}</span></div>
                {top_tool_row}
                </div>'''
            )
        files_tools = '<div class="activity">' + "".join(columns) + "</div>"

    # Optional detailed file list, under Changes/Tools.
    file_list_html = ""
    if ctx.get("show_files") and ctx.get("show_file_list") and ctx.get("files"):
        rows = []
        for path, add, dele in ctx["files"][:6]:
            rows.append(
                f'<div class="file-row"><span class="file-path">{html.escape(path)}</span>'
                f'<span class="file-stat"><span class="positive">+{add}</span> '
                f'<span class="negative">−{dele}</span></span></div>'
            )
        more = len(ctx["files"]) - 6
        if more > 0:
            rows.append(f'<div class="file-more">+ {more} more file{"s" if more != 1 else ""}</div>')
        file_list_html = '<div class="file-list">' + "".join(rows) + "</div>"

    # Optional Tests / Git columns.
    tests_git_html = ""
    show_git = bool(ctx.get("show_git") and ctx.get("git_branch"))
    show_tests = bool(ctx.get("show_tests"))
    if show_tests or show_git:
        tg = []
        if show_tests:
            tg.append(
                f'''<div class="activity-column">{_section_heading("Tests", "tests")}
                <div class="activity-row"><span>Passed</span><span class="num">—</span></div>
                <div class="activity-row"><span>Failed</span><span class="num">—</span></div>
                </div>'''
            )
        if show_git:
            commits = ctx.get("git_commits")
            commits_row = ""
            if commits is not None:
                commits_row = f'<div class="activity-row"><span>Commits</span><span class="num">{commits}</span></div>'
            tg.append(
                f'''<div class="activity-column">{_section_heading("Git", "git")}
                {commits_row}
                <div class="activity-row"><span>Branch</span><span class="num">{html.escape(ctx["git_branch"])}</span></div>
                </div>'''
            )
        tests_git_html = '<div class="dash"></div><div class="activity">' + "".join(tg) + "</div>"

    printed_html = ""
    if ctx.get("show_printed"):
        printed_html = (
            f'<div class="printed"><span class="printed-dot"></span>'
            f'PRINTED {html.escape(ctx["printed"])}</div>'
        )

    token_section = ""
    if ctx.get("show_tokens"):
        token_section = f'''
        <div class="dash"></div>
        <section class="receipt-section usage-section">
          {_section_heading("Usage", "usage")}
          {_h_rows([
              ("Input tokens", fmt_int(ctx["tok_in"]), True),
              ("Output tokens", fmt_int(ctx["tok_out"]), True),
              ("Cache read tokens", fmt_int(ctx["tok_cr"]), True),
              ("Cache write tokens", fmt_int(ctx["tok_cw"]), True),
          ])}
          <div class="rule"></div>
          <div class="row total-row"><span>Total tokens</span><span class="lead"></span><span class="num">{fmt_int(ctx["tok_total"])}</span></div>
        </section>'''

    cost_section = ""
    if ctx.get("show_cost"):
        if ctx.get("cost_available"):
            cost_section = f'''
        <div class="dash"></div>
        <section class="receipt-section compute-section">
          {_section_heading("Compute (If billed pay-as-you-go)", "compute")}
          {_h_rows([
              ("Input", fmt_money(cost(ctx["tok_in"], ctx["pricing"]["in"])), True),
              ("Output", fmt_money(cost(ctx["tok_out"], ctx["pricing"]["out"])), True),
              ("Cache discount", fmt_money(-ctx["discount"]), True),
          ])}
          <div class="rule"></div>
          <div class="row total-row api-total"><span>Estimated API cost</span><span class="lead"></span><span class="num">{fmt_money(ctx["total"])}</span></div>
          <div class="not-charged">Not charged to your plan</div>
        </section>'''
        else:
            cost_section = f'''
        <div class="dash"></div>
        <section class="receipt-section compute-section">
          {_section_heading("Compute (If billed pay-as-you-go)", "compute")}
          <div class="not-charged">Pricing unavailable for model {html.escape(ctx["model"])}.</div>
        </section>'''

    barcode_html = ""
    if ctx.get("show_barcode"):
        barcode = code128_gradient(ctx["resume_target"])
        barcode_html = f'''
        <div class="barcode" style="background-image:{barcode};" title="{html.escape(ctx["resume_cmd"])}"></div>
        <div class="resume-label">Resume with:</div>
        <button class="resume-command" type="button" data-copy title="Click to copy">{html.escape(ctx["resume_cmd"])}</button>'''

    style_vars = f"--cfg-bend:{ctx['bend']:g}deg;--cfg-leader:{ctx['leader']:g}px;"
    body = f'''<div class="stage{speed_class}" style="{style_vars}" data-receipt-status="{html.escape(ctx['stamp'])}">
  <button class="close" type="button" data-receipt-close aria-label="Close receipt">×</button>
  <div class="printer" aria-hidden="true"><div class="printer-slot"></div></div>
  <div class="paperwrap"><div class="paper-roll">
    <div class="pull-zone pull-top" data-pull="top" title="Pull down to feed paper from the roll"></div>
    <div class="pull-zone pull-bottom" data-pull="bottom" title="Pull to feed a blank tail"></div>
    <div class="feed-strip" data-lead></div>
    <div class="paper">
    <div class="print-head" aria-hidden="true"></div>
    <div class="paper-feed"></div>
    <header class="receipt-header">
      <div class="title">Agent Receipt</div>
      <div class="sub">Session Summary</div>
      <div class="dom">{html.escape(ctx["provider_brand"])}</div>
    </header>
    <div class="dash"></div>
    <section class="meta">{_h_rows(meta_rows)}</section>
    <div class="dash"></div>
    <section class="receipt-section task-section">
      {_section_heading("Task")}
      <div class="task-body">{html.escape(ctx['task'])}</div>
    </section>
    <div class="dash"></div>
    <section class="receipt-section duration-section">
      {_section_heading("Duration", "duration")}
      <div class="duration-value">{html.escape(ctx['duration'])}</div>
    </section>
    {token_section}
    {cost_section}
    <div class="dash"></div>
    {files_tools}
    {file_list_html}
    {tests_git_html}
    <div class="dash"></div>
    <section class="status-section">
      <div class="stamp-wrap"><div class="stamp">{html.escape(ctx['stamp'])}</div></div>
      <div class="thanks">Great work. Ship more.</div>
    </section>
    <div class="dash"></div>
    {barcode_html}
    {printed_html}
    </div>
    <div class="feed-strip feed-extra" data-extra>
      <div class="tear-hint" data-tear><span class="tear-rule"></span><span>TEAR HERE</span><span class="tear-rule"></span></div>
    </div>
    <div class="paper-curl" aria-hidden="true"><div class="paper-curl-clip"><div class="paper-curl-face"><div class="paper-curl-edges"></div></div></div><div class="paper-curl-shadow"></div></div>
  </div></div>
  <div class="actions">
    <button class="action-btn" type="button" data-action="save">Save</button>
    <button class="action-btn action-ghost" type="button" data-action="reprint">Print again</button>
  </div>
  <div class="close-hint">Drag to read · pull the paper edges to feed · click outside or press <kbd>Esc</kbd> to close</div>
</div>'''

    return ("<!DOCTYPE html>\n<html>\n<head>\n" + _html_head()
            + "\n</head>\n<body>\n" + body
            + "\n<script>\n" + _html_script() + "\n</script>\n</body>\n</html>\n")
