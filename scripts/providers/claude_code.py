"""Claude Code provider adapter for Agent Receipt."""

import json
import re
from datetime import datetime

from .base import AgentProvider


class ClaudeCodeProvider(AgentProvider):
    id = "claude_code"

    PRICING = {
        "opus-4.8":   {"in": 5.0, "out": 25.0, "cw": 6.25, "cr": 0.50},
        "opus-4.7":   {"in": 5.0, "out": 25.0, "cw": 6.25, "cr": 0.50},
        "opus-4.6":   {"in": 5.0, "out": 25.0, "cw": 6.25, "cr": 0.50},
        "opus-4.5":   {"in": 5.0, "out": 25.0, "cw": 6.25, "cr": 0.50},
        "opus-4.1":   {"in": 15.0, "out": 75.0, "cw": 18.75, "cr": 1.50},
        "opus-4":     {"in": 15.0, "out": 75.0, "cw": 18.75, "cr": 1.50},
        "sonnet-4.6": {"in": 3.0, "out": 15.0, "cw": 3.75, "cr": 0.30},
        "sonnet-4.5": {"in": 3.0, "out": 15.0, "cw": 3.75, "cr": 0.30},
        "sonnet-4":   {"in": 3.0, "out": 15.0, "cw": 3.75, "cr": 0.30},
        "haiku-4.5":  {"in": 1.0, "out": 5.0, "cw": 1.25, "cr": 0.10},
        "haiku-3.5":  {"in": 0.80, "out": 4.0, "cw": 1.00, "cr": 0.08},
    }
    FAMILY_FALLBACK = {"opus": "opus-4.8", "sonnet": "sonnet-4.5", "haiku": "haiku-4.5"}
    FAMILIES = ("opus", "sonnet", "haiku")

    _WRAP_TAGS = (
        "local-command-caveat", "command-name", "command-message", "command-args",
        "command-contents", "local-command-stdout", "system-reminder",
    )
    _WRAP_RE = re.compile(r"<(" + "|".join(_WRAP_TAGS) + r")\b[^>]*>.*?</\1>", re.S | re.I)
    _SLASH_CMD_RE = re.compile(r"^/[a-z][a-z0-9-]*(?::[a-z0-9-]+)?(?:\s|$)")

    def _user_text(self, content):
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_result":
                        return None
                    if block.get("type") == "text" and block.get("text"):
                        return block["text"].strip()
        return None

    def _clean_prompt(self, text):
        if not text:
            return ""
        text = self._WRAP_RE.sub("", text)
        text = re.sub(r"</?[a-z-]+>", "", text, flags=re.I)
        text = re.sub(r"Caveat:.*", "", text, flags=re.S | re.I)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or self._SLASH_CMD_RE.match(text):
            return ""
        return text

    def _derive_title(self, text):
        if not text:
            return None
        head = re.split(r"(?<=[.!?])\s|\n", text, maxsplit=1)[0].strip() or text
        head = re.sub(r"\s+", " ", head)
        if len(head) > 72:
            head = head[:69].rstrip() + "…"
        return head[:1].upper() + head[1:] if head else None

    @staticmethod
    def _parse_ts(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def parse_transcript(self, path):
        stats = {
            "model": None, "version": None, "title": None,
            "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
            "tools": {}, "first_user": None, "start": None, "end": None,
            "turns": 0,
        }
        if not path:
            return stats
        try:
            f = open(path, "r", errors="replace")
        except OSError:
            return stats
        seen_msg_ids = set()
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue

                timestamp = self._parse_ts(event.get("timestamp"))
                if timestamp:
                    stats["start"] = min(stats["start"], timestamp) if stats["start"] else timestamp
                    stats["end"] = max(stats["end"], timestamp) if stats["end"] else timestamp
                if event.get("version") and not stats["version"]:
                    stats["version"] = event["version"]

                typ = event.get("type")
                if typ == "ai-title" and event.get("aiTitle"):
                    stats["title"] = event["aiTitle"]
                    continue

                message = event.get("message") or {}
                if typ == "assistant":
                    message_id = message.get("id")
                    if message_id and message_id in seen_msg_ids:
                        continue
                    if message_id:
                        seen_msg_ids.add(message_id)
                    model = message.get("model")
                    if model and model != "<synthetic>":
                        stats["model"] = model
                    stats["turns"] += 1
                    usage = message.get("usage") or {}
                    stats["input"] += usage.get("input_tokens", 0) or 0
                    stats["output"] += usage.get("output_tokens", 0) or 0
                    stats["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                    stats["cache_write"] += usage.get("cache_creation_input_tokens", 0) or 0
                    content = message.get("content")
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                name = block.get("name", "?")
                                stats["tools"][name] = stats["tools"].get(name, 0) + 1
                elif typ == "user" and stats["first_user"] is None:
                    text = self._clean_prompt(self._user_text(message.get("content")))
                    if text:
                        stats["first_user"] = text
        return stats

    def normalize_model(self, model):
        parts = [p for p in (model or "").lower().replace("claude-", "").split("-") if p]
        if not parts:
            return "", ""
        family = next((p for p in parts if p in self.FAMILIES), "")
        version = [p for p in parts if p.isdigit() and len(p) <= 2]
        if not family:
            return "-".join(parts), ""
        return family + ("-" + ".".join(version) if version else ""), family

    def derive_title(self, text):
        return self._derive_title(text)

    def price_for(self, model):
        key, family = self.normalize_model(model)
        if key in self.PRICING:
            return self.PRICING[key]
        fallback = self.FAMILY_FALLBACK.get(family)
        return self.PRICING.get(fallback) if fallback else None

    def display_name(self, stats):
        return "Claude Code" + (f" {stats['version']}" if stats.get("version") else "")

    def brand_line(self):
        return "anthropic.com / claude / code"

    def resume_command(self, target):
        return "claude --resume " + target

    def status_for_end(self, reason):
        return {
            "clear": "Cleared",
            "resume": "Resumed",
            "logout": "Logged out",
            "prompt_input_exit": "Shipped",
            "bypass_permissions_disabled": "Ended",
            "other": "Ended",
        }.get(reason, "Ended")
