"""Turn a saved proposal's citations into a process, with its evidence and counts.

Everything counted here comes from the checked citations and the messages: the
messages that are occurrences (each once), the times the work happened, when they
were sent, and who sent and received them.

A message and the replies and forwards that answer it are one time the work
happened, not several: a request answered in three replies was done once. A
later occurrence is the same time as the latest earlier one it answers. Where
its mail client recorded what it answers (In-Reply-To, References), that
decides. Otherwise, among earlier occurrences with the same subject (less
RE:/FW:), it answers:

- one whose own text it quotes. A message's own text is what comes before the
  first header of a message it quotes ("Original Message", "Forwarded by", a
  From:/Sent: or To: block, or ">" lines).
- one that quotes the same text, as two replies to one message do.
- the latest, if it is a reply or forward (RE:/FW:) that quotes nothing, since
  then its subject is all that says what it answers.
- one it is a copy of: the same own text, sent within the window in which
  ingest treats same-content messages as copies.

Recurring mail with one subject, such as a daily nomination, is no reply, quotes
nothing and is sent a day apart, so each day stays a time.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from statistics import median

from .ingest import DUPLICATE_WINDOW_HOURS, normalize_subject
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
        if messages[i].get("replies_to"):
            return messages[j].get("message_id") in messages[i]["replies_to"]
        if not subjects[i] or subjects[j] != subjects[i]:
            return False
        (own_i, quoted_i), (own_j, quoted_j) = parts[i], parts[j]
        if own_j and own_j in quoted_i or quoted_i and quoted_i == quoted_j:
            return True
        if not quoted_i and REPLY.match(messages[i].get("subject", "")):
            return True
        return bool(own_j) and own_i == own_j and \
            _hours_apart(messages[i]["date"], messages[j]["date"]) <= DUPLICATE_WINDOW_HOURS

    time_of = {}
    for k, i in enumerate(order):
        earlier = [j for j in order[:k] if same_time(i, j)]
        time_of[i] = time_of[earlier[-1]] if earlier else len(set(time_of.values())) + 1
    return [time_of[i] for i in range(len(messages))]


def build_process(name: str, summary: str, ids: list[str], patterns: dict, headers: dict) -> dict:
    occurrences, seen_messages = [], set()
    noted = {"observations": []}
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


KINDS = ("occurrences", "observations")


def numbered_quotes(process: dict) -> dict:
    """Each quote of a process by id, in pattern order: occurrences, then observations."""
    quotes = {}
    for pid in process["patterns"]:
        for kind in KINDS:
            for citation in process["evidence"].get(kind, []):
                if citation["pattern"] == pid:
                    quotes[f"q{len(quotes) + 1}"] = citation
    return quotes
