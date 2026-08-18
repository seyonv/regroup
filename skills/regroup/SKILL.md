---
name: regroup
description: Rebuild lost context across many branches, worktrees and open Claude Code sessions. Use when the user says "/regroup", "what was I working on", "I have a bunch of branches and tabs open", "what should I commit/merge/push", "help me pick this back up", "which of these sessions can I close", or comes back to a repo after days away. Produces a pan/zoom canvas showing each workstream's original prompt, the decisions made, its tasks and subtasks, whether it is in main, and whether a session is still running — plus the command to resume or close each one.
---

# Regroup

## The problem this solves

Coming back to a repo after days away, the missing thing is not information — it is
**reassembly**. Git knows commits but not intent. Transcripts hold intent but are
unreadable. The mapping between *this terminal tab*, *this branch*, and *what I was
trying to do* lives only in the user's head, and it decays in about three days.

`/regroup` rebuilds that mapping and ranks it by what needs a human decision.

## Three rules that make it work

1. **Answer "what needs me?" before "what happened?"** Most workstreams need nothing.
   Those should recede into tombstones, not compete with the two that need a call.
2. **Never collapse independent axes.** *Is the work in main* and *is a session still
   running* are orthogonal. One badge saying "live now" answers neither question the
   user actually has. Give each axis its own encoding, always both visible.
3. **Quote the prompt verbatim.** The user's own sentence from six days ago restores
   more context than any summary of it. This is where the recognition — and the
   delight — comes from. Never paraphrase the ask.

## Workflow

### 1. Collect the facts (scripted, never guessed)

```
python3 scripts/collect.py <repo-root> > state.json
```

It gathers three independent sources:

- **git** — worktrees, branches, merge-base state, dirty files, unpushed commits
- **live processes** — `ps` + `lsof` for running `claude` processes, their cwd, their
  launch prompt (a `claude -p` headless helper is filtered out; it is not a session)
- **transcripts** — `~/.claude/projects/<slug>/*.jsonl` for each session's opening ask,
  turn count and last activity

**The key trick:** each live pid is matched to its transcript by comparing process start
time (from `ps etime`) against the transcript's first entry timestamp, claiming
nearest-first so two sessions never take the same transcript. In practice this matches
within seconds. Without it you can only guess which terminal tab holds which work.

### 2. Classify the dirty files before saying anything about them

Never report a dirty-file count as if it were the user's work. Separate:

- `git diff --numstat` on vendored/minified paths → formatter damage, revert it
- generated output (`*.html` reports, trace JSON, lockfiles) → regenerate, don't commit
- large untracked dirs → check size, they may need `.gitignore` before any `git add -A`
- **count dirty source files by extension** — "0 dirty `.swift` files anywhere" is the
  single most reassuring sentence in the whole report, and it is cheap to verify

### 3. Write the judgment (this is your job, not the script's)

Author `regroup.json`. The script supplies facts; you supply the reading. For each
workstream decide: what was this, did it land, does it need a decision, what is the one
command that acts on it. Schema:

```jsonc
{
  "repo": "...", "generated": "YYYY-MM-DD",
  "headline": { "verdict": "one imperative sentence", "reassurance": "...",
                "stats": [{"n":"58","label":"...","tone":"amber"}] },
  "actions": [{"rank":"Do now","tone":"amber","title":"...","why":"...","cmd":"..."}],
  "trunk": { "label":"main", "unpushed":58, "upstream":"origin/main",
             "nodes":[{"date":"08-16","sha":"c633b0f","title":"...","head":true}] },
  "workstreams": [{
    "id":"...", "zone":"open|chip|retired",   // open = needs you; chip = tombstone
    "gcol":7, "span":2,                        // 8-column grid; chips span 1
    "anchor":5,                                // index into trunk.nodes, or null
    "title":"...", "branch":"...", "worktree":"...",
    "landing":{"state":"unmerged|merged|none","label":"Not in main","detail":"..."},
    "session_state":{"state":"live|idle|closed|none","label":"...","detail":"..."},
    "ask":"the user's prompt, VERBATIM",
    "tree":{ "decisions":["..."],
             "tasks":[{"state":"done|unknown|open","text":"...","ref":"sha",
                       "subs":[{"state":"done","text":"..."}]}] },
    "dirty":{"count":25,"note":"no .swift — ..."},
    "verdict":"...", "next":"...",
    "act":{"label":"...","cmd":"claude --resume <session-uuid>"}
  }],
  "worktree_state": { "title":"...", "path":"...", "groups":[...] },
  "decisions": [{"date":"08-16","text":"...","tone":"moss"}],
  "method": {"title":"How this was read","items":["..."]},
  "legend": [...]
}
```

Deriving the **tree** is the highest-value work. Build tasks from commits (subject +
sha as `ref`) and from the success criteria stated in the original prompt. Mark
`unknown` — not `open` — when a bar was set but never demonstrably met; that honesty is
the point. Subtasks come from commit bodies, benchmark artifacts, and doc paths.

`act.cmd` is what turns a map into a control surface. Use `claude --resume <uuid>` (the
uuid is the transcript filename) to reopen a session, `git worktree remove …` to retire
one, `git log -p main..<branch>` to judge unmerged work.

### 4. Render and show it

```
python3 scripts/render.py regroup.json regroup.html
```

Then publish it as an Artifact and give the user the link. Take a screenshot and
**look at it** before saying it is done.

## The visual language

The page **is** the canvas; everything else floats in a small HUD. `main` runs as a
horizontal rail; open work hangs above it on dashed wires, finished worktrees sit below
on solid ones, and sessions whose work already landed become tombstones directly under
the merge that absorbed them.

Inside a card, hierarchy is carried by shape so it reads before it is read:

| shape | meaning |
|---|---|
| `“ ”` quote block, left rule | the prompt the user gave, verbatim |
| `◆` diamond on a tinted band | a decision made along the way |
| `▣` bordered node with a sha | a task |
| `└ □` indented on a spine | a subtask |

State glyphs are constant at every depth: `▣` done, `?` unknown, `□` open. Card top edge
and its wire both carry the **landing** answer, never the session answer.

Palette and type follow the skill-receipts console system — warm neutrals
(`#fbfbfa`/`#161614`), one green accent `#2f6f4f`, one rust danger `#b5432d`, hairline
rules, pill chips, monospace throughout — extended by exactly two hues, amber for idle
and violet for live.

## Traps that cost real time

- **`.world` needs `width:max-content`.** Absolutely positioned, it otherwise
  shrink-wraps to the shell and every fit calculation is wrong.
- **Default to fit-width, not fit-all.** Cards carry real reading; fitting the whole
  board shrinks them past legibility. `fitSmart` only fits all when that stays ≥0.58.
- **Top-align the open band.** One very tall card bottom-aligned pushes every short card
  to the floor and leaves a screen of void.
- **Watch class-name collisions.** `.sub` as both "subtask row" (a 12px grid column) and
  "HUD subtitle" renders the subtitle one word per line.
- **Derive wire colour from a class you did not delete.** A stale
  `className.match(/s-(\w+)/)[1]` throws on null and silently kills the whole boot —
  no wires *and* no fit, with no console error visible in a screenshot.
- **Headless screenshots**: late `setTimeout` panning does not survive
  `--virtual-time-budget`. To photograph a lower region, override the fit function
  itself rather than scheduling a pan.

## Re-running

Facts go stale within minutes — sessions exit while you work. Re-run `collect.py`
before re-rendering, and if a pid has vanished, say so in the card rather than
silently dropping it. A board that admits it changed is more trustworthy than one
that pretends it did not.
