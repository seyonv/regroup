---
description: Rebuild lost context across branches, worktrees and open Claude Code sessions. Use when the user asks what they were working on, what to commit/merge/push, which sessions can be closed, or is picking a repo back up after time away.
argument-hint: "[repo-path]"
allowed-tools: Bash, Read, Write, Edit, Artifact
---

Follow the `regroup` skill to build the board for $1 (default: the current repo).

The short version, in order:

1. `python3 scripts/collect.py <repo>` — facts only, never guessed.
2. Classify the dirty files before saying anything about them, and count dirty
   source files by extension.
3. Author `regroup.json`: the reading of that evidence — landing state and session
   state kept as separate axes, the prompt quoted verbatim, tasks and subtasks
   derived from commits and stated success criteria, and one command per card.
4. `python3 scripts/render.py regroup.json regroup.html`, publish it, look at the
   screenshot before calling it done.

Lead with what needs a decision. Most workstreams need nothing — say so plainly and
give the user permission to close them.
