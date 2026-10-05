"""Tests for probe_server.turn_state: whether a session's last prompt has its answer.

Getting this wrong froze a finished conversation on the board as "working right
now", with its last question still an open task.
"""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "probe_server", Path(__file__).resolve().parent.parent / "scripts" / "probe_server.py")
probe_server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_server)


def user(text, ts, **extra):
    return dict({"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}, **extra)


def assistant(ts, stop="end_turn", content="ok"):
    return {"type": "assistant", "timestamp": ts,
            "message": {"role": "assistant", "stop_reason": stop, "content": [{"type": "text", "text": content}]}}


class TurnState(unittest.TestCase):
    def state(self, entries, **kw):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(json.dumps(e) for e in entries) + "\n")
        self.addCleanup(os.remove, path)
        return probe_server.turn_state(path, **kw)

    def test_answered(self):
        s = self.state([user("is there no other way?", "2026-10-05T17:25:49Z"),
                        assistant("2026-10-05T17:26:03Z")])
        self.assertTrue(s["answered"])
        self.assertEqual(s["last_prompt"], "is there no other way?")

    def test_mid_turn_is_not_answered(self):
        s = self.state([user("q1", "2026-10-05T10:00:00Z"), assistant("2026-10-05T10:01:00Z"),
                        user("q2", "2026-10-05T11:00:00Z"),
                        assistant("2026-10-05T11:00:05Z", stop="tool_use")])
        self.assertFalse(s["answered"])
        self.assertEqual(s["last_prompt"], "q2")

    def test_tool_results_and_injected_text_are_not_prompts(self):
        s = self.state([
            user("real question", "2026-10-05T10:00:00Z"),
            assistant("2026-10-05T10:00:30Z"),
            user([{"type": "tool_result", "content": "x"}], "2026-10-05T10:01:00Z"),
            user("<system-reminder>noise</system-reminder>", "2026-10-05T10:02:00Z"),
            user("Base directory for this skill: /x", "2026-10-05T10:03:00Z"),
            user("meta", "2026-10-05T10:04:00Z", isMeta=True)])
        self.assertTrue(s["answered"])
        self.assertEqual(s["last_prompt"], "real question")

    def test_reminder_block_before_the_typed_text(self):
        s = self.state([user([{"type": "text", "text": "<system-reminder>x</system-reminder>"},
                              {"type": "text", "text": "fix it please"}], "2026-10-05T10:00:00Z")])
        self.assertEqual(s["last_prompt"], "fix it please")
        self.assertFalse(s["answered"])

    def test_prompt_pushed_out_of_the_tail_by_a_big_entry(self):
        s = self.state([user("look at this", "2026-10-05T10:00:00Z"),
                        assistant("2026-10-05T10:00:01Z", stop="tool_use", content="x" * 5000)],
                       tail_bytes=1000)
        self.assertEqual(s["last_prompt"], "look at this")
        self.assertFalse(s["answered"])

    def test_missing_file(self):
        self.assertIsNone(probe_server.turn_state("/nonexistent/x.jsonl"))


if __name__ == "__main__":
    unittest.main()
