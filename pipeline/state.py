"""Decide the single next action of a run by looking at what is in ``out/``.

A step is finished when its output file exists, so re-running against an
unchanged corpus repeats nothing. When messages are added or changed,
``prepare`` keeps every chunk (and its scout output) that is unaffected and
clears only the corpus-wide results in ``CORPUS_WIDE_OUTPUTS``.

Actions:

    RUN <step>        a deterministic step
    SCOUTS            one scout per chunk without output
    MERGE             one merger: which patterns are the same process
    ESTIMATE          one estimator per slice of the processes without output
    DRAFTERS         one drafter per selected opportunity without a draft
    DONE
"""

import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from .estimate import slices
from .ingest import iter_corpus

# Built from every scout output at once, so stale whenever any chunk changes.
CORPUS_WIDE_OUTPUTS = ["merge", "evidence", "drafts", "validated.json", "processes.json",
                       "estimates", "opportunities.json", "report.json"]
# Everything a run writes. Starting over removes these and nothing else.
RUN_OUTPUTS = ["chunks.json", "chunks", "scout", "messages.jsonl", "ingest_report.json",
               *CORPUS_WIDE_OUTPUTS, "run.json", "run.log", "run.lock"]


def corpus_digest(corpus_dir: Path) -> str:
    h = hashlib.sha256()
    for mid, raw in iter_corpus(corpus_dir):
        h.update(f"{mid}\0".encode("utf-8") + raw.encode("latin-1"))
    return h.hexdigest()


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_messages(out_dir: Path) -> dict:
    """Every parsed message from ``prepare``, by id."""
    with open(out_dir / "messages.jsonl", encoding="utf-8") as fh:
        return {m["id"]: m for m in map(json.loads, fh)}


def remove_outputs(out_dir: Path, names: list[str]) -> int:
    removed = 0
    for name in names:
        target = out_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        else:
            continue
        removed += 1
    return removed


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log(out_dir: Path, line: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "run.log", "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")


# --- one run at a time per output folder -------------------------------------

class RunInProgress(Exception):
    """Another run is working on this output folder."""


def _try_lock(fh) -> bool:
    fh.seek(0)
    try:
        if os.name == "nt":
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fh) -> None:
    fh.seek(0)
    if os.name == "nt":
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fh, fcntl.LOCK_UN)


@contextmanager
def run_lock(out_dir: Path):
    """Held while a run works on ``out_dir``. The operating system releases it
    when the run's process ends, however it ends, so a killed run never leaves
    the folder locked."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "run.lock", "a+") as fh:
        if not _try_lock(fh):
            raise RunInProgress(str(out_dir))
        try:
            yield
        finally:
            _unlock(fh)


def run_active(out_dir: Path) -> bool:
    if not (out_dir / "run.lock").exists():
        return False
    with open(out_dir / "run.lock", "a+") as fh:
        if _try_lock(fh):
            _unlock(fh)
            return False
        return True


# --- file locations shared with the steps that produce them ----------------

def scout_output(out_dir: Path, chunk: dict) -> Path:
    return out_dir / "scout" / f"{chunk['id']}.json"


def merge_paths(out_dir: Path) -> tuple[Path, Path]:
    return out_dir / "merge" / "names.json", out_dir / "merge" / "map.json"


def estimate_slices(out_dir: Path) -> list[dict]:
    """The estimators' slices of the processes, each with where its estimates go."""
    processes = (read_json(out_dir / "processes.json") or {}).get("processes", [])
    return [{"id": f"slice-{i:02d}", "processes": ids, "output": out_dir / "estimates" / f"slice-{i:02d}.json"}
            for i, ids in enumerate(slices(processes), 1)]


def draft_paths(out_dir: Path, opportunity: dict) -> tuple[Path, Path]:
    return out_dir / "evidence" / f"{opportunity['id']}.json", out_dir / "drafts" / f"{opportunity['id']}.md"


def next_action(corpus_dir: Path, out_dir: Path) -> dict:
    chunks_doc = read_json(out_dir / "chunks.json")
    if not isinstance(chunks_doc, dict) or chunks_doc.get("corpus_sha256") != corpus_digest(corpus_dir):
        return {"action": "RUN", "step": "prepare"}
    chunks = chunks_doc["chunks"]

    pending = [c for c in chunks if not scout_output(out_dir, c).exists()]
    if pending:
        return {"action": "SCOUTS", "chunks": pending}

    names_path, map_path = merge_paths(out_dir)
    if not names_path.exists():
        return {"action": "RUN", "step": "validate"}
    if not map_path.exists():
        return {"action": "MERGE", "input": names_path, "output": map_path}
    if not (out_dir / "processes.json").exists():
        return {"action": "RUN", "step": "group"}
    pending = [s for s in estimate_slices(out_dir) if not s["output"].exists()]
    if pending:
        return {"action": "ESTIMATE", "slices": pending}

    opportunities = read_json(out_dir / "opportunities.json")
    if opportunities is None:
        return {"action": "RUN", "step": "score"}

    pending = [o for o in opportunities["opportunities"]
               if o.get("draft") and not draft_paths(out_dir, o)[1].exists()]
    if pending:
        return {"action": "DRAFTERS", "opportunities": pending}

    if not (out_dir / "report.json").exists():
        return {"action": "RUN", "step": "finalize"}
    return {"action": "DONE"}


def progress(out_dir: Path) -> list[dict]:
    """How far each step has got, read from the files in ``out_dir``, in the order
    ``next_action`` takes them. Unlike ``next_action`` it does not check the
    corpus, so it is cheap enough for the dashboard to ask every few seconds."""
    chunks = (read_json(out_dir / "chunks.json") or {}).get("chunks")
    names, mapping = merge_paths(out_dir)
    opportunities = (read_json(out_dir / "opportunities.json") or {}).get("opportunities")
    to_draft = [o for o in opportunities or [] if o.get("draft")]
    estimate = estimate_slices(out_dir)
    steps = [
        ("prepare", chunks is not None, None),
        ("scouts", None, [sum(scout_output(out_dir, c).exists() for c in chunks or []), len(chunks or [])]),
        ("validate", names.exists(), None),
        ("merge", mapping.exists(), None),
        ("group", (out_dir / "processes.json").exists(), None),
        ("estimate", None, [sum(s["output"].exists() for s in estimate), len(estimate)]),
        ("score", opportunities is not None, None),
        ("drafters", None, [sum(draft_paths(out_dir, o)[1].exists() for o in to_draft), len(to_draft)]),
        ("finalize", (out_dir / "report.json").exists(), None),
    ]
    # A counted step is done once its inputs exist and every item has its output.
    done_before = True
    result = []
    for step, done, count in steps:
        if done is None:
            done = done_before and count[0] == count[1]
        result.append({"step": step, "done": done, "count": count})
        done_before = done
    return result


def format_action(a: dict) -> str:
    if a["action"] == "RUN":
        return f"RUN {a['step']}"
    if a["action"] == "SCOUTS":
        return f"SCOUTS {len(a['chunks'])} pending: " + " ".join(c["id"] for c in a["chunks"])
    if a["action"] == "ESTIMATE":
        return f"ESTIMATE {len(a['slices'])} pending: " + " ".join(s["id"] for s in a["slices"])
    if a["action"] == "DRAFTERS":
        return f"DRAFTERS {len(a['opportunities'])} pending: " + " ".join(o["id"] for o in a["opportunities"])
    if a["action"] == "MERGE":
        return f"{a['action']} {a['input'].name} -> {a['output'].name}"
    return "DONE"
