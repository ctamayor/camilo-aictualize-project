"""Command line entry point: ``python -m pipeline <step>``."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import CORPUS_DIR, OUT_DIR, run as runner, serve as dashboard
from .chunk import build_chunks
from .draft import finalize
from .explore import ANALYSTS, EXPLORE_MINUTES, coverage, check, coverage_line, reject, save
from .ingest import ingest
from .state import (CORPUS_WIDE_OUTPUTS, RUN_OUTPUTS, corpus_digest, format_action, log, next_action,
                    read_json, remove_outputs, run_active, write_json)


def prepare(corpus_dir: Path, out_dir: Path) -> str:
    messages, report = ingest(corpus_dir)
    previous = read_json(out_dir / "chunks.json")
    previous = previous["chunks"] if isinstance(previous, dict) else []
    chunks = build_chunks(messages, previous=previous)

    # Unchanged chunks keep their reader's leads. Any change at all invalidates
    # the corpus-wide results.
    current = {(c["id"], c["sha256"]) for c in chunks}
    if current != {(c["id"], c["sha256"]) for c in previous}:
        for stale in (out_dir / "leads").glob("chunk-*.json"):
            if stale.stem not in {c["id"] for c in chunks}:
                stale.unlink()
        remove_outputs(out_dir, CORPUS_WIDE_OUTPUTS)

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "messages.jsonl", "w", encoding="utf-8") as fh:
        for m in messages:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")

    chunk_dir = out_dir / "chunks"
    chunk_dir.mkdir(exist_ok=True)
    for stale in chunk_dir.glob("chunk-*.txt"):
        if stale.stem not in {c["id"] for c in chunks}:
            stale.unlink()
    for c in chunks:
        end = f"===== END OF {c['id']}: {len(c['message_ids'])} messages, last was {c['message_ids'][-1]} =====\n"
        (chunk_dir / f"{c['id']}.txt").write_text(c["text"] + end, encoding="utf-8")

    report["chunks"] = len(chunks)
    report["est_tokens_total"] = sum(c["est_tokens"] for c in chunks)
    write_json(out_dir / "ingest_report.json", report)
    # Written last: it is what marks this step as finished.
    write_json(out_dir / "chunks.json", {
        "corpus_sha256": corpus_digest(corpus_dir),
        "chunks": [{k: v for k, v in c.items() if k != "text"} | {"file": f"chunks/{c['id']}.txt"}
                   for c in chunks],
    })
    summary = (f"read {report['files_read']} files, {report['unique_messages']} unique "
               f"({report['duplicates_removed']} duplicates), {len(report['date_issues'])} date issues, "
               f"{report['chunks']} chunks (~{report['est_tokens_total']:,} tokens)")
    log(out_dir, f"prepare: {summary}")
    return summary


STEPS = {"prepare": prepare, "finalize": finalize}


def status(corpus_dir: Path, out_dir: Path) -> str:
    """Whether ``out_dir`` already holds a run, and what running again would do."""
    if run_active(out_dir):
        return f"RUNNING a run is in progress on {out_dir}"
    if not (out_dir / "chunks.json").exists():
        return f"NONE no earlier run in {out_dir}"
    action = next_action(corpus_dir, out_dir)
    if action["action"] == "DONE":
        return "DONE the earlier run finished; running again repeats nothing"
    if action == {"action": "RUN", "step": "prepare"}:
        return "CHANGED the corpus has changed since the earlier run; running again redoes only what the change affects"
    return f"STOPPED the earlier run stopped before {format_action(action)}; running again continues from there"


def reset(out_dir: Path) -> str:
    """Remove every output of the run in ``out_dir``, so the next run starts over."""
    if run_active(out_dir):
        sys.exit(f"a run is in progress on {out_dir}; nothing was removed")
    removed = remove_outputs(out_dir, RUN_OUTPUTS)
    return f"reset: removed {removed} outputs from {out_dir}"


def start_dashboard(out_dir: Path, corpus_dir: Path) -> str:
    try:
        return dashboard.ensure_running(out_dir, corpus_dir)
    except RuntimeError as e:
        return f"not started: {e}"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("step", choices=["run", "status", "reset", "dashboard", "serve", "next", "check", "save", "reject", "coverage", *STEPS])
    parser.add_argument("ids", nargs="*", help="check, save, reject: the proposal or rejection file")
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    # The critic runs check, save and reject from the agents' folder, where the run sets PIPELINE_OUT.
    parser.add_argument("--out", type=Path, default=Path(os.environ.get("PIPELINE_OUT") or OUT_DIR))
    parser.add_argument("--parallel", type=int, default=runner.MAX_PARALLEL, help="run: the readers or drafters to run at once")
    parser.add_argument("--minutes", type=float, default=EXPLORE_MINUTES, help="run: the minutes the analysts explore")
    parser.add_argument("--analysts", type=int, default=ANALYSTS, help="run: the analysts to run at once")
    parser.add_argument("--port", type=int, default=dashboard.PORT, help="serve: the port to listen on")
    args = parser.parse_args()

    if args.step == "run":
        # The dashboard is up before any work starts, so the run can be watched.
        print(f"dashboard: {start_dashboard(args.out, args.corpus)}", flush=True)
        line = runner.run(args.corpus, args.out, STEPS, args.parallel, args.minutes, args.analysts,
                          echo=lambda text: print(text, flush=True))
        print(line)
        sys.exit(1 if line.startswith("FAILED") else 0)
    elif args.step in ("check", "save", "reject"):
        file = args.ids[0] if args.ids else None
        done, text = reject(args.out, file) if args.step == "reject" else             {"check": check, "save": save}[args.step](args.corpus, args.out, file)
        print(text)
        # Asking what a command needs is not a failure; a file it refuses is.
        sys.exit(0 if done or not args.ids else 1)
    elif args.step == "coverage":
        print(coverage_line(coverage(args.out)))
    elif args.step == "status":
        print(status(args.corpus, args.out))
    elif args.step == "reset":
        print(reset(args.out))
    elif args.step == "dashboard":
        print(f"dashboard: {start_dashboard(args.out, args.corpus)}")
    elif args.step == "serve":
        dashboard.serve(args.out, args.corpus, args.port)
    elif args.step == "next":
        print(format_action(next_action(args.corpus, args.out)))
    elif args.step in STEPS:
        print(STEPS[args.step](args.corpus, args.out))


if __name__ == "__main__":
    main()
