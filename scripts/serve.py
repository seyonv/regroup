#!/usr/bin/env python3
"""regroup/serve.py: the board as a local page, with a small server behind it.

    python3 serve.py <regroup.json> [--port N] [--no-open]

Serves the board on 127.0.0.1 and gives it four things a published artifact
cannot have:

  /api/probe   what is true in the repo right now (~60 ms; see probe_server.py)
  /api/run     run one of the board's own commands, after the page confirms
  /api/chat    `claude -p` in the repo, streamed: your Max plan, full read access
  /            the board itself, rendered fresh from the JSON on every load

Only commands that appear on the board can be run. Every /api call must carry
the per-start token the page was served with, and the Host header must be this
server, so no other web page can drive it. It exits after 30 minutes with no
request (an open board checks in every few seconds).

If a server for the same board is already running, a second start just opens
it in the browser and exits.
"""
import importlib
import json
import re
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import probe_server  # noqa: E402
import render  # noqa: E402

IDLE_EXIT_S = 30 * 60
TOKEN = None  # set in main(): one per board, kept across restarts
STATE = {"last": time.time()}

# Read-only tools for the chat. Writing is done through the board's buttons,
# where the viewer sees the exact command and confirms it.
CHAT_TOOLS = ["Read", "Grep", "Glob",
              "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git status:*)",
              "Bash(git branch:*)", "Bash(git worktree list:*)", "Bash(git rev-list:*)",
              "Bash(git merge-base:*)", "Bash(git range-diff:*)", "Bash(git cherry:*)",
              "Bash(ls:*)", "Bash(wc:*)"]


INTERACTIVE = re.compile(r"^claude\b|(^|[|;&]\s*)(less|more|vim?|nano|emacs|top|htop)(\s|$)|"
                         r"git (rebase|add|checkout|reset|stash) (-i|-p|--interactive|--patch)\b|"
                         r"git commit(?!.*(\s-m|\s-F|--no-edit|--amend -F))")


def interactive(cmd):
    """Commands that need a terminal (a pager, an editor, an interactive session)
    stay copy-only; the server will not run them."""
    return bool(INTERACTIVE.search(cmd))


# Commands Claude wrote in this server's chat answers. Like the board's own
# commands they run only after the viewer confirms the exact string on the page;
# nothing else is runnable.
CHAT_CMDS = set()
CMD_START = re.compile(r"^(git|gh|kill|pkill|rm|mv|cp|mkdir|ls|cat|npm|npx|node|python3?|swift|bash|sh|"
                       r"open|launchctl|defaults|brew|uvx?|make|claude|\./[\w./-]+)(\s|$)")


def chat_commands(text):
    """Shell commands in an answer: fenced shell blocks and inline code that starts
    with a known command. Placeholders (<id>) and interactive commands are skipped."""
    found = []
    for lang, body in re.findall(r"```(\w*)\n(.*?)```", text, re.S):
        body = body.strip()
        if lang in ("", "bash", "sh", "shell", "zsh", "console") and CMD_START.match(body):
            found.append(body)
    for code in re.findall(r"(?<!`)`([^`\n]+)`(?!`)", re.sub(r"```.*?```", "", text, flags=re.S)):
        code = code.strip()
        if CMD_START.match(code) and " " in code:
            found.append(code)
    return [c for c in dict.fromkeys(found)
            if not interactive(c) and "<" not in c and "sudo " not in c]


# Safe commands the page offers by itself (e.g. "main is 2 behind: pull").
BUILTIN_CMDS = {"git pull --ff-only", "git fetch --prune"}


def runnable(data):
    cmds = [a.get("cmd") for a in data.get("actions", [])]
    cmds += [(w.get("act") or {}).get("cmd") for w in data.get("workstreams", [])]
    return {c for c in cmds if c and not interactive(c)}


def slug(path):
    return str(path).replace("/", "-").replace("_", "-").replace(".", "-")


def projects_dir(repo):
    d = Path.home() / ".claude" / "projects" / slug(os.path.realpath(repo))
    return str(d) if d.is_dir() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "regroup"

    def log_message(self, *a):
        pass

    # ---- plumbing ----
    def data(self):
        return json.loads(Path(self.server.board).read_text())

    def send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        return secrets.compare_digest(self.headers.get("X-Regroup-Token") or "", TOKEN or "")

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    # ---- routes ----
    def do_GET(self):
        STATE["last"] = time.time()
        if self.path in ("/", "/index.html"):
            # Pick up edits to render.py without a server restart.
            mt = os.path.getmtime(render.__file__)
            if mt != STATE.get("render_mtime"):
                importlib.reload(render)
                STATE["render_mtime"] = mt
            head = "<script>window.REGROUP_LOCAL=" + json.dumps({"token": TOKEN}) + "</script>"
            return self.send(200, render.render(self.data(), head), "text/html")
        self.send(404, {"error": "not found"})

    def do_POST(self):
        STATE["last"] = time.time()
        if not self.allowed():
            return self.send(403, {"error": "forbidden"})
        try:
            if self.path == "/api/probe":
                return self.send(200, probe_server.probe(self.body()))
            if self.path == "/api/run":
                return self.run_cmd(self.body())
            if self.path == "/api/chat":
                return self.chat(self.body())
            if self.path == "/api/marks":
                return self.marks(self.body())
            if self.path == "/api/chats":
                return self.send(200, list_chats(self.server.board))
            if self.path == "/api/chat-load":
                return self.chat_load(self.body())
            self.send(404, {"error": "not found"})
        except BrokenPipeError:
            pass
        except Exception as e:  # report to the page instead of dropping the socket
            self.send(500, {"error": str(e)})

    def marks(self, req):
        """Manual "mark done" ticks, saved beside the board and keyed by the
        action's title so they survive reloads, restarts and reordering."""
        f = Path(self.server.board).with_name("marks.json")
        try:
            m = json.loads(f.read_text())
        except (OSError, ValueError):
            m = {}
        if req.get("title"):
            if req.get("done"):
                m[str(req["title"])] = int(time.time())
            else:
                m.pop(str(req["title"]), None)
            f.write_text(json.dumps(m, indent=1))
        self.send(200, m)

    def chat_load(self, req):
        f = chats_dir(self.server.board) / (re.sub(r"[^\w-]", "", str(req.get("id") or "")) + ".json")
        try:
            c = json.loads(f.read_text())
        except (OSError, ValueError):
            return self.send(404, {"error": "no such chat"})
        # Commands in a reopened chat are runnable again, still behind a confirm.
        for t in c.get("turns", []):
            if t.get("role") == "assistant":
                t["cmds"] = chat_commands(t.get("content", ""))
                CHAT_CMDS.update(t["cmds"])
        self.send(200, c)

    def run_cmd(self, req):
        data = self.data()
        cmd = str(req.get("cmd") or "")
        if cmd not in runnable(data) and cmd not in CHAT_CMDS and cmd not in BUILTIN_CMDS:
            return self.send(400, {"error": "not a command on this board"})
        t0 = time.time()
        try:
            r = subprocess.run(["bash", "-c", cmd], cwd=data["repo_path"], capture_output=True,
                               text=True, timeout=180)
            out, code = (r.stdout + r.stderr), r.returncode
        except subprocess.TimeoutExpired as e:
            out, code = ((e.stdout or "") + (e.stderr or "") + "\n[stopped after 180 s]"), 124
        self.send(200, {"code": code, "out": out[-8000:], "ms": int((time.time() - t0) * 1000)})

    def chat(self, req):
        """Stream `claude -p` as NDJSON lines: {"t":"text","d":…}, {"t":"tool","s":…},
        {"t":"done"} or {"t":"error","m":…}."""
        data = self.data()
        repo = data["repo_path"]
        all_turns = [t for t in (req.get("turns") or []) if t.get("content")]
        turns = all_turns[-16:]  # the prompt carries the recent past; the saved chat keeps everything
        if not turns or turns[-1].get("role") != "user":
            return self.send(400, {"error": "last turn must be the user's"})
        history = "".join(("Q: " if t["role"] == "user" else "A: ") + t["content"].strip() + "\n\n"
                          for t in turns[:-1])
        prompt = (("Earlier in this chat:\n\n" + history + "Now:\n") if history else "") + turns[-1]["content"]
        system = (
            "You are answering questions beside a regroup board: a map of the user's Claude Code sessions, "
            "branches and worktrees in this repo (" + repo + "). You run in the repo with read-only tools: "
            "files, git, and the session transcripts under ~/.claude/projects. Use them whenever the board "
            "lacks a fact, and say in one line what you looked at.\n"
            "Answer briefly: lead with the answer, then at most a few bullets. Put commands, shas and branch "
            "names in backticks, spelled exactly.\n"
            "You cannot change anything yourself. For a change, give the exact shell command in backticks, "
            "or several lines in a ```bash block, ready to run as written in the repo root (no placeholders): "
            "each one gets a run button the user confirms. Never suggest an interactive command (an editor, a pager, "
            "`git rebase -i`).\n"
            "When your answer centres on one workstream, end with [[focus:<id>]] using its id from the board, "
            "and the board will fly to it.\n\n"
            "LIVE STATE (just checked, newer than the board; trust it over the board):\n"
            + json.dumps(probe_server.probe({"repo_path": repo})) + "\n\nBOARD:\n" + json.dumps(data))
        args = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                "--no-session-persistence", "--strict-mcp-config", "--setting-sources", "project",
                "--model", "opus" if req.get("deep") else "sonnet",
                "--append-system-prompt", system, "--allowedTools", *CHAT_TOOLS]
        tdir = projects_dir(repo)
        if tdir:
            args += ["--add-dir", tdir]
        args += ["--", prompt]

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        full = []
        p = subprocess.Popen(args, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)

        def emit(obj):
            self.wfile.write((json.dumps(obj) + "\n").encode())
            self.wfile.flush()

        try:
            for line in p.stdout:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                kind = e.get("type")
                if kind == "stream_event":
                    ev = e.get("event") or {}
                    d = (ev.get("delta") or {})
                    if ev.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                        full.append(d.get("text", ""))
                        emit({"t": "text", "d": d.get("text", "")})
                elif kind == "assistant":
                    for c in (e.get("message") or {}).get("content") or []:
                        if c.get("type") == "tool_use":
                            i = c.get("input") or {}
                            s = i.get("command") or i.get("file_path") or i.get("pattern") or c.get("name")
                            emit({"t": "tool", "s": str(s)[:160]})
                elif kind == "result":
                    if e.get("is_error"):
                        emit({"t": "error", "m": str(e.get("result") or e.get("subtype"))[:400]})
                    cmds = chat_commands("".join(full))
                    CHAT_CMDS.update(cmds)
                    if not e.get("is_error") and full:
                        save_chat(self.server.board, req.get("chat_id"), all_turns, "".join(full))
                    if cmds:
                        emit({"t": "cmds", "list": cmds})
                    emit({"t": "done"})
            p.wait(timeout=5)
            if p.returncode not in (0, None):
                emit({"t": "error", "m": (p.stderr.read() or "claude exited " + str(p.returncode))[-400:]})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page pressed Stop
        finally:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)


def chats_dir(board):
    d = Path(board).with_name("chats")
    d.mkdir(exist_ok=True)
    return d


def save_chat(board, chat_id, turns, answer):
    """One file per conversation: every question and answer, newest first in the list."""
    cid = re.sub(r"[^\w-]", "", str(chat_id or "")) or time.strftime("%Y%m%d-%H%M%S")
    f = chats_dir(board) / (cid + ".json")
    try:
        old = json.loads(f.read_text())
    except (OSError, ValueError):
        old = {"id": cid, "started": int(time.time() * 1000)}
    old["turns"] = [{"role": t["role"], "content": t["content"]} for t in turns] + \
                   [{"role": "assistant", "content": re.sub(r"\s*\[\[focus:[\w-]+\]\]\s*", " ", answer).strip()}]
    old["title"] = next(t["content"] for t in old["turns"] if t["role"] == "user")[:90]
    old["updated"] = int(time.time() * 1000)
    f.write_text(json.dumps(old, indent=1))


def list_chats(board):
    out = []
    for f in chats_dir(board).glob("*.json"):
        try:
            c = json.loads(f.read_text())
            out.append({"id": c["id"], "title": c.get("title", ""), "updated": c.get("updated", 0),
                        "questions": sum(1 for t in c.get("turns", []) if t["role"] == "user")})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda c: -c["updated"])


def free_port(start):
    for port in range(start, start + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("no free port near " + str(start))


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    board = Path(argv[0]).expanduser().resolve()
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else None
    open_it = "--no-open" not in argv
    json.loads(board.read_text())  # fail early on a broken board

    lock = board.with_name("server.json")
    if lock.exists():
        try:
            old = json.loads(lock.read_text())
            os.kill(old["pid"], 0)
            url = old["url"]
            if open_it:
                webbrowser.open(url)
            print("already serving " + url)
            return
        except (OSError, ValueError, KeyError):
            pass

    # The token lives beside the board (mode 600), so a page that is already
    # open keeps working when the server restarts.
    global TOKEN
    tok = board.with_name("token")
    try:
        TOKEN = tok.read_text().strip()
    except OSError:
        TOKEN = ""
    if len(TOKEN) < 24:
        TOKEN = secrets.token_urlsafe(24)
        tok.write_text(TOKEN)
    os.chmod(tok, 0o600)

    port = port or free_port(4777)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    srv.board = str(board)
    url = "http://127.0.0.1:" + str(port) + "/"
    lock.write_text(json.dumps({"pid": os.getpid(), "url": url}))

    def idle_watch():
        while time.time() - STATE["last"] < IDLE_EXIT_S:
            time.sleep(30)
        srv.shutdown()
    threading.Thread(target=idle_watch, daemon=True).start()

    print("regroup board at " + url, flush=True)
    if open_it:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    finally:
        try:
            if json.loads(lock.read_text()).get("pid") == os.getpid():
                lock.unlink()
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    main()
