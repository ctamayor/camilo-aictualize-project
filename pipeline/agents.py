"""Run the agents defined in ``.claude/agents/`` headlessly through Claude Code.

Each worker is one ``claude -p`` process. The agent file is its system prompt,
the task text is its only input, it has no tools, and Claude Code checks its
reply against a JSON schema before this code sees it. No model chooses a file
path or decides what runs next.
"""

import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import ROOT

CLAUDE = os.environ.get("PIPELINE_CLAUDE") or shutil.which("claude") or "claude"
# The run session's shell call is cut off at 10 minutes and the first wave always
# runs, right after prepare's few seconds, so a worker gets as long as fits in that.
# Scouts on 200K-token chunks are expected to need 3 to 6 minutes.
WORKER_TIMEOUT_S = 9 * 60


@dataclass
class Task:
    name: str
    agent: str
    prompt: str
    output: Path
    schema: dict


def command(agent: str, schema: dict) -> list[str]:
    return [CLAUDE, "-p", "--agent", agent, "--tools", "", "--output-format", "json",
            "--json-schema", json.dumps(schema, separators=(",", ":"))]


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


def run_one(task: Task) -> dict:
    """Run one worker; write its reply to ``task.output`` on success."""
    start = time.monotonic()

    def done(error: str | None = None, usage: dict | None = None) -> dict:
        return {"name": task.name, "ok": error is None, "seconds": round(time.monotonic() - start),
                "error": error, "usage": usage or {}}

    try:
        proc = subprocess.run(command(task.agent, task.schema), input=task.prompt, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", cwd=ROOT,
                              timeout=WORKER_TIMEOUT_S)
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
