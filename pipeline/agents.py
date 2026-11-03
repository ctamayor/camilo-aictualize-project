"""Run the agents defined in ``.claude/agents/`` headlessly through Claude Code.

Each worker is one ``claude -p`` process. The agent file is its system prompt
and sets its model and effort, the task text is its only input, it has no
tools, and Claude Code checks its
reply against a JSON schema before this code sees it. No model chooses a file
path or decides what runs next.
"""

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import ROOT

CLAUDE = os.environ.get("PIPELINE_CLAUDE") or shutil.which("claude") or "claude"
AGENTS_DIR = ROOT / ".claude" / "agents"
# Workers have replied in half a minute to four minutes; one that hangs is retried
# once (run.py).
WORKER_TIMEOUT_S = 9 * 60
# A worker reads only its task: not the memory Claude Code keeps for this folder.
ENV = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}


@dataclass
class Task:
    name: str
    agent: str
    prompt: str
    output: Path
    schema: dict


def definition(name: str) -> dict:
    """An agent file's fields and its prompt."""
    _, front, body = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8").split("---", 2)
    fields = dict(line.split(":", 1) for line in front.strip().splitlines())
    return {k.strip(): v.strip() for k, v in fields.items()} | {"prompt": body.strip()}


def command(agent: str, schema: dict) -> list[str]:
    # The agent runs as the session itself, which takes its effort from the command line.
    return [CLAUDE, "-p", "--agent", agent, "--tools", "", "--output-format", "json",
            "--json-schema", json.dumps(schema, separators=(",", ":")), "--effort", definition(agent)["effort"]]


def _parse_reply(stdout: str) -> dict:
    """Return the agent's structured reply from Claude Code's JSON envelope."""
    envelope = json.loads(stdout)
    if envelope.get("is_error"):
        raise ValueError(f"claude reported an error: {str(envelope.get('result'))[:300]}")
    data = envelope.get("structured_output")
    if data is None:
        data = json.loads(envelope.get("result") or "")
    if not isinstance(data, dict):
        raise ValueError("reply is not a JSON object")
    # Turns are logged because some workers report two to three times their input in
    # tokens, which suggests Claude Code made extra model calls for one reply.
    # The models are logged so a run shows which model each agent file actually ran on.
    return data | {"_usage": envelope.get("usage", {}) | {"turns": envelope.get("num_turns"),
                                                          "models": sorted(envelope.get("modelUsage", {}))}}


def call(argv: list[str], prompt: str, timeout: float | None = None, cwd: Path = ROOT,
         env: dict | None = None) -> subprocess.CompletedProcess:
    """Run ``argv`` with ``prompt`` on stdin in ``cwd``, killing it and every process it
    started after ``timeout`` seconds (WORKER_TIMEOUT_S by default).

    ``subprocess.run``'s timeout kills only the process it started, then waits for
    its output pipes to close, and processes that one started keep them open: hung
    workers outlived the timeout by minutes. Killing the whole tree closes them."""
    timeout = timeout or WORKER_TIMEOUT_S
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", cwd=cwd,
                            env=None if env is None else os.environ | env, start_new_session=os.name != "nt")
    killed = threading.Event()

    def kill() -> None:
        killed.set()
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)

    timer = threading.Timer(timeout, kill)
    timer.start()
    try:
        stdout, stderr = proc.communicate(prompt)
    finally:
        timer.cancel()
    if killed.is_set():
        # What it wrote before it was killed is kept: a long worker's progress is worth reading.
        raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def run_one(task: Task) -> dict:
    """Run one worker; write its reply to ``task.output`` on success."""
    start = time.monotonic()

    def done(error: str | None = None, usage: dict | None = None) -> dict:
        return {"name": task.name, "ok": error is None, "seconds": round(time.monotonic() - start),
                "error": error, "usage": usage or {}}

    try:
        proc = call(command(task.agent, task.schema), task.prompt, env=ENV)
    except subprocess.TimeoutExpired:
        return done(f"no reply after {WORKER_TIMEOUT_S // 60} minutes")
    except OSError as e:
        return done(f"could not start claude: {e}")
    if proc.returncode != 0:
        return done(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-400:]}")
    try:
        data = _parse_reply(proc.stdout)
    except (json.JSONDecodeError, ValueError) as e:
        return done(f"unusable reply: {e}")

    usage = data.pop("_usage")
    task.output.parent.mkdir(parents=True, exist_ok=True)
    task.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return done(usage=usage)


def run_wave(tasks: list[Task], parallel: int) -> list[dict]:
    """Run ``tasks`` concurrently, at most ``parallel`` at a time."""
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        return list(pool.map(run_one, tasks))


def describe(result: dict) -> str:
    u = result["usage"]
    read = sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    tokens = f", {read:,} in / {u.get('output_tokens', 0):,} out, {u.get('turns')} turns" if u else ""
    if u.get("models"):
        tokens += ", " + " + ".join(u["models"])
    status = "ok" if result["ok"] else f"FAILED: {result['error']}"
    return f"{result['name']} {status} ({result['seconds']}s{tokens})"
