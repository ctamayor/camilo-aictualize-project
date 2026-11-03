"""The readers: one agent per batch reads every message in it, so that every message
in the archive is read, and records the work it noticed as leads for the analysts.

A lead names the files of the messages that show it. Only files of messages in the
reader's own batch are kept, since those are the only ones it read; a lead left
with none is dropped. ``leads.md`` lists what is kept, for the analysts to start
from. Nothing in it has been checked, and nothing in it is ranked: only what a
critic saves is.
"""

from pathlib import Path

from . import agents, schemas
from .ingest import message_id
from .state import leads_output, log, read_json


def reader_task(out_dir: Path, chunk: dict) -> agents.Task:
    text = (out_dir / chunk["file"]).read_text(encoding="utf-8")
    prompt = f"Batch {chunk['id']}: {len(chunk['message_ids'])} messages.\n\n{text}"
    return agents.Task(chunk["id"], "reader", prompt, leads_output(out_dir, chunk), schemas.READER)


def checked_leads(out_dir: Path) -> tuple[list[dict], int, int]:
    """Every batch's leads with only the files of its own messages, as corpus paths,
    and how many files and leads were dropped."""
    kept, files_dropped, leads_dropped = [], 0, 0
    for chunk in read_json(out_dir / "chunks.json")["chunks"]:
        batch = dict.fromkeys(chunk["message_ids"])
        for lead in (read_json(leads_output(out_dir, chunk)) or {}).get("leads", []):
            ids = [message_id(f, batch, {}) for f in lead["files"]]
            files = list(dict.fromkeys(f"corpus/{i.removesuffix('.')}.eml" for i in ids if i))
            files_dropped += len(ids) - sum(map(bool, ids))
            if files:
                kept.append({"work": lead["work"], "why": lead["why"], "files": files})
            else:
                leads_dropped += 1
    return kept, files_dropped, leads_dropped


def leads_markdown(out_dir: Path) -> str:
    leads, files_dropped, leads_dropped = checked_leads(out_dir)
    log(out_dir, f"leads: {len(leads)} kept; {leads_dropped} dropped for naming no message of their batch, "
                 f"{files_dropped} files dropped for not being in their batch")
    return ("# Leads\n\nWork that readers of every message in the archive noticed, batch by batch, "
            "with the files that show it. None of it has been checked.\n\n"
            + "".join(f"- {l['work']}: {l['why']} Files: {', '.join(l['files'])}\n" for l in leads))
