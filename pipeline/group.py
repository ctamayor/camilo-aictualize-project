"""Turn the merge reply into processes, each with its evidence and counts.

The merge agent only says which patterns are the same process. Everything
counted here comes from the validated citations and the messages: the messages
that are occurrences (each once), the times the work happened, when they were
sent, and who sent and received them.

A message and the replies and forwards that quote it are one time the work
happened, not several: a request answered in three replies was done once. A
later occurrence with the same subject (less RE:/FW:) is the same time as the
latest earlier one it matches:

- any earlier one, if it is a reply or forward (RE:/FW:). A reply belongs to
  the thread its subject names, whether or not it quotes it: Notes replies often
  quote nothing, and forwards are often edited.
- one whose own text it quotes. A message's own text is what comes before the
  first header of a message it quotes ("Original Message", "Forwarded by", a
  From:/Sent: or To: block, or ">" lines).
- one it is a copy of: the same own text, sent within the window in which
  ingest treats same-content messages as copies.

Recurring mail with one subject, such as a daily nomination, is no reply, quotes
nothing and is sent a day apart, so each day stays a time. A pattern the merge did not list
stays a process of its own, an id it invented is ignored, and a pattern it
listed twice stays in the first process it was listed in. Each of those problems
is logged.

The stats are the second measure of the reading: of the patterns that rested on
one message in their batch, how many turned out to recur, that is, ended up in a
process with more than one message.
"""

import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

from .ingest import DUPLICATE_WINDOW_HOURS, normalize_subject
from .state import log, merge_paths, read_json, read_messages, write_json
from .validate import normalize


def _addresses(field: str) -> list[str]:
    return [a.strip().lower() for a in field.split(",") if a.strip()]


def _ranked(counter: Counter) -> dict:
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


QUOTE_START = re.compile(r"-{2,}\s*Original Message\s*-{2,}|-{3,}\s*Forwarded by|^[ \t]*From:.*\n[ \t]*Sent:"
                         r"|^[ \t]*To:[ \t]|^[ \t]*>|wrote:[ \t]*$", re.MULTILINE | re.IGNORECASE)
REPLY = re.compile(r"\s*(re|fw|fwd)\s*:", re.IGNORECASE)


def split_quoted(body: str) -> tuple[str, str]:
    """A message's own text and the text it quotes, both normalized and lowercased."""
    m = QUOTE_START.search(body)
    own, quoted = (body[:m.start()], body[m.start():]) if m else (body, "")
    return normalize(own).lower(), normalize(quoted).lower()


def _hours_apart(a: str | None, b: str | None) -> float:
    if a is None or b is None:
        return float("inf")
    return abs(datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds() / 3600


def count_times(messages: list[dict]) -> list[int]:
    """For each message, the number of the time it belongs to (1, 2, ...), in date order."""
    order = sorted(range(len(messages)), key=lambda i: (messages[i]["date"] or "9", messages[i]["id"]))
    parts = {i: split_quoted(messages[i].get("body", "")) for i in order}
    subjects = {i: normalize_subject(messages[i].get("subject", "")) for i in order}

    def same_time(i: int, j: int) -> bool:
        (own_i, quoted_i), (own_j, _) = parts[i], parts[j]
        if REPLY.match(messages[i].get("subject", "")):
            return True
        if own_j and own_j in quoted_i:
            return True
        return bool(own_j) and own_i == own_j and \
            _hours_apart(messages[i]["date"], messages[j]["date"]) <= DUPLICATE_WINDOW_HOURS

    time_of = {}
    for k, i in enumerate(order):
        earlier = [j for j in order[:k] if subjects[i] and subjects[j] == subjects[i] and same_time(i, j)]
        time_of[i] = time_of[earlier[-1]] if earlier else len(set(time_of.values())) + 1
    return [time_of[i] for i in range(len(messages))]


def build_process(name: str, summary: str, ids: list[str], patterns: dict, headers: dict) -> dict:
    occurrences, seen_messages = [], set()
    noted = {"observations": [], "stalls": []}
    seen_quotes = {kind: set() for kind in noted}
    for pid in ids:
        for o in patterns[pid]["occurrences"]:
            if o["message"] not in seen_messages:
                seen_messages.add(o["message"])
                occurrences.append(o | {"pattern": pid})
        for kind in noted:
            for o in patterns[pid].get(kind, []):
                key = (o["message"], normalize(o["quote"]))
                if key not in seen_quotes[kind]:
                    seen_quotes[kind].add(key)
                    noted[kind].append(o | {"pattern": pid})

    messages = [headers[o["message"]] for o in occurrences]
    for o, time in zip(occurrences, count_times(messages)):
        o["time"] = time
    dates = sorted(m["date"] for m in messages if m["date"])
    began = {}  # each time's first dated message
    for o, m in zip(occurrences, messages):
        if m["date"] and m["date"] < began.get(o["time"], "9"):
            began[o["time"]] = m["date"]
    senders, recipients, reach = Counter(), Counter(), []
    for m in messages:
        addressed = set(_addresses(m["to"]) + _addresses(m["cc"]))
        senders.update(_addresses(m["from"]))
        recipients.update(addressed)
        reach.append(len(addressed))
    return {
        "name": name,
        "summary": summary,
        "patterns": ids,
        "chunks": sorted({patterns[pid]["chunk"] for pid in ids}),
        "occurrences": len(occurrences),
        "times": len({o["time"] for o in occurrences}),
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
        "months": dict(sorted(Counter(d[:7] for d in began.values()).items())),  # times begun each month
        "senders": _ranked(senders),
        "recipients": _ranked(recipients),
        "median_recipients": median(reach) if reach else 0,
        "evidence": {"occurrences": occurrences, **noted},
    }


def group(corpus_dir: Path, out_dir: Path) -> str:
    patterns = {p["id"]: p for p in read_json(out_dir / "validated.json")["patterns"]}
    reply = read_json(merge_paths(out_dir)[1])
    headers = read_messages(out_dir)

    groups, placed, problems = [], set(), Counter()
    for proc in reply["processes"]:
        ids = []
        for pid in proc["patterns"]:
            if pid not in patterns:
                problems["unknown pattern id"] += 1
            elif pid in placed:
                problems["pattern listed twice"] += 1
            else:
                placed.add(pid)
                ids.append(pid)
        if ids:
            groups.append((proc["name"], proc["summary"], ids))
    groups += [(p["name"], p["summary"], [pid]) for pid, p in patterns.items() if pid not in placed]

    processes = [build_process(*g, patterns, headers) for g in groups]
    processes.sort(key=lambda p: (-p["times"], -p["occurrences"], p["patterns"][0]))
    processes = [{"id": f"proc-{i:03d}"} | p for i, p in enumerate(processes, 1)]

    home = {pid: p for p in processes for pid in p["patterns"]}
    single = [pid for pid, p in patterns.items() if len(p["occurrences"]) == 1]
    stats = {
        "patterns": len(patterns),
        "processes": len(processes),
        "merged": sum(len(p["patterns"]) > 1 for p in processes),
        "one_message_patterns": len(single),
        "one_message_patterns_recurring": sum(home[pid]["occurrences"] > 1 for pid in single),
        "one_message_processes": sum(p["occurrences"] == 1 for p in processes),
        "one_time_processes": sum(p["times"] == 1 for p in processes),
        "messages": sum(p["occurrences"] for p in processes),
        "times": sum(p["times"] for p in processes),
        "merge_problems": dict(problems),
    }
    write_json(out_dir / "processes.json", {"stats": stats, "processes": processes})

    summary = (f"{stats['processes']} processes from {stats['patterns']} patterns ({stats['merged']} merged); "
               f"{stats['one_message_patterns_recurring']} of {stats['one_message_patterns']} one-message "
               f"patterns recur; {stats['times']} times in {stats['messages']} messages; "
               f"{stats['one_time_processes']} processes happen once")
    log(out_dir, f"group: {summary}")
    for problem, n in sorted(problems.items()):
        log(out_dir, f"group: merge reply had {n} x {problem}")
    return summary
