"""Parse every message in the corpus and collapse duplicates.

Each message is identified by its original maildir path (e.g.
``farmer-d/logistics/1.``), which is what citations name. On Windows the files
are stored as ``1.eml`` (see scripts/extract_corpus.py); both layouts are read.
"""

from __future__ import annotations

import email
import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# Anything dated outside this window is treated as having no usable date.
EARLIEST = datetime(1995, 1, 1)
LATEST = datetime(2003, 12, 31)

SKIP_FILES = {"manifest.csv"}


def original_path(rel: str) -> str:
    """Map an on-disk relative path back to the maildir name it came from."""
    return rel[: -len(".eml")] + "." if rel.endswith(".eml") else rel


def message_id(file: str, messages: dict, copies: dict) -> str | None:
    """The id of the message a file names, as written relative to the corpus or the agents' folder."""
    rel = file.replace("\\", "/").strip()
    rel = rel.rsplit("corpus/", 1)[-1].removeprefix("./")
    for mid in (original_path(rel), rel, rel + "."):
        if mid in messages or mid in copies:
            return mid
    return None


def read_raw(corpus_dir: Path, msg_id: str) -> str:
    """Return the raw text of a message given its original path."""
    path = corpus_dir / msg_id
    if not path.exists():
        path = corpus_dir / (msg_id.rstrip(".") + ".eml")
    return path.read_bytes().decode("latin-1")


def parse_date(raw: str | None) -> tuple[str | None, str | None]:
    """Return (ISO timestamp in UTC, problem) for a Date header."""
    if not raw:
        return None, "missing"
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None, "unparseable"
    if dt is None:
        return None, "unparseable"
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    if not EARLIEST <= dt <= LATEST:
        return None, "out_of_range"
    return dt.isoformat(), None


def normalize_subject(subject: str) -> str:
    """Lowercase and strip any run of RE:/FW:/FWD: prefixes."""
    s = subject.strip().lower()
    s = re.sub(r"^((re|fw|fwd)\s*:\s*)+", "", s)
    return re.sub(r"\s+", " ", s).strip()


# Same-content messages count as one only if sent within this many hours.
# Re-exported copies in this archive are shifted by exactly 11 hours (a
# timezone bug in one export). Daily recurring mail, e.g. the same Calpine
# nomination text every morning, is 24+ hours apart and must stay separate.
DUPLICATE_WINDOW_HOURS = 12


def content_key(sender: str, subject: str, body: str) -> str:
    """Hash of the message content, ignoring layout.

    The same message exported twice can differ in line wrapping, tabs vs spaces
    and ``<Embedded ...>`` placeholders, so only letters and digits are kept.
    """
    body = re.sub(r"<Embedded [^>]*>", "", body)
    text = "\n".join([
        sender.lower(),
        normalize_subject(subject),
        re.sub(r"[^a-z0-9]", "", body.lower()),
    ])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _close_in_time(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return True
    gap = abs(datetime.fromisoformat(a) - datetime.fromisoformat(b))
    return gap.total_seconds() <= DUPLICATE_WINDOW_HOURS * 3600


def _text(part) -> str:
    # 54 messages are quoted-printable; undecoded, their lines end in "=" and
    # words are split ("as=\nsistant"), which no verbatim quote can match.
    if (part["Content-Transfer-Encoding"] or "").strip().lower() == "quoted-printable":
        return part.get_payload(decode=True).decode("latin-1")
    return part.get_payload()


def parse_message(msg_id: str, raw: str) -> dict:
    m = email.message_from_string(raw)
    if m.is_multipart():  # keep the text parts in order
        body = "\n".join(_text(p) for p in m.walk() if p.get_content_type() == "text/plain")
    else:
        body = _text(m)
    date, date_issue = parse_date(m["Date"])
    return {
        "id": msg_id,
        "mailbox": msg_id.split("/")[0],
        "message_id": (m["Message-ID"] or "").strip(),
        # The messages this one answers, where its mail client recorded them.
        "replies_to": re.findall(r"<[^<>\s]+>", f"{m['In-Reply-To'] or ''} {m['References'] or ''}"),
        "date": date,
        "date_raw": m["Date"],
        "date_issue": date_issue,
        "from": (m["From"] or "").strip(),
        "to": " ".join((m["To"] or "").split()),
        "cc": " ".join((m["Cc"] or "").split()),
        "subject": " ".join((m["Subject"] or "").split()),
        "body": body,
    }


def iter_corpus(corpus_dir: Path):
    """Yield (original_path, raw_text) for every message file, in sorted order."""
    # Hidden files, such as the .DS_Store macOS leaves in a folder, are not mail.
    files = [p for p in corpus_dir.rglob("*")
             if p.is_file() and p.name not in SKIP_FILES and not p.name.startswith(".")]
    for p in sorted(files, key=lambda p: p.relative_to(corpus_dir).as_posix()):
        yield original_path(p.relative_to(corpus_dir).as_posix()), p.read_bytes().decode("latin-1")


def dedupe(messages: list[dict]) -> list[dict]:
    """Collapse copies of the same message.

    Two messages are copies if they share a Message-ID, or have the same
    sender, subject and content (see ``content_key``) within
    ``DUPLICATE_WINDOW_HOURS`` of each other. The first message in path order
    is kept; the others are listed under ``duplicates`` so any of them can
    still be cited.
    """
    parent = list(range(len(messages)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    by_mid, by_content = {}, {}
    for i, m in enumerate(messages):
        if m["message_id"]:
            if m["message_id"] in by_mid:
                union(by_mid[m["message_id"]], i)
            else:
                by_mid[m["message_id"]] = i
        same = by_content.setdefault(content_key(m["from"], m["subject"], m["body"]), [])
        for j in same:
            if _close_in_time(messages[j]["date"], m["date"]):
                union(j, i)
        same.append(i)

    groups = {}
    for i in range(len(messages)):
        groups.setdefault(find(i), []).append(i)
    kept = []
    for root in sorted(groups):
        members = groups[root]
        keep = dict(messages[members[0]])
        keep["duplicates"] = [messages[j]["id"] for j in members[1:]]
        kept.append(keep)
    return kept


def ingest(corpus_dir: Path) -> tuple[list[dict], dict]:
    parsed = [parse_message(mid, raw) for mid, raw in iter_corpus(corpus_dir)]
    unique = dedupe(parsed)
    report = {
        "files_read": len(parsed),
        "unique_messages": len(unique),
        "duplicates_removed": len(parsed) - len(unique),
        "duplicate_groups": [[m["id"], *m["duplicates"]] for m in unique if m["duplicates"]],
        "date_issues": [
            {"id": m["id"], "issue": m["date_issue"], "raw": m["date_raw"]}
            for m in parsed
            if m["date_issue"]
        ],
    }
    return unique, report
