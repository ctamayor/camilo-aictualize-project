"""Drive a run to completion: deterministic steps in-process, agents as workers.

``run`` loops over ``next_action`` until the run is DONE or a worker FAILS twice:
the readers, one per batch of the mail; the analysts and critics, for a set time;
then the drafters, one per top opportunity. A run stopped partway continues
where it left off when started again.

Only one run at a time works on an output folder (``run_lock``). While it runs
it keeps ``run.json`` up to date with the step and the workers in flight, which
the dashboard shows.
"""

import os
from pathlib import Path

from . import agents
from .draft import drafter_tasks
from .explore import ANALYSTS, EXPLORE_MINUTES, explore
from .leads import reader_task
from .state import RunInProgress, log, next_action, now, run_lock, write_json

# Every batch's reader at once: the corpus is about 15 batches.
MAX_PARALLEL = 16


def tasks_for(out_dir: Path, action: dict) -> list[agents.Task]:
    """The worker tasks an agent action stands for."""
    if action["action"] == "READERS":
        return [reader_task(out_dir, c) for c in action["chunks"]]
    return drafter_tasks(out_dir, action["opportunities"])


def run_tasks(out_dir: Path, tasks: list[agents.Task], parallel: int) -> list[dict]:
    results = agents.run_wave(tasks, parallel)
    for task, r in zip(tasks, results):
        log(out_dir, f"{task.agent} " + agents.describe(r))
    return results


def run(corpus_dir: Path, out_dir: Path, steps: dict, parallel: int = MAX_PARALLEL,
        explore_minutes: float = EXPLORE_MINUTES, analysts: int = ANALYSTS, echo=print) -> str:
    """Return the final status line: DONE or FAILED <reason>."""
    try:
        with run_lock(out_dir):
            return _run(corpus_dir, out_dir, steps, parallel, explore_minutes, analysts, echo)
    except RunInProgress:
        return "FAILED another run is in progress on this output folder"


def _run(corpus_dir: Path, out_dir: Path, steps: dict, parallel: int, explore_minutes: float,
         analysts: int, echo) -> str:
    # A worker that fails is tried once more; a second failure stops the run.
    failed_before = set()
    record = {"pid": os.getpid(), "started": now(), "ended": None, "status": "running",
              "step": None, "working_on": [], "remaining": 0, "since": None, "failed": []}

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
            note(step=step, working_on=[], remaining=0, since=now())
            echo(f"{step}: {steps[step](corpus_dir, out_dir)}")

        elif kind == "DONE":
            return status("DONE")

        elif kind == "EXPLORE":
            note(step="explore", working_on=[f"analyst-{i}" for i in range(1, analysts + 1)], remaining=0, since=now())
            echo(f"explore: {analysts} analysts for {explore_minutes:g} minutes")
            echo(f"explore: {explore(corpus_dir, out_dir, explore_minutes, analysts)}")

        else:
            tasks = tasks_for(out_dir, action)
            wave = tasks[:parallel]
            note(step=kind.lower(), working_on=[t.name for t in wave], remaining=len(tasks), since=now())
            echo(f"{kind.lower()}: running {len(wave)} of {len(tasks)}")
            results = run_tasks(out_dir, wave, parallel)
            for r in results:
                echo("  " + agents.describe(r))
            failed = [r["name"] for r in results if not r["ok"]]
            if again := [name for name in failed if name in failed_before]:
                return status(f"FAILED no usable reply for {', '.join(again)}")
            if failed:
                failed_before.update(failed)
                note(failed=sorted(failed_before))
                log(out_dir, f"trying again: {', '.join(failed)}")
                echo(f"  trying again: {', '.join(failed)}")
