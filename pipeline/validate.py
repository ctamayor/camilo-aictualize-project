"""Check every scout citation against the corpus and build the merge input.

A citation survives only if its message is in the scout's own batch, no scout
marked that message untrusted, and the quote appears in the message as parsed
from its raw file (headers and decoded body, as the scout was shown them).
Quotes are compared after collapsing whitespace, straightening quote characters,
dropping control characters and removing the ">" markers at the start of quoted
reply lines (the scout may write line breaks as spaces and skip the markers, and
cannot write a stray control byte), and ignoring case. A kept
citation's quote is replaced by the message's own text, so what is shown is
verbatim. A pattern left with no occurrence is dropped. Every rejected citation
is kept with its reason so failures can be investigated.

The stats are how a run's reading is judged: how many citations fail and why,
how much of each batch the patterns cover, and how many patterns rest on a
single message in their batch (patterns the scout expects to recur elsewhere).
"""

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .ingest import parse_message, read_raw
from .state import log, merge_paths, read_json, scout_output, write_json

# Quote characters straightened, and control characters that are not whitespace dropped.
QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}
                            | dict.fromkeys(map(chr, [*range(0x00, 0x09), *range(0x0e, 0x1c), 0x7f])))
REPLY_MARKERS = re.compile(r"^[ \t]*(?:>[ \t]*)+", re.MULTILINE)


def normalize(text: str) -> str:
    return " ".join(REPLY_MARKERS.sub("", text).translate(QUOTE_CHARS).split())


def find_quote(quote: str, text: str) -> str | None:
    """Return the span of normalized ``text`` matching ``quote`` ignoring case, or None.

    The corpus is ASCII, so lowercasing keeps every offset in place."""
    q = normalize(quote)
    i = text.lower().find(q.lower()) if q else -1
    return text[i:i + len(q)] if i >= 0 else None


def canonical(message_id: str, batch: set[str]) -> str:
    """Restore a dropped trailing dot: scouts sometimes write "x/12" for "x/12.",
    reading the dot as punctuation. Every id ends in a dot, so this is unambiguous."""
    if message_id not in batch and message_id + "." in batch:
        return message_id + "."
    return message_id


def check(citation: dict, batch: set[str], untrusted: set[str], text_of) -> tuple[str | None, str | None]:
    """Return (why the citation fails, None) or (None, the message's own text for the quote)."""
    if citation["message"] not in batch:
        return "message not in batch", None
    if citation["message"] in untrusted:
        return "cites an untrusted message", None
    if not normalize(citation["quote"]):
        return "empty quote", None
    span = find_quote(citation["quote"], text_of(citation["message"]))
    return (None, span) if span else ("quote not in message", None)


def parsed(corpus_dir: Path):
    """Return a cached lookup of a message as parsed from its raw file."""
    return lru_cache(maxsize=None)(lambda message_id: parse_message(message_id, read_raw(corpus_dir, message_id)))


def message_text(parse):
    """Return a cached lookup of a message's normalized text."""
    @lru_cache(maxsize=None)
    def text_of(message_id: str) -> str:
        m = parse(message_id)
        return normalize(f"From: {m['from']}\nTo: {m['to']}\nCc: {m['cc']}\nSubject: {m['subject']}\n\n{m['body']}")
    return text_of


def validate(corpus_dir: Path, out_dir: Path) -> str:
    chunks = read_json(out_dir / "chunks.json")["chunks"]
    replies = {c["id"]: read_json(scout_output(out_dir, c)) for c in chunks}
    untrusted_ids = {canonical(u["message"], set(c["message_ids"]))
                     for c in chunks for u in replies[c["id"]]["untrusted"]}
    parse = parsed(corpus_dir)
    text_of = message_text(parse)

    patterns, untrusted, rejected = [], [], []
    per_chunk = {}
    for chunk in chunks:
        reply, batch = replies[chunk["id"]], set(chunk["message_ids"])
        stats = Counter({k: 0 for k in ("citations_checked", "ids_repaired", "patterns_recorded",
                                        "patterns_kept", "single_occurrence")}, messages=len(batch))
        reasons = Counter()
        covered = set()

        def keep(citation, kind, pattern_id, distrust=untrusted_ids):
            """Return the citation (with its id repaired if needed) if it holds, else None."""
            message = canonical(citation["message"], batch)
            stats["ids_repaired"] += message != citation["message"]
            citation = citation | {"message": message}
            problem, span = check(citation, batch, distrust, text_of)
            stats["citations_checked"] += 1
            if problem:
                reasons[problem] += 1
                rejected.append({"chunk": chunk["id"], "pattern": pattern_id, "kind": kind, **citation,
                                 "reason": problem})
                return None
            return citation | {"quote": span}

        for u in reply["untrusted"]:
            if u := keep(u, "untrusted", None, distrust=set()):
                untrusted.append({"chunk": chunk["id"], **u})
        stats["untrusted"] = len({canonical(u["message"], batch) for u in reply["untrusted"]})

        for i, p in enumerate(reply["patterns"], 1):
            pid = f"{chunk['id']}.p{i:02d}"
            # Occurrences are messages, so each counts once; observations once per quote.
            occurrences, seen = [], set()
            for o in p["occurrences"]:
                if (o := keep(o, "occurrence", pid)) and o["message"] not in seen:
                    seen.add(o["message"])
                    occurrences.append(o)
            noted = {}
            for kind in ("observations", "stalls"):
                noted[kind], seen = [], set()
                # Outputs from before scouts recorded stalls have none.
                for o in p.get(kind, []):
                    if (o := keep(o, kind[:-1], pid)) and (o["message"], normalize(o["quote"])) not in seen:
                        seen.add((o["message"], normalize(o["quote"])))
                        noted[kind].append(o)
            stats["patterns_recorded"] += 1
            if not occurrences:
                continue
            stats["patterns_kept"] += 1
            stats["single_occurrence"] += len(occurrences) == 1
            covered |= {o["message"] for o in occurrences + noted["observations"] + noted["stalls"]}
            patterns.append({"id": pid, "chunk": chunk["id"], "name": p["name"], "summary": p["summary"],
                             "occurrences": occurrences, **noted})

        stats["messages_covered"] = len(covered)
        per_chunk[chunk["id"]] = dict(stats) | {"rejected": dict(reasons)}

    total = sum((Counter({k: v for k, v in s.items() if k != "rejected"}) for s in per_chunk.values()), Counter())
    total = dict(total) | {"rejected": dict(Counter(r["reason"] for r in rejected))}

    write_json(out_dir / "validated.json", {"stats": {"total": total, "chunks": per_chunk},
                                            "patterns": patterns, "untrusted": untrusted,
                                            "rejected": rejected})
    names_path, _ = merge_paths(out_dir)
    # The merger judges which patterns are the same work, so it sees when and by whom each was done.
    shown = lambda o: {"month": (parse(o["message"])["date"] or "undated")[:7], "from": parse(o["message"])["from"],
                       "quote": o["quote"]}
    # Written last: it is what marks this step as finished.
    write_json(names_path, {"patterns": [{"id": p["id"], "name": p["name"], "summary": p["summary"],
                                          "occurrences": [shown(o) for o in p["occurrences"]]} for p in patterns]})

    summary = (f"{total.get('patterns_kept', 0)} of {total.get('patterns_recorded', 0)} patterns kept "
               f"({total.get('single_occurrence', 0)} on one message), "
               f"{len(rejected)} of {total.get('citations_checked', 0)} citations rejected "
               f"({total.get('ids_repaired', 0)} ids repaired), "
               f"{len(untrusted_ids)} untrusted messages, "
               f"{total.get('messages_covered', 0)} of {total.get('messages', 0)} messages covered")
    log(out_dir, f"validate: {summary}")
    for reason, n in sorted(total["rejected"].items()):
        log(out_dir, f"validate: rejected {n} ({reason})")
    # A scout that stopped short shows up here as a batch with little of it cited.
    for cid, s in per_chunk.items():
        log(out_dir, f"validate: {cid} cites {s['messages_covered']} of {s['messages']} messages "
                     f"in {s['patterns_kept']} patterns")
    return summary
