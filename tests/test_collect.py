"""Tests for the parts of collect.py with real edge cases.

The git and process calls are shelling out to the machine and are not worth
faking; what is worth testing is the parsing and the matcher, because both have
silent-wrong-answer failure modes.
"""

import importlib.util
import time
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "collect", Path(__file__).resolve().parent.parent / "scripts" / "collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


class EtimeSeconds(unittest.TestCase):
    """`ps -o etime` uses three different shapes depending on age."""

    def test_minutes_seconds(self):
        self.assertEqual(collect.etime_seconds("05:22"), 322)

    def test_hours_minutes_seconds(self):
        self.assertEqual(collect.etime_seconds("02:01:06"), 7266)

    def test_days_hours_minutes_seconds(self):
        self.assertEqual(collect.etime_seconds("06-18:32:18"), 6 * 86400 + 18 * 3600 + 32 * 60 + 18)

    def test_zero(self):
        self.assertEqual(collect.etime_seconds("00:00"), 0)

    def test_multi_digit_days(self):
        self.assertEqual(collect.etime_seconds("13-00:00:00"), 13 * 86400)


class Humanize(unittest.TestCase):
    def test_minutes_only(self):
        self.assertEqual(collect.humanize(322), "5m")

    def test_hours_and_minutes(self):
        self.assertEqual(collect.humanize(7266), "2h 1m")

    def test_days_and_hours(self):
        self.assertEqual(collect.humanize(6 * 86400 + 18 * 3600), "6d 18h")

    def test_rounds_down_not_up(self):
        self.assertEqual(collect.humanize(119), "1m")


class SlugFor(unittest.TestCase):
    """Claude Code's project-directory name; a wrong slug finds no transcripts."""

    def test_slashes_become_dashes(self):
        self.assertEqual(collect.slug_for("/Users/me/src/app"), "-Users-me-src-app")

    def test_underscores_and_dots_also_become_dashes(self):
        self.assertEqual(
            collect.slug_for("/Users/me/delightful_note_experience"),
            "-Users-me-delightful-note-experience")

    def test_hidden_worktree_path(self):
        self.assertEqual(
            collect.slug_for("/repo/.claude/worktrees/x"),
            "-repo--claude-worktrees-x")


class LinkSessionsToTranscripts(unittest.TestCase):
    """A pid and its transcript share a cwd and start within seconds."""

    def _session(self, pid, cwd, start):
        return {"pid": pid, "cwd": cwd, "start_epoch": start,
                "launch_prompt": "", "uptime_human": "1h 0m"}

    def _tx(self, sid, cwd, first_ts, prompt="ask"):
        return {"session_id": sid, "cwd": cwd, "first_ts": first_ts,
                "first_prompt": prompt, "branch": "main", "user_turns": 1, "mtime": first_ts}

    def test_matches_nearest_in_time(self):
        now = time.time()
        s = [self._session(1, "/r", now)]
        t = [self._tx("far", "/r", now - 3000), self._tx("near", "/r", now - 2)]
        collect.link_sessions_to_transcripts(s, t)
        self.assertEqual(s[0]["transcript_id"], "near")
        self.assertEqual(s[0]["intent"], "ask")

    def test_two_sessions_never_claim_one_transcript(self):
        now = time.time()
        s = [self._session(1, "/r", now), self._session(2, "/r", now + 1)]
        t = [self._tx("a", "/r", now), self._tx("b", "/r", now + 40)]
        collect.link_sessions_to_transcripts(s, t)
        ids = {x["transcript_id"] for x in s}
        self.assertEqual(ids, {"a", "b"}, "each session must claim a distinct transcript")

    def test_different_cwd_never_matches(self):
        now = time.time()
        s = [self._session(1, "/r", now)]
        t = [self._tx("elsewhere", "/other", now)]
        collect.link_sessions_to_transcripts(s, t)
        self.assertIsNone(s[0]["transcript_id"])

    def test_beyond_tolerance_never_matches(self):
        now = time.time()
        s = [self._session(1, "/r", now)]
        t = [self._tx("old", "/r", now - 99999)]
        collect.link_sessions_to_transcripts(s, t)
        self.assertIsNone(s[0]["transcript_id"])

    def test_launch_prompt_wins_over_transcript(self):
        """A `claude "do the thing"` invocation states its intent directly."""
        now = time.time()
        s = [self._session(1, "/r", now)]
        s[0]["launch_prompt"] = "build the honesty layer"
        t = [self._tx("x", "/r", now, prompt="something else")]
        collect.link_sessions_to_transcripts(s, t)
        self.assertEqual(s[0]["intent"], "build the honesty layer")

    def test_marks_live_transcripts(self):
        now = time.time()
        s = [self._session(1, "/r", now)]
        t = [self._tx("live", "/r", now), self._tx("dead", "/r", now - 99999)]
        collect.link_sessions_to_transcripts(s, t)
        self.assertTrue(t[0]["live"])
        self.assertFalse(t[1]["live"])


if __name__ == "__main__":
    unittest.main()
