"""The estimators' input: every process with its people, patterns and quotes.

The estimators read no message text. For each process they get what the scouts
recorded and code validated: each pattern's name and summary, the quote showing
each occurrence, each observation's quote and note, and each stall's quote and
note, marked as a reader's note since it is a reading of the quote, not its
words. They also get how many times began in each month. Each quote gets an id within its process (q1, q2, ...) so an estimate can
name the quotes it rests on without copying them; the score step maps the ids
back to the quotes and their messages.

The processes are estimated in slices, one estimator each. In one call over 104
processes the reasoning shrank steadily down the list (trial6: from about 144
characters to 36), and the processes at the end are the small ones that rank
highest when a stated rate lifts them. Each slice takes every k-th process by
size, so each spans the whole range, and every estimator also sees every
process's name, summary and count, so all estimates are made on one scale.
"""

import math

# About as many processes as one estimator still reasoned about in full.
ESTIMATE_SLICE = 20
KINDS = ("occurrences", "observations", "stalls")


def numbered_quotes(process: dict) -> dict:
    """Each quote of a process by id, in pattern order: occurrences, observations, then stalls."""
    quotes = {}
    for pid in process["patterns"]:
        for kind in KINDS:
            for citation in process["evidence"].get(kind, []):
                if citation["pattern"] == pid:
                    quotes[f"q{len(quotes) + 1}"] = citation
    return quotes


def slices(processes: list[dict]) -> list[list[str]]:
    """The process ids each estimator estimates."""
    n = math.ceil(len(processes) / ESTIMATE_SLICE)
    return [[p["id"] for p in processes[i::n]] for i in range(n)]


def _most(counts: dict, n: int = 3) -> str:
    return ", ".join(f"{address} ({k})" for address, k in list(counts.items())[:n]) or "no one"


def _when(process: dict) -> str:
    span = f"between {process['first'][:10]} and {process['last'][:10]}" if process.get("first") else "undated"
    # By month, so a burst of times in one month shows as a burst.
    months = ", ".join(f"{m}: {n}" for m, n in process.get("months", {}).items())
    return (f"Happened {process['times']} times in the archive ({process['occurrences']} messages, a reply counted "
            f"with what it answers), {span}." + (f" Times begun each month: {months}." if months else ""))


def describe(process: dict, patterns: dict) -> str:
    lines = [f"## {process['id']}: {process['name']}", process["summary"], _when(process),
             f"Most often from {_most(process['senders'])}; most often to {_most(process['recipients'])}; "
             f"a median of {process['median_recipients']:g} addresses per message."]
    quotes = numbered_quotes(process)
    stalls = {id(c) for c in process["evidence"].get("stalls", [])}
    for pid in process["patterns"]:
        lines.append(f"\nPattern {pid} | {patterns[pid]['name']} | {patterns[pid]['summary']}")
        for qid, c in quotes.items():
            if c["pattern"] == pid:
                label = "Stall: " if id(c) in stalls else ""
                lines.append(f'{qid}: {label}"{c["quote"]}"' + (f" Reader's note: {c['note']}" if "note" in c else ""))
    return "\n".join(lines)


def estimate_prompt(processes: list[dict], patterns: dict, slice_ids: list[str] | None = None) -> str:
    """The prompt for the estimator of ``slice_ids`` (by default, every process)."""
    ids = set(slice_ids) if slice_ids is not None else {p["id"] for p in processes}
    mine = [p for p in processes if p["id"] in ids]
    others = [p for p in processes if p["id"] not in ids]
    text = f"{len(mine)} processes follow. Estimate every one.\n\n" + "\n\n".join(describe(p, patterns) for p in mine) + "\n"
    if others:
        text += (f"\n# The other {len(others)} processes, estimated by others: for scale only\n\n"
                 + "".join(f"{p['id']}: {p['name']} ({p['times']} times). {p['summary']}\n" for p in others))
    return text
