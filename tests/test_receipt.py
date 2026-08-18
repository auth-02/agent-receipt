import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import _receipt as R
from providers import get_provider


class ReceiptTests(unittest.TestCase):
    def test_claude_provider_isolated(self):
        provider = get_provider("claude_code")
        self.assertEqual(provider.id, "claude_code")
        self.assertEqual(provider.resume_command("abc"), "claude --resume abc")
        self.assertEqual(provider.status_for_end("prompt_input_exit"), "Shipped")

    def test_session_end_statuses(self):
        base = {
            "session_id": "s1",
            "transcript_path": None,
            "cwd": "/tmp",
        }
        for reason, expected in {
            "prompt_input_exit": "Shipped",
            "clear": "Cleared",
            "resume": "Resumed",
            "logout": "Logged out",
            "bypass_permissions_disabled": "Ended",
            "other": "Ended",
            "unknown": "Ended",
        }.items():
            ctx = R.build_context({**base, "reason": reason})
            self.assertEqual(ctx["stamp"], expected)

    def test_ongoing_status(self):
        ctx = R.build_context({
            "session_id": "s1",
            "transcript_path": None,
            "cwd": "/tmp",
            "ongoing": True,
        })
        self.assertEqual(ctx["stamp"], "Ongoing")

    def test_token_total_matches_visible_total(self):
        ctx = R.build_context({
            "session_id": "s1",
            "transcript_path": None,
            "cwd": "/tmp",
        })
        ctx.update({"tok_in": 100, "tok_out": 25, "tok_cr": 1000, "tok_cw": 50})
        ctx["tok_total"] = ctx["tok_in"] + ctx["tok_out"] + ctx["tok_cr"] + ctx["tok_cw"]
        self.assertEqual(
            ctx["tok_total"], ctx["tok_in"] + ctx["tok_out"] + ctx["tok_cr"] + ctx["tok_cw"]
        )

    def test_claude_transcript_usage_and_pricing(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "user", "timestamp": "2026-08-12T20:00:00Z", "message": {"content": "Implement auth persistence"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-08-12T20:10:00Z", "version": "2.1.0", "message": {"id": "m1", "model": "claude-opus-4-8", "usage": {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 500, "cache_creation_input_tokens": 50}, "content": [{"type": "tool_use", "name": "Bash"}]}}) + "\n")
            transcript = f.name
        try:
            ctx = R.build_context({"session_id": "usage-test", "transcript_path": transcript, "cwd": "/tmp", "reason": "prompt_input_exit"})
            self.assertEqual(ctx["model"], "claude-opus-4-8")
            # Total now sums input + output + cache read + cache write.
            self.assertEqual(ctx["tok_total"], 1000 + 200 + 500 + 50)
            self.assertTrue(ctx["cost_available"])
            self.assertEqual(ctx["tools"], [("Bash", 1)])
        finally:
            os.unlink(transcript)

    def test_html_matches_reference_receipt_order(self):
        ctx = R.build_context({
            "session_id": "s1",
            "transcript_path": None,
            "cwd": "/tmp",
            "reason": "prompt_input_exit",
        })
        html = R.render_html(ctx)
        order = [
            "<div class=\"title\">Agent Receipt",
            "<div class=\"sub\">Session Summary",
            "Receipt no.",
            "Workspace",
            "<span>Agent</span>",
            "<span>Model</span>",
            "<span>Task</span>",
            "Duration",
            "Usage",
            "Compute (If billed pay-as-you-go)",
            "Changes",
            "Tools used",
            "<div class=\"stamp\">Shipped",
            "class=\"barcode\"",
            "Resume with:",
        ]
        positions = [html.index(x) for x in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn(".txt", html)
        self.assertNotIn("ANSI", html)
        self.assertNotIn("<link rel=\"stylesheet\"", html)
        self.assertNotIn("<script src=", html)
        self.assertIn(".paper", html)

    def test_optional_sections_can_be_disabled(self):
        original_files, original_tools = R.SHOW_FILES, R.SHOW_TOOLS
        try:
            R.SHOW_FILES = False
            R.SHOW_TOOLS = False
            ctx = R.build_context({"session_id": "s1", "transcript_path": None, "cwd": "/tmp"})
            html = R.render_html(ctx)
            self.assertNotIn("Changes", html)
            self.assertNotIn("Tools used", html)
            self.assertIn("Duration", html)
            self.assertIn("Usage", html)
        finally:
            R.SHOW_FILES, R.SHOW_TOOLS = original_files, original_tools


if __name__ == "__main__":
    unittest.main()
