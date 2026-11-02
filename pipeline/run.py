"""Drive a run to completion: deterministic steps in-process, agents as workers.

``run`` loops over ``next_action`` until the run is DONE, a worker FAILS, or the
time budget for this invocation is spent (CONTINUE: call it again and it picks
up where it left off). The budget exists because the launching session's shell
call has a hard time limit; a wave of workers is never started that might cross it.

Only one run at a time works on an output folder (``run_lock``). While it runs
it keeps ``run.json`` up to date with the step and the workers in flight, which
the dashboard shows.
"""

import os
import time
from pathlib import Path

from . import agents, schemas
from .estimate import estimate_prompt
from .state import RunInProgress, log, next_action, now, read_json, run_lock, scout_output, write_json

MAX_PARALLEL = 8


def scout_task(out_dir: Path, chunk: dict) -> agents.Task:
    text = (out_dir / chunk["file"]).read_text(encoding="utf-8")
    prompt = (f"Batch {chunk['id']}: {len(chunk['message_ids'])} messages. "
              f"Record the patterns these messages show.\n\n{text}")
    return agents.Task(chunk["id"], "scout", prompt, scout_output(out_dir, chunk), schemas.SCOUT)


def merge_task(action: dict) -> agents.Task:
    patterns = read_json(action["input"])["patterns"]
    blocks = "\n".join(f"{p['id']} | {p['name']} | {p['summary']}\n" + "".join(f'- "{q}"\n' for q in p["occurrences"])
                       for p in patterns)
    prompt = (f"{len(patterns)} patterns, each as a line id | name | summary followed by the quote "
              f"showing each of its occurrences. Group them into processes.\n\n{blocks}")
    return agents.Task("merge", "merger", prompt, action["output"], schemas.MERGE)


def estimate_task(out_dir: Path, piece: dict, processes: list[dict], patterns: dict) -> agents.Task:
    prompt = estimate_prompt(processes, patterns, piece["processes"])
    return agents.Task(piece["id"], "estimator", prompt, piece["output"], schemas.ESTIMATE)


def tasks_for(out_dir: Path, action: dict) -> list[agents.Task]:
    """The worker tasks an agent action stands for; empty if not built yet."""
    if action["action"] == "SCOUTS":
        return [scout_task(out_dir, c) for c in action["chunks"]]
    if action["action"] == "MERGE":
        return [merge_task(action)]
    if action["action"] == "ESTIMATE":
        processes = read_json(out_dir / "processes.json")["processes"]
        patterns = {p["id"]: p for p in read_json(out_dir / "validated.json")["patterns"]}
        return [estimate_task(out_dir, piece, processes, patterns) for piece in action["slices"]]
    return []


def run_tasks(out_dir: Path, tasks: list[agents.Task], parallel: int) -> list[dict]:
    results = agents.run_wave(tasks, parallel)
    for task, r in zip(tasks, results):
        log(out_dir, f"{task.agent} " + agents.describe(r))
    return results


def run(corpus_dir: Path, out_dir: Path, steps: dict, parallel: int = MAX_PARALLEL,
        max_minutes: float = 9, echo=print) -> str:
    """Return the final status line: DONE, CONTINUE or FAILED <reason>."""
    try:
        with run_lock(out_dir):
            return _run(corpus_dir, out_dir, steps, parallel, max_minutes, echo)
    except RunInProgress:
        return "FAILED another run is in progress on this output folder"


def _run(corpus_dir: Path, out_dir: Path, steps: dict, parallel: int, max_minutes: float, echo) -> str:
    started = time.monotonic()
    longest_wave = 0.0
    record = {"pid": os.getpid(), "started": now(), "ended": None, "status": "running",
              "step": None, "working_on": [], "remaining": 0, "since": None}

    def note(**fields) -> None:
        record.update(fields)
        write_json(out_dir / "run.json", record)

    def status(line: str) -> str:
        log(out_dir, line)
        note(status=line, ended=now(), step=None, working_on=[], remaining=0, since=None)
        return line

    note()

    while True:
        action = next_action(corpus_dir, out_dir)
        kind = action["action"]

        if kind == "RUN":
            step = action["step"]
            if step not in steps:
                return status(f"FAILED step '{step}' is not built yet")
            note(step=step, working_on=[], remaining=0, since=now())
            echo(f"{step}: {steps[step](corpus_dir, out_dir)}")

        elif kind == "DONE":
            return status("DONE")

        else:
            tasks = tasks_for(out_dir, action)
            if not tasks:
                return status(f"FAILED step '{kind.lower()}' is not built yet")
            # Always make progress: the first wave runs; later waves only if a
            # wave as long as the longest so far would still fit the budget.
            elapsed = time.monotonic() - started
            if longest_wave and elapsed + longest_wave > max_minutes * 60:
                return status(f"CONTINUE {len(tasks)} {tasks[0].agent} tasks still to run")
            wave = tasks[:parallel]
            note(step=kind.lower(), working_on=[t.name for t in wave], remaining=len(tasks), since=now())
            echo(f"{kind.lower()}: running {len(wave)} of {len(tasks)}")
            wave_started = time.monotonic()
            results = run_tasks(out_dir, wave, parallel)
            longest_wave = max(longest_wave, time.monotonic() - wave_started, 1e-6)
            for r in results:
                echo("  " + agents.describe(r))
            failed = [r["name"] for r in results if not r["ok"]]
            if failed:
                return status(f"FAILED no usable reply for {', '.join(failed)}")
