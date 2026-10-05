---
name: regroup
description: Rebuild lost context across many branches, worktrees and open Claude Code sessions, local or in Claude Code cloud. Use when the user says "/regroup", "what was I working on", "I have a bunch of branches and tabs open", "what should I commit/merge/push", "help me pick this back up", "which of these sessions can I close", or comes back to a repo after days away. Produces a pan/zoom canvas showing each workstream's original prompt, the decisions made, its tasks and subtasks, whether it is in main, and whether a session is still running — plus the command to resume or close each one.
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
   user actually has. Give each axis its own encoding, always both visible. *Where it
   ran* (this Mac or Claude Code cloud) is a third axis with its own badge.
3. **Quote the prompt verbatim.** The user's own sentence from six days ago restores
   more context than any summary of it. This is where the recognition — and the
   delight — comes from. Never paraphrase the ask.

## Workflow

### 1. Collect the facts (scripted, never guessed)

```
python3 scripts/collect.py <repo-root> > state.json
python3 scripts/collect.py --since-days=120 <repo-root> > state.json   # look further back
```

It gathers three independent sources:

- **git** — worktrees, branches, merge-base state, dirty files, unpushed commits
- **live processes** — `ps` + `lsof` for running `claude` processes, their cwd, their
  launch prompt (a `claude -p` headless helper is filtered out; it is not a session)
- **transcripts** — `~/.claude/projects/<slug>/*.jsonl` for each session's opening ask,
  turn count and last activity

### 1b. How far back it can see, and the two things that hide history

`--since-days` (default 30) is the transcript window. Raising it is free, but on
most machines it will not find more, because **Claude Code deletes transcripts
after 30 days** — `cleanupPeriodDays` in `~/.claude/settings.json`, unset by
default. Check the oldest file on disk before promising a longer horizon:

```
ls -lt ~/.claude/projects/<slug>/*.jsonl | tail -1
```

If it sits exactly 30 days back, history is being pruned right now. Setting
`cleanupPeriodDays` higher preserves what is left; it never resurrects what is
gone. Say so plainly rather than reporting a clean 90-day read that is really a
30-day one.

**The bigger blind spot is retired worktrees.** `git worktree list` only knows
the trees still on disk, so a lane deleted after it merged takes its whole
session with it — and those are exactly the nights you no longer remember. The
transcripts survive under their own project dir. Two shapes, handled differently
because only one of them can be identified safely:

- a worktree **inside** the repo has a slug that extends the repo's own
  (`…-delightful-note-experience--claude-worktrees-suggest-honesty`). Unambiguous,
  so `nested_worktree_dirs` includes it automatically.
- a lane checked out **beside** the repo (`…-repos-grove-nights-caret`) shares no
  slug prefix, and nothing inside the transcript reliably says which repo it
  served. `sibling_candidates` lists every sibling with its session count, size,
  last-touched date and how often it names the repo — as evidence, not a filter.
  Pass the ones you recognise: `--also-dir=<slug>` (repeatable, accepts a path too).

Never auto-include on a name match. A count of two hits fires on unrelated repos
that merely mentioned this one in passing; on the run that motivated this note it
dragged in four foreign projects and still missed three of the four real lanes,
which had never named the main checkout at all.

Lanes launched headless have **no opening user prompt** — `first_prompt` is empty
and `user_turns` is 0. Do not render that as a missing ask. Their intent is in the
branch's commits and whatever `SUMMARY.md` the lane wrote before it stopped.

**The key trick:** each live pid is matched to its transcript by comparing process start
time (from `ps etime`) against the transcript's first entry timestamp, claiming
nearest-first so two sessions never take the same transcript. In practice this matches
within seconds. Without it you can only guess which terminal tab holds which work.

### 1c. Cloud sessions: the work that leaves no trace on this Mac

A Claude Code cloud session (claude.ai/code, or `&`/remote from the CLI) has no
process here and no transcript under `~/.claude/projects`, so everything above misses
it. It does leave two traces, and `collect.py` reads one of them:

- **git** (scripted, in `state.json` → `cloud`): it runs `git fetch --prune`
  (`--no-fetch` to skip) and lists every remote branch not in main. A branch counts as
  cloud-made when its commits are authored by `noreply@anthropic.com`, the cloud
  container's identity, or it is named `claude/*`. Each commit's `Claude-Session:`
  trailer gives the session URL. Do not use the trailer alone as the signal: local
  sessions can write it too. `cloud.landed` lists cloud-authored commits already on main.
- **ListAgents** (call it yourself): it lists the account's cloud sessions with a title
  and idle/running state, but not their repo. Match a title to a branch only when the
  branch slug clearly echoes it (`claude/product-vision-strategy-…` ↔ "Product vision
  and strategy exploration"), and say "likely" in the card. Cloud sessions with no
  branch on this repo go in the method note as unattributed, never onto the board.

On the board, every cloud workstream gets `"runtime": "cloud"` and `"cloud_url"`.
The renderer then draws a solid blue CLAUDE CODE CLOUD badge above the title (cards and
chips), a blue left edge, and the session link in the meta block. Local workstreams take
`"runtime": "local"`, or nothing. Add the `runtime` row to the legend, and count cloud
branches in the headline stats (tone `cloud`).

The opening prompt of a cloud session is not readable from here. Leave `ask` empty and
say so in the verdict; never reconstruct it from the commit message. Intent comes from
the branch's commits and the docs it wrote. Cloud commits usually carry
`Co-Authored-By` and `Claude-Session` trailers; if the user's rules forbid those, the
landing command must strip them (cherry-pick, then `git commit --amend` with the
trailers filtered out). Do not suggest a plain merge.

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
    "runtime":"local|cloud", "cloud_url":"https://claude.ai/code/session_…",  // cloud only
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

**Read the turn before writing a session's state.** `collect.py` gives every
transcript a `turn` (from its tail, via `probe_server.turn_state`): `answered`,
`last_prompt`, `answered_at`, and `recent_prompts`. A running pid is not a working
session. Only `answered: false` justifies "Working right now" or an `open` task
for the last question. With `answered: true` the session is idle and waiting on
the user, and `recent_prompts` often shows they already closed the loop ("we can
close this session"). Never take "the last question" from `prompts`: that list
comes from the head of the transcript. Any task for a question still in flight
gets `"done": [{"answered": "<uuid>"}]` so it ticks itself when the answer lands.

Deriving the **tree** is the highest-value work. Build tasks from commits (subject +
sha as `ref`) and from the success criteria stated in the original prompt. Mark
`unknown` — not `open` — when a bar was set but never demonstrably met; that honesty is
the point. Subtasks come from commit bodies, benchmark artifacts, and doc paths.

**One action per independent decision.** Never bundle things that land, drop or
finish separately ("decide the three cloud branches") into one action. The title
reads as "all of these must happen together", one command can only act on one of
them, and one done check can't show partial progress. Give each its own title,
reason, command and `done` check, and say in the reason that it is independent.

`act.cmd` is what turns a map into a control surface. Use `claude --resume <uuid>` (the
uuid is the transcript filename) to reopen a session, `git worktree remove …` to retire
one, `git log -p main..<branch>` to judge unmerged work.

### 3b. Fill the chips, set `repo_path`

Chips open in place when clicked, showing the same body as a card. So give every chip
an `ask` (verbatim, from the transcript), a `tree` built from its commit bodies, a
`verdict`, and an `act` (usually `claude --resume <uuid>`). A chip with only a title
gives the reader nothing to open. Set top-level `"repo_path"` to the repo's absolute
path (`state.json` → `git.root`), because the chat's git tools need it.
`"chat": {"suggestions": [...]}` is optional: two or three questions this board
invites.

### 4. Serve it locally (the main experience)

Keep boards in `~/.claude/regroup/<repo-slug>/`: `regroup.json` is the current
board, and copy it to `boards/<YYYY-MM-DD-HHMM>.json` too so earlier boards are kept.
Then start the server detached, so it outlives this session, and give the user the URL:

```
nohup python3 scripts/serve.py ~/.claude/regroup/<slug>/regroup.json > ~/.claude/regroup/<slug>/server.log 2>&1 & disown
```

`serve.py` opens the board in the browser on 127.0.0.1 (port 4777 or the next free
one; `server.json` beside the board records it, and a second start just reopens the
running one). It renders `regroup.json` fresh on every load, so after re-running the
skill the user reloads once. It exits after 30 minutes with no request. Behind the page:

- **`/api/probe`**: `probe_server.probe()`, the same read-only snapshot as the MCP
  server, in parallel, ~60–200 ms. The page checks on load, every 4 s while visible,
  and the moment the viewer comes back (focus, visibility, first pointer move after a
  pause). Results are applied in place: actions strike through, cards dim with a
  "done" stamp, tags relabel, only what changed pulses once. Never a reload, never a
  camera move.
- **`/api/run`**: every runnable command on the board (`actions[].cmd`,
  `workstreams[].act.cmd`) gets a **run** button that opens an inline confirm showing
  the exact command (red for kill, `branch -D`, `worktree remove`, reset, rm). The
  server runs only exact command strings that appear on the board, in `repo_path`, and
  never interactive ones (`claude …`, `| less`), which stay copy-only. After a run the
  board re-checks at once.
- **`/api/chat`**: `claude -p` in the repo on the user's plan, streamed. It gets the
  board plus a fresh probe as its system prompt, and read-only tools (Read, Grep, Glob, read-only git,
  `--add-dir` on the repo's transcripts). `--strict-mcp-config --setting-sources project`
  skips user hooks and MCP startup, which halves time to first word (~2 s vs ~4 s);
  `--bare` would skip more but needs an API key, so not that. Sonnet by default, Opus
  with "think longer". `--no-session-persistence`, so the chat's own calls never show
  up as sessions on the next board. An answer ending `[[focus:<id>]]` flies the board
  to that card.
- **Commands in chat answers run too.** When an answer finishes, the server pulls
  the shell commands out of it: fenced `bash` blocks, and inline code starting with a
  known command. Those become runnable for this server's lifetime and get the same
  run button and inline confirm in the chat. The run output lands in the chat and the
  board re-checks at once.
  The system prompt tells Claude to write ready-to-run commands with no placeholders.
  Placeholders (`<id>`), `sudo` and anything interactive are never runnable. That means
  `claude …`, pagers, editors, `git rebase -i`, `add -p`, and `git commit` without `-m`/`-F`
  (`INTERACTIVE` in serve.py). Those stay copy-only.
- **Saved state beside the board:** `marks.json` holds manual "mark done" ticks,
  keyed by action title (never by position: splitting an action once shifted every
  tick). `chats/<id>.json` holds one file per chat conversation. The clock icon in the chat header lists past
  chats; any one reopens and continues, with run buttons restored. The latest
  chat reopens on reload if it's under 6 h old. "+" starts a new one.
- **GitHub-side changes:** the probe runs `git fetch --prune` and `gh pr list` in a
  background thread at most once a minute, never on the request path. Subjects are
  matched on `main` and `main@{upstream}`. When main is behind its upstream, the top
  bar shows "↓N to pull" with a `git pull --ff-only` run button (a built-in command).
  A squash merge rewrites the commit title, so land checks for branches should not
  rely on `on_main` alone. Use `{"any": [{"on_main": …}, {"path_on_main": "<a file the
  branch adds>"}, {"pr_merged": "<head branch>"}, {"remote_gone": …}]}`.
- **Security:** every `/api` call needs the per-start token injected into the page,
  and the Host header must be 127.0.0.1 or localhost, so no other site can drive it.

**Live data in `regroup.json`:**

```jsonc
"repo_path": "/abs/path",
"actions":    [{ …, "done": [check, …] }],          // all must pass
"workstreams":[{ …, "pid": 63526,                    // session tag flips to closed when it exits
                    "done": [check, …],              // card dims + "done" stamp
                    "live": [{"when": [check], "landing": {"state","label","detail"}}] }],
"known": {"branches": [], "remote_branches": [], "worktrees": [], "pids": [], "sessions": [transcript ids]}
```

Tasks inside `tree.tasks` take the same `done` list and tick themselves, and the
"N of M done" count follows. Every card with a `pid` and a `claude --resume <uuid>`
command (or `session_id`) also has its session turn probed. If the pid is alive and
the last prompt is answered, the tag becomes "Idle, answered". A card whose
`landing.state` is `none` (nothing to land) closes itself when its pid exits,
because it is a closed loop.

A check is one of `{"pushed": true}`, `{"answered": "<session uuid>"}` (the last
typed prompt has an answer that ended after it), `{"branch_gone": name}`, `{"remote_gone": "origin/x"}`,
`{"worktree_gone": path}`, `{"pid_gone": n}`, `{"on_main": "commit subject prefix"}`
(matches cherry-picks and merges alike), or `{"any": [check, …]}`. Give every action a
`done` list unless nothing can verify it (hand tests); those get a "mark done" tick
saved in the browser. `known` is what the board was built with. Anything the probe sees
beyond it (a new branch, worktree or session; a resumed known session is recognised
by its transcript id in the command line) shows as **+N new** in the top bar,
prompting a re-run of `/regroup`.

Test it in a real browser before handing it over. Drive it over the DevTools
protocol: click run, confirm, read the result. Take a screenshot and **look at it**.

### 4b. Optional: an artifact snapshot

When the user wants a link (phone, another machine, sharing), also render to a file
(`python3 scripts/render.py regroup.json regroup.html`) and publish it as an Artifact
with `{"sample": {}, "mcp": {"servers": [{"server": "host:git", "tools": ["git_status",
"git_log", "git_show", "git_diff", "git_branch"]}, {"server": "host:regroup", "tools": ["probe"]}]}}`.
The same page detects it isn't local and falls back to its artifact behaviour: the chat answers
from the board on the viewer's plan (`sample`, with a `focus_card` tool), and live
checks plus git come through the local MCP servers `regroup` (`probe_server.py`) and
`git` (`uvx mcp-server-git`), registered in the Claude desktop app. Those
answer only for the owner inside the desktop app, at most every 30 s. There are no run
buttons: an artifact can only hand over commands.

## The visual language

The page **is** the canvas. Chrome gets one 46px top bar and the shell starts *below*
it, so nothing ever covers the work: the bar carries the greeting, a one-line count, the
zoom controls, and three buttons that open the overview, the legend, and the actions
drawer on demand. All of them start closed, only one opens at a time, and a click on the
canvas dismisses them.

`main` runs as a horizontal rail; open work hangs above it on dashed wires, finished
worktrees sit below on solid ones, and sessions whose work already landed become
tombstones directly under the merge that absorbed them.

**White means it needs you; hatched means it's context.** A closed loop is shown
three ways at once and stays that way when opened:
- a grey hatched ground
- a solid "✓ Done · closed loop, kept for context" stamp
- strike-through on its title, next step and command, plus a faded wire

Chips and finished lanes are closed by default. `"closed": true` closes any card, and `"closed": false` keeps a
chip open. Cards with live `done` checks close themselves the moment the check passes.
Never let a finished card look like open work: the reader uses the board to decide
what to ignore.

**Chips open.** Clicking a chip widens it to two columns and reveals its prompt,
tasks, verdict and command; clicking again or Esc closes it. **Hovering** any card
thickens its wire and rings its merge on the rail, so connections are never a guess.

**Reading a card never needs manual zoom.** A click on any card or chip glides the
camera to it at reading size: centred when it fits, top-aligned at about 1.15× when
it's taller than the screen (the wheel pans the rest). Clicking it again, clicking empty
canvas or pressing Esc glides back to the view before. A manual pan or zoom after
focusing forgets that way back. A press that moves more than 5 px is a pan, never a
click. The canvas is `user-select:none` and `pointerdown` calls `preventDefault`, so
panning never highlights text; copying is what the command buttons are for.

Every card opens with a clock strip — `opened → last touched · how long open` and a
relative badge that runs violet within the hour and rust past five days — because the
reader is usually panned away from the rail and cannot read dates off it.

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
rules, pill chips, monospace throughout — extended by exactly three hues: amber for idle,
violet for live, and blue (`--cloud`) for work that ran in Claude Code cloud.

## Traps that cost real time

- **A board froze a finished conversation as "working".** On 10-05 a card said
  "Working right now" and listed "your last question" as an open task. The question
  had been answered two hours before the board was built, and the user closed the
  session minutes after. Two causes. `collect.py` read only the head of the
  transcript, so nothing said who spoke last. The live layer flipped the session
  tag on exit but left the card white with an open task. Both are fixed: the
  `turn` facts and the `answered` check above, the idle-answered tag, and
  auto-close for sessions with nothing to land. The turn reader skips injected
  text blocks and falls back to a full read when a pasted image pushes the
  last prompt out of the 600 KB tail.

- **Read-only git must never take `.git/index.lock`.** `git status` refreshes the
  index under that lock. On a stalled machine, the probe's timeout killed one
  mid-write, and the stale lock then made the user's own `git pull` fail with
  "index.lock: File exists". Every read-only git call (probe, collect) runs with
  `--no-optional-locks` and `GIT_OPTIONAL_LOCKS=0`. A stale lock is safe to remove
  only when `lsof` shows nothing holding it.

- **The server's token must outlive the server.** A token minted per start broke
  every open board on the first restart: run said "exit -1 forbidden", live checks
  died quietly, and new styles never arrived. The token lives in `token` beside the
  board (mode 600). A 403 tells the viewer to reload once and says nothing was run.
  After changing `render.py`, the server reloads it by itself; never restart the
  server just to ship a style change.

- **Wires from the lowest band must not pass behind chips.** Drawn straight up, a
  finished lane's wire vanishes behind a chip and reappears above it, so the chip
  looks wired to the card below (this confused a real reader). Retired-band wires run
  down, along under the chips, up a free column gutter, then curve to the merge.
- **`#chat{display:flex}` beats the `hidden` attribute** unless `#chat[hidden]` is
  restated. Without it an empty chat pane covers the canvas in any view where
  `sample` is unavailable.

- **Measure a card to focus by layout offsets** (`offsetLeft/Top` up to `.world`),
  never `getBoundingClientRect`: during a glide the screen rect is an in-between frame,
  and a second click mid-flight sends the camera somewhere else.
- **Resize must respect focus.** The resize handler refits the board, and headless
  Chrome fires a resize at startup. Refocus the focused card instead of calling
  `fitWidth()`, or the zoom silently resets while the outline stays.

- **Grid cards place in source order.** A card with `gcol` lower than the card before
  it drops to the next row. Sort each zone by `gcol` (cloud cards after local ones if
  they should form their own row).
- **The `<title>` comes from `title` in the JSON** (falls back to `<repo> Regroup`).

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
