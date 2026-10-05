#!/usr/bin/env python3
"""regroup probe: a read-only MCP server (stdio, stdlib only) that a published
regroup board calls to see what has changed since it was built.

One tool, `probe`. It never writes, never fetches over the network, and answers
in well under a second, so the board can check the moment the viewer switches
back from the terminal. Register it in the Claude desktop app as "regroup":

    "regroup": {"command": "python3", "args": ["<this file>"]}
"""
import json
import os
import shutil
import threading
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

POOL = ThreadPoolExecutor(max_workers=8)
CWD = {}

# Work that happens on GitHub (a PR merged in the browser, a branch deleted) is
# invisible until the local refs are fetched. A background thread fetches and asks
# gh for PR states at most once a minute, off the request path: a probe never
# waits on the network, it reports what the last refresh saw.
REMOTE = {}          # repo -> {"at": ms, "prs": {head_branch: {...}}, "busy": bool}
REMOTE_EVERY_S = 60


def _refresh_remote(repo):
    st = REMOTE[repo]
    try:
        subprocess.run(["git", "--no-optional-locks", "-C", repo, "fetch", "--prune", "--quiet"],
                       capture_output=True, timeout=45, env=GIT_ENV)
        if shutil.which("gh"):
            r = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "50", "--json",
                                "number,state,headRefName,title"],
                               cwd=repo, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                st["prs"] = {x["headRefName"]: {"number": x["number"], "state": x["state"],
                                                "title": x["title"]} for x in json.loads(r.stdout or "[]")}
        st["at"] = int(time.time() * 1000)
    except Exception:
        pass
    finally:
        st["busy"] = False


def remote_state(repo):
    st = REMOTE.setdefault(repo, {"at": 0, "prs": {}, "busy": False})
    if not st["busy"] and time.time() * 1000 - st["at"] > REMOTE_EVERY_S * 1000:
        st["busy"] = True
        threading.Thread(target=_refresh_remote, args=(repo,), daemon=True).start()
    return st

TOOL = {
    "name": "probe",
    "description": (
        "Read-only snapshot of one git repo for a regroup board: current branch, "
        "local and remote branches, main vs upstream, worktrees with dirty counts, "
        "which given commit subjects are on main, which given pids are alive, and "
        "the Claude Code sessions running in the repo, and whether each given session's "
        "last prompt has been answered."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "repo_path": {"type": "string"},
            "pids": {"type": "array", "items": {"type": "integer"}},
            "subjects": {"type": "array", "items": {"type": "string"}},
            "paths": {"type": "array", "items": {"type": "string"}},
            "sessions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["repo_path"],
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}

# Claude Code's own helper processes, not sessions anyone opened.
NOT_SESSIONS = ("bg-pty-host", "bg-spare", " agents", " -p ", " --print", " mcp ")


# Read-only callers must never take .git/index.lock: `git status` otherwise
# refreshes the index under that lock, and a call killed by the timeout on a
# stalled machine leaves the lock behind, blocking the user's own commits and pulls.
GIT_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")


def git(repo, *args):
    """One git call; on failure or a stalled machine it answers "" rather than
    failing the whole probe."""
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-C", repo, *args], capture_output=True,
                           text=True, timeout=10, env=GIT_ENV)
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


PROJECTS = os.path.expanduser("~/.claude/projects")
TRANSCRIPT = {}      # session id -> path, found once


def _prompt_text(e):
    """The text of a prompt the user typed, or "" for tool results, skill
    bodies, reminders and other harness-injected user entries."""
    if e.get("type") != "user" or e.get("isMeta"):
        return ""
    c = (e.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return ""
        c = " ".join(b.get("text", "").strip() for b in c if isinstance(b, dict) and b.get("type") == "text"
                     and not b.get("text", "").lstrip().startswith("<"))
    t = (c or "").strip()
    if not t or t.startswith("<") or t.startswith("Base directory for this skill") or "system-reminder" in t[:200]:
        return ""
    return t


def turn_state(path, tail_bytes=600_000):
    """Who has the ball in a session: the last prompt the user typed and whether
    an answer ended after it. A board that reads only the head of a transcript
    calls a question open that was answered hours ago."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - tail_bytes))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    user, user_at, ended_at, last_at, prompts = "", "", "", "", []
    for line in lines:
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        ts = e.get("timestamp") or ""
        if e.get("type") in ("user", "assistant") and ts:
            last_at = max(last_at, ts)
        t = _prompt_text(e)
        if t:
            user, user_at = t, ts
            prompts = (prompts + [t[:300]])[-4:]
        elif e.get("type") == "assistant" and (e.get("message") or {}).get("stop_reason") == "end_turn":
            ended_at = max(ended_at, ts)
    state = {"answered": bool(user_at) and ended_at >= user_at, "last_prompt": user[:300],
            "last_prompt_at": user_at, "answered_at": ended_at if ended_at >= user_at else "",
            "last_at": last_at, "recent_prompts": prompts}
    if not user_at and size > tail_bytes and tail_bytes < 40_000_000:
        # Pasted images and long tool output can push the last prompt out of the tail.
        return turn_state(path, 40_000_000)
    return state


def find_transcript(sid):
    if sid not in TRANSCRIPT:
        hit = ""
        if os.path.isdir(PROJECTS):
            for d in os.listdir(PROJECTS):
                p = os.path.join(PROJECTS, d, sid + ".jsonl")
                if os.path.isfile(p):
                    hit = p
                    break
        TRANSCRIPT[sid] = hit
    return TRANSCRIPT[sid]


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def claude_sessions(repo):
    """Interactive `claude` processes whose working directory is in this repo."""
    out = subprocess.run(["ps", "-axo", "pid=,args="], capture_output=True, text=True).stdout
    pids, args = [], {}
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        cmd = " " + cmd.strip() + " "
        if not (cmd.startswith(" claude ") or "/claude " in cmd.split()[0] + " "):
            continue
        if any(x in cmd for x in NOT_SESSIONS):
            continue
        pids.append(pid)
        args[int(pid)] = cmd.strip()[:200]
    if not pids:
        return []
    real = os.path.realpath(repo)
    # A process's cwd is looked up once (lsof is the slow part) and kept: this
    # server runs for as long as the app does.
    new = [p for p in pids if int(p) not in CWD]
    if new:
        r = subprocess.run(["lsof", "-a", "-d", "cwd", "-Fpn", "-p", ",".join(new)],
                           capture_output=True, text=True, timeout=10).stdout
        cur = None
        for line in r.splitlines():
            if line.startswith("p"):
                cur = int(line[1:])
            elif line.startswith("n") and cur is not None:
                CWD[cur] = os.path.realpath(line[1:])
    live = {int(p) for p in pids}
    for gone in [p for p in CWD if p not in live]:
        del CWD[gone]
    return [{"pid": p, "cwd": CWD[p], "args": args.get(p, "")} for p in sorted(live)
            if p in CWD and (CWD[p] == real or CWD[p].startswith(real + os.sep))]


def probe(args):
    """Every git and ps call is independent, so they all run at once: the probe
    costs about as much as its slowest call, not the sum of them."""
    t0 = time.time()
    repo = os.path.expanduser(str(args.get("repo_path") or ""))
    if not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isfile(os.path.join(repo, ".git")):
        raise ValueError("not a git repo: " + repo)
    subjects = [str(x) for x in (args.get("subjects") or []) if x]
    pids = [int(x) for x in (args.get("pids") or []) if str(x).isdigit()]
    paths = [str(x) for x in (args.get("paths") or []) if x]
    sids = [str(x) for x in (args.get("sessions") or []) if str(x).replace("-", "").isalnum()]
    gh = remote_state(repo)

    f_head = POOL.submit(git, repo, "rev-parse", "--abbrev-ref", "HEAD")
    f_refs = POOL.submit(git, repo, "for-each-ref", "--format=%(refname)|%(objectname:short)",
                         "refs/heads", "refs/remotes")
    f_up = POOL.submit(git, repo, "rev-parse", "--abbrev-ref", "main@{upstream}")
    f_ab = POOL.submit(git, repo, "rev-list", "--left-right", "--count", "main...main@{upstream}")
    f_wt = POOL.submit(git, repo, "worktree", "list", "--porcelain")
    # Subjects count as landed on local main or on its upstream, so a PR merged
    # on GitHub shows before anyone pulls.
    f_log = POOL.submit(git, repo, "log", "main", "main@{upstream}", "--format=%s", "-800") if subjects else None
    f_paths = [POOL.submit(git, repo, "ls-tree", "--name-only", "main@{upstream}", "--", x) for x in paths]
    f_paths_local = [POOL.submit(git, repo, "ls-tree", "--name-only", "main", "--", x) for x in paths]
    f_ses = POOL.submit(claude_sessions, repo)
    f_turns = {x: POOL.submit(lambda x=x: turn_state(find_transcript(x)) if find_transcript(x) else None)
               for x in sids}

    worktrees, cur = [], {}
    for line in f_wt.result().splitlines() + [""]:
        if not line:
            if cur:
                worktrees.append(cur)
            cur = {}
            continue
        k, _, v = line.partition(" ")
        if k == "worktree":
            cur = {"path": v}
        elif k == "branch":
            cur["branch"] = v.replace("refs/heads/", "")
        elif k == "HEAD":
            cur["head"] = v[:7]
    dirty = [POOL.submit(git, w["path"], "status", "--porcelain") if os.path.isdir(w["path"]) else None
             for w in worktrees]

    local, remote = {}, {}
    for line in f_refs.result().splitlines():
        ref, _, sha = line.partition("|")
        if ref.startswith("refs/heads/"):
            local[ref[11:]] = sha
        elif ref.startswith("refs/remotes/") and not ref.endswith("/HEAD"):
            remote[ref[13:]] = sha
    main = "main" if "main" in local else "master"
    ahead = behind = None
    lr = f_ab.result().split()
    if len(lr) == 2:
        ahead, behind = int(lr[0]), int(lr[1])
    log = f_log.result().splitlines() if f_log else []
    for w, f in zip(worktrees, dirty):
        w["dirty"] = len([l for l in f.result().splitlines() if l.strip()]) if f else 0

    return {
        "ok": True,
        "at": int(time.time() * 1000),
        "head_branch": f_head.result(),
        "main": main,
        "main_sha": local.get(main, ""),
        "upstream": f_up.result(),
        "ahead": ahead,
        "behind": behind,
        "branches": local,
        "remote_branches": remote,
        "worktrees": worktrees,
        "on_main": [x for x in subjects if any(l.startswith(x) for l in log)],
        "paths_on_main": [x for x, a, b in zip(paths, f_paths, f_paths_local) if a.result() or b.result()],
        "prs": gh["prs"],
        "fetched_at": gh["at"],
        "alive": [p for p in pids if alive(p)],
        "sessions": f_ses.result(),
        "turns": {x: f.result() for x, f in f_turns.items()},
        "ms": int((time.time() - t0) * 1000),
    }


def reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        try:
            m = json.loads(raw)
        except ValueError:
            continue
        method, id_ = m.get("method"), m.get("id")
        if id_ is None:
            continue  # notifications need no answer
        if method == "initialize":
            reply(id_, {"protocolVersion": m.get("params", {}).get("protocolVersion", "2024-11-05"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "regroup", "version": "1.0"}})
        elif method == "tools/list":
            reply(id_, {"tools": [TOOL]})
        elif method == "tools/call":
            p = m.get("params", {})
            if p.get("name") != "probe":
                reply(id_, error={"code": -32602, "message": "unknown tool"})
                continue
            try:
                r = probe(p.get("arguments") or {})
                reply(id_, {"content": [{"type": "text", "text": json.dumps(r)}],
                            "structuredContent": r})
            except Exception as e:
                reply(id_, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        elif method == "ping":
            reply(id_, {})
        else:
            reply(id_, error={"code": -32601, "message": "method not found"})


if __name__ == "__main__":
    main()
