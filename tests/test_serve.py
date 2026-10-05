"""Tests for the parts of serve.py that decide what the page may run.

The page can only run a command after the viewer confirms it, but the server
still has to refuse anything that needs a terminal and anything Claude did not
actually write. Both filters fail silently if they are wrong, so they are pinned
down here.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("serve", SCRIPTS / "serve.py")
serve = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serve)


class Interactive(unittest.TestCase):
    """Commands that need a terminal stay copy-only."""

    def test_needs_a_terminal(self):
        for cmd in ["claude --resume 1353081c-28da-4cfa-a122-ce47fe409995",
                    "git show origin/x:docs/a.md | less",
                    "git rebase -i main",
                    "git add -p",
                    "git commit",
                    "git commit --amend",
                    "vim notes.md"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(serve.interactive(cmd))

    def test_runs_without_a_terminal(self):
        for cmd in ["git push origin main",
                    "git branch -D list",
                    "kill 63526 77105",
                    'git commit -m "x"',
                    "git cherry-pick origin/evals && git log -1 --format=%B | "
                    "grep -v -e Co-Authored-By -e Claude-Session | git commit --amend -F -",
                    "git log --oneline -3 main"]:
            with self.subTest(cmd=cmd):
                self.assertFalse(serve.interactive(cmd))


class ChatCommands(unittest.TestCase):
    """Only real, ready-to-run shell commands in an answer become runnable."""

    ANSWER = """Run `git branch -d evals && git push origin --delete evals`, then check `git log -1`.
Not `main`, not `<sha>`, and not `git rebase -i main`.

```bash
git fetch --prune
git branch -a
```

```python
print("not a shell block")
```
"""

    def test_picks_inline_and_fenced_shell(self):
        got = serve.chat_commands(self.ANSWER)
        self.assertIn("git branch -d evals && git push origin --delete evals", got)
        self.assertIn("git log -1", got)
        self.assertIn("git fetch --prune\ngit branch -a", got)

    def test_skips_words_placeholders_interactive_and_other_languages(self):
        got = serve.chat_commands(self.ANSWER)
        self.assertNotIn("main", got)
        self.assertNotIn("<sha>", got)
        self.assertNotIn("git rebase -i main", got)
        self.assertFalse(any("print(" in c for c in got))

    def test_no_duplicates(self):
        got = serve.chat_commands("`git log -1` and again `git log -1`")
        self.assertEqual(got, ["git log -1"])


class BoardCommands(unittest.TestCase):
    """The board's own commands are runnable unless they need a terminal."""

    def test_runnable_set(self):
        data = {"actions": [{"cmd": "git push origin main"},
                            {"cmd": "claude --resume abc"}],
                "workstreams": [{"act": {"cmd": "git branch -D list"}},
                                {"act": {"cmd": "git show x:y | less"}},
                                {}]}
        self.assertEqual(serve.runnable(data), {"git push origin main", "git branch -D list"})


if __name__ == "__main__":
    unittest.main()
