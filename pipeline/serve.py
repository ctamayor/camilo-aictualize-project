"""Serve the dashboard on localhost, with every claim's evidence a click away.

The page (dashboard.html) is static. It asks this server for /api/progress,
what the run is doing now, every few seconds; for /api/report, everything the
run produced as read from out/, whenever that changes; and for /api/message,
one message as parsed from its raw corpus file with where each cited quote sits
in it. The server computes no figure: hours and dollars come from score. It
serves only messages the run read, looked up by id, never a path taken from a
request.

A run starts the server before it starts work, in the background so the
dashboard outlives the run command (``ensure_running``). The server holds no
file in out/ open, so starting over can remove the folder's contents under it.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import ROOT
from .ingest import parse_message, read_raw
from .state import draft_paths, progress, read_json, read_messages, run_active
from .validate import QUOTE_CHARS, REPLY_MARKERS, normalize

HOST = "127.0.0.1"
PORT = 8765
PAGE = Path(__file__).with_name("dashboard.html")


def locate(quote: str, text: str) -> list[int] | None:
    """Return [start, end] of ``quote`` in ``text``, matched the way validate matches it.

    Validate compares after removing reply markers, straightening quote characters,
    collapsing whitespace and ignoring case, so the match is found in that
    normalized text and its two ends are mapped back to offsets in ``text``.
    """
    removed = set()
    for m in REPLY_MARKERS.finditer(text):
        removed.update(range(m.start(), m.end()))
    chars, where = [], []
    for i, ch in enumerate(text):
        if i in removed:
            continue
        if ch.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
                where.append(i)
            continue
        chars.append(ch.translate(QUOTE_CHARS))
        where.append(i)
    if chars and chars[-1] == " ":
        chars.pop()
        where.pop()
    q = normalize(quote).lower()
    k = "".join(chars).lower().find(q) if q else -1
    return [where[k], where[k + len(q) - 1] + 1] if k >= 0 else None


_cache = {}


def _cached(path: Path, load):
    """``load(path)``, reloaded only when the file changes, so a running dashboard follows the run."""
    try:
        stamp = path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    if _cache.get(path, (None,))[0] != stamp:
        _cache[path] = (stamp, load(path))
    return _cache[path][1]


def _messages(out_dir: Path) -> dict:
    return _cached(out_dir / "messages.jsonl", lambda p: read_messages(p.parent)) or {}


def report(out_dir: Path) -> dict:
    """Everything the dashboard shows, as the run's steps wrote it."""
    scored = read_json(out_dir / "opportunities.json") or {}
    processes = (read_json(out_dir / "processes.json") or {}).get("processes", [])
    messages = _messages(out_dir)
    opportunities = scored.get("opportunities", [])
    # Headers of every message the page can cite, so its quotes say who wrote them and when.
    cited = {c["message"] for p in processes for kind in ("occurrences", "observations", "stalls")
             for c in p["evidence"].get(kind, [])}
    # The name each pattern was recorded under, which says what its messages were cited as showing.
    names = {p["id"]: p["name"] for p in (read_json(out_dir / "validated.json") or {}).get("patterns", [])}
    return {
        "scored": bool(scored),
        "totals": scored.get("totals"),
        "mailboxes": scored.get("mailboxes", {}),
        "opportunities": opportunities,
        "processes": processes,
        "patterns": {pid: names[pid] for p in processes for pid in p["patterns"] if pid in names},
        "drafts": sorted(o["id"] for o in opportunities if draft_paths(out_dir, o)[1].exists()),
        "messages": {i: {k: messages[i][k] for k in ("date", "from", "subject")} for i in sorted(cited) if i in messages},
    }


def live(out_dir: Path) -> dict:
    """What the run is doing now, and a version that changes whenever the report would."""
    log = out_dir / "run.log"
    stamps = []
    for name in ("messages.jsonl", "ingest_report.json", "validated.json", "processes.json", "opportunities.json"):
        try:
            stamps.append(str((out_dir / name).stat().st_mtime_ns))
        except FileNotFoundError:
            stamps.append("-")
    stamps.append(str(len(list((out_dir / "drafts").glob("*.md")))))
    return {
        "active": run_active(out_dir),
        "run": read_json(out_dir / "run.json"),
        "steps": progress(out_dir),
        "log": log.read_text(encoding="utf-8").splitlines()[-40:] if log.exists() else [],
        "version": " ".join(stamps),
    }


def message(corpus_dir: Path, out_dir: Path, message_id: str, quotes: list[str]) -> dict | None:
    """One message as validate read it, with where each quote sits in it and in the raw file."""
    messages = _messages(out_dir)
    copies = {d: m["id"] for m in messages.values() for d in m.get("duplicates", [])}
    if message_id not in messages and message_id not in copies:
        return None
    raw = read_raw(corpus_dir, message_id)
    m = parse_message(message_id, raw)
    # The same text validate checked every quote against.
    text = f"From: {m['from']}\nTo: {m['to']}\nCc: {m['cc']}\nSubject: {m['subject']}\n\n{m['body']}"
    kept = messages.get(message_id) or messages[copies[message_id]]
    file = next(p for p in (corpus_dir / message_id, corpus_dir / (message_id.rstrip(".") + ".eml")) if p.exists())
    return {
        "id": message_id,
        "file": file.relative_to(corpus_dir.parent).as_posix(),
        "date": m["date"], "date_raw": m["date_raw"], "date_issue": m["date_issue"],
        "text": text,
        "spans": [locate(q, text) for q in quotes],
        "raw": raw,
        "raw_spans": [locate(q, raw) for q in quotes],
        "copy_of": copies.get(message_id),
        "duplicates": kept.get("duplicates", []),
    }


def make_handler(out_dir: Path, corpus_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, data) -> None:
            self.send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/":
                return self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/ping":
                return self.send_json({"out": str(out_dir.resolve())})
            if url.path == "/api/progress":
                return self.send_json(live(out_dir))
            if url.path == "/api/report":
                return self.send_json(report(out_dir))
            if url.path == "/api/message":
                found = message(corpus_dir, out_dir, query.get("id", [""])[0], query.get("q", []))
                return self.send_json(found) if found else self.send(404, b"no such message", "text/plain")
            if url.path == "/api/draft":
                opp = {"id": query.get("id", [""])[0]}
                path = draft_paths(out_dir, opp)[1] if opp["id"].startswith("opp-") and opp["id"][4:].isdigit() else None
                if path and path.exists():
                    return self.send(200, path.read_bytes(), "text/markdown; charset=utf-8")
            self.send(404, b"not found", "text/plain")

        def log_message(self, *args) -> None:
            pass

    return Handler


def serve(out_dir: Path, corpus_dir: Path, port: int = PORT) -> None:
    server = ThreadingHTTPServer((HOST, port), make_handler(out_dir, corpus_dir))
    print(f"dashboard: http://{HOST}:{port}/ (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def serving(port: int) -> str | None:
    """The out/ folder the dashboard on ``port`` shows, or None if no dashboard answers there."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/ping", timeout=1) as reply:
            return json.loads(reply.read())["out"]
    except (OSError, ValueError, KeyError):
        return None


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def server_log(port: int) -> Path:
    # Outside out/, so the server never holds a file there open.
    return Path(tempfile.gettempdir()) / f"pipeline-dashboard-{port}.log"


def _start(out_dir: Path, corpus_dir: Path, port: int) -> None:
    argv = [sys.executable, "-m", "pipeline", "serve", "--out", str(out_dir.resolve()),
            "--corpus", str(corpus_dir.resolve()), "--port", str(port)]
    with open(server_log(port), "a", encoding="utf-8") as errors:
        common = dict(cwd=ROOT, stdin=subprocess.DEVNULL, stdout=errors, stderr=errors, close_fds=True)
        if os.name != "nt":
            subprocess.Popen(argv, start_new_session=True, **common)
            return
        # Detached, and out of the launching shell's job if it allows that, so the
        # server is not stopped when the run command or its shell call ends.
        detached = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(argv, creationflags=detached | subprocess.CREATE_BREAKAWAY_FROM_JOB, **common)
        except OSError:
            subprocess.Popen(argv, creationflags=detached, **common)


def ensure_running(out_dir: Path, corpus_dir: Path, port: int = PORT) -> str:
    """Return the URL of a dashboard showing ``out_dir``, starting one in the background if needed.

    A dashboard already showing this folder is reused. A port held by anything
    else is skipped, so another run's dashboard keeps running."""
    want = str(out_dir.resolve())
    for candidate in range(port, port + 10):
        shown = serving(candidate)
        if shown == want:
            return f"http://{HOST}:{candidate}/"
        if shown is None and _port_free(candidate):
            _start(out_dir, corpus_dir, candidate)
            for _ in range(50):
                if serving(candidate) == want:
                    return f"http://{HOST}:{candidate}/"
                time.sleep(0.2)
            raise RuntimeError(f"the dashboard did not start on port {candidate}; see {server_log(candidate)}")
    raise RuntimeError(f"ports {port}-{port + 9} are all taken")
