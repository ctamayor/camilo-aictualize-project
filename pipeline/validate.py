"""How a quote is checked against its message.

A quote holds only if it appears in the message as parsed from its raw file
(headers and decoded body). Quotes are compared after collapsing whitespace,
straightening quote characters, dropping control characters and removing the
">" markers at the start of quoted reply lines (an agent may write line breaks as
spaces and skip the markers, and cannot write a stray control byte), and ignoring
case. A quote that holds is stored as the message's own text, so what is shown is
verbatim.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .ingest import parse_message, read_raw

# Quote characters straightened, and control characters that are not whitespace dropped.
QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}
                            | dict.fromkeys(map(chr, [*range(0x00, 0x09), *range(0x0e, 0x1c), 0x7f])))
REPLY_MARKERS = re.compile(r"^[ \t]*(?:>[ \t]*)+", re.MULTILINE)


def normalize(text: str) -> str:
    return " ".join(REPLY_MARKERS.sub("", text).translate(QUOTE_CHARS).split())


def find_quote(quote: str, text: str) -> str | None:
    """Return the span of normalized ``text`` matching ``quote`` ignoring case, or None."""
    q = normalize(quote)
    m = re.search(re.escape(q), text, re.IGNORECASE) if q else None
    return m[0] if m else None


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
