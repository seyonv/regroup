#!/usr/bin/env python3
"""regroup/collect.py — inventory every open workstream in a repo.

Sources of truth, in order of reliability:
  1. git            — worktrees, branches, merge state, dirty files, unpushed commits
  2. live processes — `claude` sessions still running, their cwd and launch prompt
  3. transcripts    — ~/.claude/projects/<slug>/*.jsonl, for what each session was asked to do

Writes one JSON blob to stdout. render.py turns it into the canvas.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"


def sh(args, cwd=None):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60)
        return r.stdout.strip()
    except Exception:
        return ""


def slug_for(path):
    """Claude Code's transcript directory name for a working directory."""
    return str(path).replace("/", "-").replace("_", "-").replace(".", "-")


# ---------------------------------------------------------------- git


def git_facts(root):
    root = str(root)
    main = "main"
    for cand in ("main", "master"):
        if sh(["git", "-C", root, "rev-parse", "--verify", cand]):
            main = cand
            break

    worktrees = []
    cur = {}
    for line in sh(["git", "-C", root, "worktree", "list", "--porcelain"]).splitlines():
        if not line.strip():
            if cur:
                worktrees.append(cur)
            cur = {}
            continue
        k, _, v = line.partition(" ")
        if k == "worktree":
            cur["path"] = v
        elif k == "HEAD":
            cur["head"] = v[:7]
        elif k == "branch":
            cur["branch"] = v.replace("refs/heads/", "")
        elif k == "locked":
            cur["locked"] = True
        elif k == "detached":
            cur["branch"] = None
    if cur:
        worktrees.append(cur)

    for w in worktrees:
        p = w["path"]
        porcelain = sh(["git", "-C", p, "status", "--porcelain"])
        files = [l for l in porcelain.splitlines() if l.strip()]
        w["dirty_count"] = len(files)
        w["dirty_files"] = [
            {"status": l[:2].strip(), "path": l[3:]} for l in files[:200]
        ]
        w["last_commit"] = sh(
            ["git", "-C", p, "log", "-1", "--format=%cs|%h|%s"]
        )
        w["is_root"] = os.path.realpath(p) == os.path.realpath(root)

    merged = set(
        b.strip().lstrip("* ").strip()
        for b in sh(["git", "-C", root, "branch", "--format=%(refname:short)",
                     "--merged", main]).splitlines() if b.strip()
    )

    branches = []
    fmt = "%(refname:short)|%(committerdate:short)|%(committerdate:unix)|%(objectname:short)|%(contents:subject)"
    for line in sh(["git", "-C", root, "for-each-ref", "--sort=-committerdate",
                    "refs/heads", f"--format={fmt}"]).splitlines():
        parts = line.split("|", 4)
        if len(parts) < 5:
            continue
        name, date, unix, sha, subject = parts
        ahead = sh(["git", "-C", root, "rev-list", "--count", f"{main}..{name}"])
        behind = sh(["git", "-C", root, "rev-list", "--count", f"{name}..{main}"])
        branches.append({
            "name": name,
            "date": date,
            "unix": int(unix) if unix.isdigit() else 0,
            "sha": sha,
            "subject": subject,
            "ahead": int(ahead or 0),
            "behind": int(behind or 0),
            "merged": name in merged,
            "is_main": name == main,
        })

    upstream = sh(["git", "-C", root, "rev-parse", "--abbrev-ref",
                   f"{main}@{{upstream}}"])
    unpushed = []
    if upstream:
        for line in sh(["git", "-C", root, "log", "--format=%h|%cs|%s",
                        f"{upstream}..{main}"]).splitlines():
            p = line.split("|", 2)
            if len(p) == 3:
                unpushed.append({"sha": p[0], "date": p[1], "subject": p[2]})

    # Merge commits on main tell us which workstreams actually landed.
    landed = []
    for line in sh(["git", "-C", root, "log", "--merges", "-40",
                    "--format=%h|%cs|%s", main]).splitlines():
        p = line.split("|", 2)
        if len(p) == 3:
            landed.append({"sha": p[0], "date": p[1], "subject": p[2]})

    return {
        "root": root,
        "main": main,
        "upstream": upstream,
        "worktrees": worktrees,
        "branches": branches,
        "unpushed": unpushed,
        "landed": landed,
    }


# ------------------------------------------------------- live sessions


def etime_seconds(etime):
    """ps etime -> seconds. Forms: MM:SS, HH:MM:SS, DD-HH:MM:SS."""
    days = 0
    if "-" in etime:
        d, _, etime = etime.partition("-")
        days = int(d)
    parts = [int(x) for x in etime.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return days * 86400 + h * 3600 + m * 60 + s


def humanize(sec):
    d, r = divmod(int(sec), 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def link_sessions_to_transcripts(sessions, transcripts, tolerance=7200):
    """A live process and its transcript share a cwd and start within minutes.

    Claim nearest-first so two sessions never point at the same transcript.
    """
    pairs = []
    for s in sessions:
        for t in transcripts:
            if os.path.realpath(t.get("cwd") or "/") != os.path.realpath(s["cwd"] or "/"):
                continue
            if not t.get("first_ts"):
                continue
            delta = abs(t["first_ts"] - s["start_epoch"])
            if delta <= tolerance:
                pairs.append((delta, s["pid"], t["session_id"]))
    pairs.sort()
    taken_s, taken_t = set(), set()
    by_pid = {}
    for delta, pid, sid in pairs:
        if pid in taken_s or sid in taken_t:
            continue
        taken_s.add(pid)
        taken_t.add(sid)
        by_pid[pid] = (sid, delta)
    tx_by_id = {t["session_id"]: t for t in transcripts}
    for s in sessions:
        hit = by_pid.get(s["pid"])
        s["transcript_id"] = hit[0] if hit else None
        s["match_delta_s"] = round(hit[1]) if hit else None
        t = tx_by_id.get(hit[0]) if hit else None
        s["intent"] = (s["launch_prompt"] or (t or {}).get("first_prompt") or "")
        s["branch_at_start"] = (t or {}).get("branch", "")
        s["user_turns"] = (t or {}).get("user_turns", 0)
        s["last_active"] = (t or {}).get("mtime", 0)
    live_ids = {s["transcript_id"] for s in sessions if s["transcript_id"]}
    for t in transcripts:
        t["live"] = t["session_id"] in live_ids
    return sessions


def live_sessions(repo_paths):
    """Running `claude` processes whose cwd is inside one of repo_paths."""
    out = sh(["ps", "-eo", "pid,ppid,lstart,etime,command"])
    found = []
    for line in out.splitlines()[1:]:
        m = re.match(r"\s*(\d+)\s+(\d+)\s+(\S+\s+\S+\s+\d+\s+\S+\s+\d+)\s+(\S+)\s+(.*)$", line)
        if not m:
            continue
        pid, ppid, lstart, etime, cmd = m.groups()
        exe = cmd.split()[0] if cmd.split() else ""
        if os.path.basename(exe) != "claude":
            continue
        # Skip headless one-shot helpers (-p / --print): not human sessions.
        if re.search(r"(?:^|\s)-p(?:\s|$)|--output-format\s", cmd):
            continue
        cwd = ""
        n = sh(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"])
        for l in n.splitlines():
            if l.startswith("n"):
                cwd = l[1:]
        if not any(os.path.realpath(cwd).startswith(os.path.realpath(r))
                   for r in repo_paths if r):
            continue
        # Anything after the flags is the launch prompt.
        prompt = ""
        pm = re.search(r"claude\s+(.*)$", cmd)
        if pm:
            rest = pm.group(1)
            rest = re.sub(r"^(?:--\S+(?:\s+\S+)?\s*)*", "", rest)
            if rest and not rest.startswith("-") and rest.strip() != "code":
                prompt = rest.replace("\\012", "\n").strip()
        found.append({
            "pid": int(pid),
            "ppid": int(ppid),
            "started": lstart.strip(),
            "start_epoch": time.time() - etime_seconds(etime),
            "uptime": etime,
            "uptime_human": humanize(etime_seconds(etime)),
            "cwd": cwd,
            "worktree_flag": ("--worktree" in cmd),
            "model": (re.search(r"--model\s+(\S+)", cmd).group(1)
                      if re.search(r"--model\s+(\S+)", cmd) else ""),
            "launch_prompt": prompt,
            "cmd": cmd[:4000],
        })
    return found


# --------------------------------------------------------- transcripts


def read_transcript(path, max_bytes=3_000_000):
    """Pull intent + shape out of a session jsonl without loading the whole file."""
    size = path.stat().st_size
    info = {
        "session_id": path.stem,
        "file": str(path),
        "size": size,
        "mtime": path.stat().st_mtime,
        "cwd": "",
        "branch": "",
        "first_prompt": "",
        "first_ts": 0,
        "user_turns": 0,
        "prompts": [],
    }
    # Head: first user message carries the intent.
    with path.open("r", errors="replace") as f:
        head = f.read(max_bytes)
    for line in head.splitlines():
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        info["cwd"] = info["cwd"] or e.get("cwd", "")
        info["branch"] = info["branch"] or e.get("gitBranch", "") or ""
        if not info["first_ts"] and e.get("timestamp"):
            try:
                info["first_ts"] = datetime.fromisoformat(
                    e["timestamp"].replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        if e.get("type") == "user" and not e.get("isMeta"):
            msg = e.get("message", {})
            c = msg.get("content")
            text = ""
            if isinstance(c, str):
                text = c
            elif isinstance(c, list):
                text = " ".join(b.get("text", "") for b in c
                                if isinstance(b, dict) and b.get("type") == "text")
            text = text.strip()
            if not text or text.startswith("<"):
                continue
            if "system-reminder" in text[:200]:
                continue
            info["user_turns"] += 1
            if len(info["prompts"]) < 6:
                info["prompts"].append(text[:2000])
            if not info["first_prompt"]:
                info["first_prompt"] = text[:4000]
    return info


def transcripts_for(paths, since_days=30):
    cutoff = time.time() - since_days * 86400
    out = []
    for p in paths:
        d = PROJECTS / slug_for(p)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.jsonl"), key=lambda x: -x.stat().st_mtime):
            if f.stat().st_mtime < cutoff:
                continue
            try:
                out.append(read_transcript(f))
            except Exception as e:
                out.append({"session_id": f.stem, "file": str(f), "error": str(e),
                            "mtime": f.stat().st_mtime, "size": f.stat().st_size})
    return out


# ------------------------------------------------------------ task docs


CHECK = re.compile(r"^\s*[-*]\s*\[([ xX~/-])\]\s+(.*)$")


def task_docs(root, globs=("tasks/*.md", "docs/superpowers/plans/*.md")):
    docs = []
    for g in globs:
        for p in sorted(Path(root).glob(g)):
            try:
                text = p.read_text(errors="replace")
            except Exception:
                continue
            items = []
            for line in text.splitlines():
                m = CHECK.match(line)
                if m:
                    items.append({"done": m.group(1).lower() == "x",
                                  "text": m.group(2).strip()[:300]})
            if not items:
                continue
            docs.append({
                "path": str(p.relative_to(root)),
                "mtime": p.stat().st_mtime,
                "total": len(items),
                "done": sum(1 for i in items if i["done"]),
                "items": items[:80],
            })
    return docs


# ------------------------------------------------------------------ main


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    root = sh(["git", "-C", root, "rev-parse", "--show-toplevel"]) or root

    g = git_facts(root)
    wt_paths = [w["path"] for w in g["worktrees"]]
    sessions = live_sessions(wt_paths + [root])
    tx = transcripts_for(wt_paths)
    link_sessions_to_transcripts(sessions, tx)

    # Attach transcripts to the worktree they ran in.
    for w in g["worktrees"]:
        rp = os.path.realpath(w["path"])
        w["sessions_live"] = [s for s in sessions
                              if os.path.realpath(s["cwd"] or "/") == rp]
        w["transcripts"] = sorted(
            [t for t in tx if os.path.realpath(t.get("cwd") or "/") == rp],
            key=lambda t: -t["mtime"])
        w["tasks"] = task_docs(w["path"]) if os.path.isdir(w["path"]) else []

    orphan = [s for s in sessions
              if not any(os.path.realpath(s["cwd"] or "/") == os.path.realpath(w["path"])
                         for w in g["worktrees"])]

    print(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "git": g,
        "sessions": sessions,
        "orphan_sessions": orphan,
        "transcripts": tx,
    }, indent=1))


if __name__ == "__main__":
    main()
