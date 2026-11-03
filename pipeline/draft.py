"""The drafters: one agent per top opportunity writes the artifact that would start
its change, and ``finalize`` writes each as Markdown with the report.

A drafter is given the opportunity's analysis as the critic saved it and code
scored it: the work today, the change, the figures, and the quotes with who sent
them and when. It reads no message beyond those quotes, since the analysis says
everything the change rests on, and nothing it writes is cited or ranked.
"""

from pathlib import Path

from . import agents, schemas
from .explore import figures
from .serve import report
from .state import draft_paths, log, read_json, read_messages, write_json


def _quote(c: dict, messages: dict) -> str:
    m = messages.get(c["message"], {})
    who = f"{(m.get('date') or 'undated')[:10]}, {m.get('from', 'unknown sender')}"
    return f"- {who}: “{c['quote']}”" + (f" ({c['note']})" if c.get("note") else "") + "\n"


def draft_prompt(o: dict, process: dict, messages: dict) -> str:
    evidence = process["evidence"]
    people = lambda counts: ", ".join(f"{a} ({n})" for a, n in list(counts.items())[:10])
    return (f"Opportunity {o['rank']}: {o['name']}\n\n"
            f"How the work is done today: {o['summary']}\n\n"
            f"The change: {o['change']}\n\n{o['explanation']}\n\n"
            f"The savings: {figures(o)}\n"
            "What the mail shows about the time the work takes, where it stalls, "
            "and which of its steps the change would remove:\n"
            + "".join(_quote(c, messages) for c in o["basis"])
            + "\nThe messages in which the work happens:\n"
            + "".join(_quote(c, messages) for c in evidence["occurrences"])
            + f"\nWho sends them, with how many: {people(process['senders'])}\n"
            f"Who receives them: {people(process['recipients'])}\n")


def drafter_tasks(out_dir: Path, opportunities: list[dict]) -> list[agents.Task]:
    processes = {p["id"]: p for p in read_json(out_dir / "processes.json")["processes"]}
    messages = read_messages(out_dir)
    return [agents.Task(o["id"], "drafter", draft_prompt(o, processes[o["process"]], messages),
                        draft_paths(out_dir, o)[0], schemas.DRAFT) for o in opportunities]


def markdown(draft: dict, o: dict) -> str:
    return (f"# {draft['title']}\n\n"
            f"*{draft['kind'][:1].upper() + draft['kind'][1:]}, drafted for opportunity {o['rank']}: "
            f"{o['name']}, ${o['dollars_per_month']:,.0f} a month.*\n\n"
            f"**For:** {draft['audience'].strip()}\n\n---\n\n{draft['body'].strip()}\n")


def finalize(corpus_dir: Path, out_dir: Path) -> str:
    """Each draft as Markdown, and report.json: what the dashboard shows, as one file."""
    opportunities = (read_json(out_dir / "opportunities.json") or {}).get("opportunities", [])
    written = 0
    for o in opportunities:
        reply, page = draft_paths(out_dir, o)
        if o.get("draft") and reply.exists():
            page.write_text(markdown(read_json(reply), o), encoding="utf-8")
            written += 1
    data = report(out_dir)
    write_json(out_dir / "report.json", data)
    totals = data["totals"] or {}
    summary = (f"{totals.get('ranked', 0)} opportunities ranked, ${totals.get('dollars_per_month', 0):,.0f} "
               f"a month; {written} drafted")
    log(out_dir, f"finalize: {summary}")
    return summary
