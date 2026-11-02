"""Pack messages into chunk files a single scout can read in one context.

Messages with the same normalized subject stay in the same chunk so a reply is
read next to the message it answers. A message larger than the budget gets a
chunk of its own rather than being truncated.
"""

import hashlib
import math
import re

from .ingest import normalize_subject

# Token budget per chunk. 100K packs the corpus into about 15 chunks. At 200K
# (7 chunks) a scout's recall fell in the back half of its batch and one scout
# stopped short altogether, so 1,418 messages were cited against 2,163 at 100K
# (trial6 against trial4). Token counts are estimated, not measured, at 3.5
# chars/token; the model counts about three quarters of that for this mail.
CHUNK_TOKEN_BUDGET = 100_000
CHARS_PER_TOKEN = 3.5

# Broadcasts list hundreds of recipients on one line. The full lists stay in
# messages.jsonl for the people counts; scouts only need to see it's a broadcast.
MAX_RECIPIENTS_SHOWN = 10

# A body line that looks like a message boundary is shown quoted, so text inside
# one message cannot pose as another message to the scout. No real message in
# the corpus has such a line; the injection test used one to forge a message.
FAKE_BOUNDARY = re.compile(r"^[ \t]*=+[ \t]*(MESSAGE|END OF)\b", re.MULTILINE)


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _recipients(field: str) -> str:
    addrs = [a.strip() for a in field.split(",") if a.strip()]
    shown = ", ".join(addrs[:MAX_RECIPIENTS_SHOWN])
    return shown + (f" (+{len(addrs) - MAX_RECIPIENTS_SHOWN} more)" if len(addrs) > MAX_RECIPIENTS_SHOWN else "")


def render_message(m: dict) -> str:
    date = f"{m['date']} UTC" if m["date"] else f"[no usable date: {m['date_issue']}; raw header: {m['date_raw']!r}]"
    lines = [
        f"===== MESSAGE {m['id']} =====",
        f"Date: {date}",
        f"From: {m['from']}",
        f"To: {_recipients(m['to'])}",
    ]
    if m["cc"]:
        lines.append(f"Cc: {_recipients(m['cc'])}")
    body = FAKE_BOUNDARY.sub(lambda b: "> " + b.group(0), m["body"].rstrip())
    lines += [f"Subject: {m['subject']}", "", body, "", ""]
    return "\n".join(lines)


def _sort_key(m: dict) -> tuple:
    # Undated messages sort after dated ones; path breaks ties deterministically.
    return (m["date"] is None, m["date"] or "", m["id"])


def group_by_subject(messages: list[dict]) -> list[list[dict]]:
    """Group messages by normalized subject; an empty subject is its own group."""
    groups = {}
    for m in messages:
        key = normalize_subject(m["subject"]) or f"__no_subject__{m['id']}"
        groups.setdefault(key, []).append(m)
    ordered = [sorted(g, key=_sort_key) for g in groups.values()]
    return sorted(ordered, key=lambda g: _sort_key(g[0]))


def _chunk_record(chunk_id: str, members: list[tuple[dict, str]], budget: int) -> dict:
    text = "".join(t for _, t in members)
    return {
        "id": chunk_id,
        "budget": budget,
        "message_ids": [m["id"] for m, _ in members],
        "est_tokens": estimate_tokens(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
    }


def build_chunks(messages: list[dict], budget: int = CHUNK_TOKEN_BUDGET,
                 previous: list[dict] = ()) -> list[dict]:
    """Pack messages into chunks, reusing ``previous`` chunks that still match.

    A previous chunk is kept, with its id, when it was packed under the same
    budget and every message in it still exists and renders to exactly the
    same text, so its scout output stays valid. Everything else (new messages,
    and messages from chunks that no longer match) is packed into new chunks
    numbered after the highest previous id; ids are never reused. A changed
    budget therefore repacks the whole corpus.
    """
    rendered = {m["id"]: render_message(m) for m in messages}
    kept, used = [], set()
    for prev in previous:
        if prev.get("budget") == budget and all(i in rendered and i not in used for i in prev["message_ids"]):
            record = _chunk_record(prev["id"], [({"id": i}, rendered[i]) for i in prev["message_ids"]], budget)
            if record["sha256"] == prev["sha256"]:
                kept.append(record)
                used.update(prev["message_ids"])

    start = 1 + max((int(p["id"].split("-")[1]) for p in previous), default=0)
    fresh = _pack([m for m in messages if m["id"] not in used], budget)
    return kept + [_chunk_record(f"chunk-{start + n:03d}", members, budget) for n, members in enumerate(fresh)]


def _pack(messages: list[dict], budget: int) -> list[list[tuple[dict, str]]]:
    """Greedily pack subject groups into chunks of at most ``budget`` tokens.

    A group too large for an empty chunk is split across consecutive chunks in
    date order; a single message over budget always ends up alone.
    """
    chunks, current, current_tokens = [], [], 0

    def flush():
        nonlocal current, current_tokens
        if current:
            chunks.append(current)
        current, current_tokens = [], 0

    for group in group_by_subject(messages):
        rendered = [(m, render_message(m)) for m in group]
        group_tokens = sum(estimate_tokens(t) for _, t in rendered)
        if current_tokens + group_tokens > budget:
            flush()
        for m, text in rendered:
            tokens = estimate_tokens(text)
            if current and current_tokens + tokens > budget:
                flush()
            current.append((m, text))
            current_tokens += tokens
    flush()
    return chunks
