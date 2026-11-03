"""The simpler architecture: analyst agents explore the mail and propose
opportunities, and critic agents check each one and save those that hold up.

Several analysts explore the whole archive at once, each in a session of its own,
and send each proposal, in their own words, to a critic. Only a critic can save:
it writes the proposal to a file and runs ``save`` on it. ``save`` is
deterministic. It checks every quote against its message, counts the times the
work happened from the messages given as occurrences, and computes hours and
dollars by the same rules as the scored pipeline (score.py), then rewrites the
files the dashboard reads. A proposal with any problem is not saved, and the
reasons are printed for the critic to act on. ``check`` does the same and shows
the hours and dollars without saving, so the critic can compare them with its own
before it saves. A critic that turns a proposal down
records why with ``reject``. Both rewrite ``decisions.md`` in the agents' folder,
which tells every analyst and critic what has been saved and rejected, so that
work is not proposed or saved twice and a rejection that more research could
overturn is not lost.

Each analyst and its critics work in a folder of their own that holds a copy of
the corpus, the folder proposals are written to, and ``leads.md``, the work the
readers noticed in every message (leads.py), so the only files they can read are
the archive's and those (not earlier runs, the code or its notes), and critics of
different analysts cannot overwrite each other's files. An analyst that ends its
session before the time is up is started again in a new one. The run is stopped after
``max_minutes``, and whatever was saved by then is the result. ``explore/done.json``
marks it finished, so a run that continues later does not explore again.
"""

import json
import re
import shutil
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from . import ROOT, agents
from .group import build_process, numbered_quotes
from .ingest import message_id, read_raw
from .leads import leads_markdown
from .score import PER_MONTH, mailbox_months, score, score_process
from .state import _try_lock, _unlock, explore_done, log, now, read_json, read_messages, write_json
from .validate import find_quote, message_text, normalize, parsed

EXPLORE_MINUTES = 20
ANALYSTS = 8
MIN_SESSION_S = 60
TASK = "Find the opportunities in the mail in `corpus`, and send each to the critic."
# The critic writes only proposals and runs only check, save and reject; reading is confined to the
# agents' folder by Claude Code itself.
ALLOWED = ["Read", "Grep", "Glob", "Agent", "Edit(proposals/**)", "Write(proposals/**)",
           "Bash(py -m pipeline save:*)", "Bash(python3 -m pipeline save:*)",
           "Bash(py -m pipeline reject:*)", "Bash(python3 -m pipeline reject:*)",
           "Bash(py -m pipeline check:*)", "Bash(python3 -m pipeline check:*)"]

# What save needs, shown to the critic when it asks or gets it wrong.
FORMAT = {
    "name": "the recurring work, in a few words",
    "today": "how the work is done today, enough to see what causes the cost",
    "change": "one line: what would change, for a manager deciding whether to read further",
    "explanation": "the change: what would be built or changed, who would use it, "
                   "and how the work would go afterwards",
    "occurrences": [{"file": "a message file in which the work happens", "quote": "the words of it that show the work"}],
    "evidence": [{"file": "a message file", "quote": "its exact words",
                  "note": "what they show about the time the work takes or what the change removes"}],
    "stalls": [{"file": "a message file", "quote": "its exact words", "note": "what is held up, and why"}],
    "ongoing": "true if the work continues as part of how the organization runs, false if it is an episode that ends",
    "stated_rate": "null, or {\"count\": a number, \"per\": one of " + ", ".join(PER_MONTH) +
                   ", \"file\": the message that says how often, \"quote\": its words that say it}",
    "minutes": "the minutes the change saves each time the work happens, counting everyone involved",
}
# What reject needs.
REJECTION = {
    "name": "the recurring work, in a few words, as the proposal named it",
    "change": "one line: the change it proposed",
    "reason": "what is wrong with it, in a sentence; the full explanation goes in your reply",
    "research": "null if more evidence would not change the verdict, or in a sentence what further research could settle it",
}
TEXT_FIELDS = ("name", "today", "change", "explanation")
CITATION_FIELDS = {"occurrences": ("file", "quote"), "evidence": ("file", "quote", "note"),
                   "stalls": ("file", "quote", "note")}


def shape_problems(data) -> list[str]:
    """What is missing or of the wrong kind in a proposal, before any quote is checked."""
    if not isinstance(data, dict):
        return ["the file does not hold one JSON object"]
    problems = [f"{k} is missing" for k in FORMAT if k not in data]
    problems += [f"{k} is not text" for k in TEXT_FIELDS if k in data and not (isinstance(data[k], str) and data[k].strip())]
    for kind, fields in CITATION_FIELDS.items():
        if kind in data and not (isinstance(data[kind], list) and all(
                isinstance(c, dict) and all(isinstance(c.get(f), str) for f in fields) for c in data[kind])):
            problems.append(f"{kind} is not a list of {{{', '.join(fields)}}}")
    for kind in ("occurrences", "evidence"):
        if isinstance(data.get(kind), list) and not data[kind]:
            problems.append(f"{kind} is empty")
    if "ongoing" in data and not isinstance(data["ongoing"], bool):
        problems.append("ongoing is not true or false")
    if "minutes" in data and (isinstance(data["minutes"], bool) or not isinstance(data["minutes"], (int, float))):
        problems.append("minutes is not a number")
    stated = data.get("stated_rate")
    if stated is not None and not (isinstance(stated, dict) and isinstance(stated.get("count"), (int, float))
                                   and stated.get("per") in PER_MONTH and isinstance(stated.get("file"), str)
                                   and isinstance(stated.get("quote"), str)):
        problems.append(f"stated_rate is not null or {{count, per ({', '.join(PER_MONTH)}), file, quote}}")
    return problems


class Checker:
    """Checks the citations of a proposal against the corpus."""

    def __init__(self, corpus_dir: Path, messages: dict):
        self.corpus_dir, self.messages = corpus_dir, messages
        self.copies = {d: m["id"] for m in messages.values() for d in m.get("duplicates", [])}
        self.text_of = message_text(parsed(corpus_dir))

    def cite(self, citation: dict) -> tuple[dict | None, str | None]:
        """(the citation as stored, None), or (None, why it fails)."""
        mid = message_id(citation["file"], self.messages, self.copies)
        if mid is None:
            return None, f"{citation['file']} is not a message file of the corpus"
        span = find_quote(citation["quote"], self.text_of(mid))
        if span is None:
            why = f"the quote “{citation['quote']}” is not in {citation['file']}"
            if find_quote(citation["quote"], normalize(read_raw(self.corpus_dir, mid))):
                why += (" as decoded: the file is quoted-printable encoded, so quote the words as they read "
                        "once its “=” line breaks and codes such as =20 are decoded")
            return None, why
        kept = {"message": self.copies.get(mid, mid), "quote": span}
        return kept | ({"note": citation["note"]} if "note" in citation else {}), None


def build(data: dict, n: int, checker: Checker, boxes: dict) -> tuple[dict, list[str], dict | None]:
    """The saved entry for a proposal (its pattern, process and estimate), its problems,
    and the opportunity as scored, once its citations hold."""
    problems, cited = [], {}
    for kind in CITATION_FIELDS:
        cited[kind] = []
        for i, c in enumerate(data[kind], 1):
            kept, why = checker.cite(c)
            if why:
                problems.append(f"{kind} {i}: {why}")
            else:
                cited[kind].append(kept)
    stated = data["stated_rate"] if data["stated_rate"] and data["stated_rate"]["count"] > 0 else None
    if stated:
        kept, why = checker.cite({"file": stated["file"], "quote": stated["quote"], "note": "says how often the work is done"})
        if why:
            problems.append(f"stated_rate: {why}")
            stated = None
        else:
            cited["evidence"].append(kept)
    if not cited["occurrences"] or not cited["evidence"]:
        return {}, problems or ["no occurrence or evidence holds"], None

    pid = f"saved-{n:02d}"
    pattern = {"id": pid, "chunk": "saved", "name": data["name"], "summary": data["today"],
               "occurrences": cited["occurrences"], "observations": cited["evidence"], "stalls": cited["stalls"]}
    process = {"id": f"proc-{n:03d}"} | build_process(data["name"], data["today"], [pid], {pid: pattern},
                                                     checker.messages)
    # The evidence is numbered after the occurrences (estimate.numbered_quotes); the
    # estimate names its quotes by those numbers, as an estimator's would.
    quotes = numbered_quotes(process)
    evidence_ids = {(c["message"], normalize(c["quote"])): qid for qid, c in quotes.items()
                    if any(c is o for o in process["evidence"]["observations"])}
    qid = lambda c: evidence_ids[(c["message"], normalize(c["quote"]))]
    basis = list(dict.fromkeys(qid(c) for c in cited["evidence"][:len(cited["evidence"]) - bool(stated)]))
    estimate = {"process": process["id"], "change": data["change"], "explanation": data["explanation"],
                "not_served": [], "ongoing": data["ongoing"],
                "stated_rate": {"count": stated["count"], "per": stated["per"], "quote": qid(cited["evidence"][-1]),
                                "words": cited["evidence"][-1]["quote"]} if stated
                else {"count": 0, "per": "month", "quote": "", "words": ""},
                "basis": basis, "minutes": data["minutes"]}
    scored = score_process(process, estimate, checker.messages, boxes)
    problems += scored["problems"] + ([scored["unused"]] if "unused" in scored else [])
    return {"pattern": pattern, "process": process, "estimate": estimate, "proposal": data}, problems, scored


@contextmanager
def _saving(out_dir: Path):
    """One save or rejection at a time, since critics run several at once."""
    with open(out_dir / "save.lock", "a+") as fh:
        while not _try_lock(fh):
            time.sleep(0.2)
        try:
            yield
        finally:
            _unlock(fh)


def _listing(out_dir: Path) -> str:
    """What has been saved, with the files it cites, and what has been rejected and why."""
    ranked = [o for o in (read_json(out_dir / "opportunities.json") or {}).get("opportunities", []) if o["rank"]]
    cites = {s["process"]["id"]: sorted({c["message"] + "eml" for kind in ("occurrences", "observations")
                                         for c in s["pattern"][kind]})
             for s in read_json(out_dir / "saved.json") or []}
    rejected = read_json(out_dir / "rejected.json") or []
    text = "# Saved\n\n" + ("".join(
        f"{o['rank']}. {o['name']}: {o['change']} (${o['dollars_per_month']:,.2f} a month). "
        f"Cites {', '.join(cites.get(o['process'], []))}\n" for o in ranked) or "Nothing yet.\n")
    text += "\n# Rejected\n\n" + ("".join(
        f"- {r['name']}: {r['change']}. Why: {r['reason']}"
        + (f" Research that could settle it: {r['research']}" if r["research"] else "") + "\n"
        for r in rejected) or "Nothing yet.\n")
    return text


def write_decisions(out_dir: Path) -> None:
    """decisions.md in every analyst's folder, for every analyst and critic to read. The
    commands do not print it: it grows with every decision, and each critic runs several."""
    text = _listing(out_dir)
    for workspace in (out_dir / "workspaces").glob("*"):
        (workspace / "decisions.md").write_text(text, encoding="utf-8")


# Given to the critic in its prompt, and again when a file is not in this form.
NEEDS = "Write the proposal as one JSON object with these fields:\n" + json.dumps(FORMAT, indent=2, ensure_ascii=False) + "\n"
REJECTION_NEEDS = ("Write the rejection as one JSON object with these fields:\n"
                   + json.dumps(REJECTION, indent=2, ensure_ascii=False) + "\n")


def _proposal(file: str) -> tuple[dict | None, list[str]]:
    """The proposal in ``file``, and what keeps it from being checked."""
    try:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, [f"{file} could not be read as JSON ({e})"]
    return data, shape_problems(data)


def _bullets(problems: list[str]) -> str:
    return "".join(f"- {p}\n" for p in problems)


def figures(o: dict) -> str:
    """How the hours and dollars of a scored opportunity were worked out."""
    r, c, s = o["rate"], o["rate"]["counted"], o["rate"]["stated"]
    over = (f"{c['times'] - 1} gaps between its {c['times']} times over the {c['months']} months from "
            f"{c['span'][0]} to {c['span'][1]}, since the work is ongoing" if c["span"] else
            f"{c['times']} times over the {c['months']} months of mail the archive holds for {', '.join(c['mailboxes'])}")
    text = (f"{o['minutes']:g} minutes x {r['per_month']:g} times a month = {o['hours_per_month']:g} hours "
            f"= ${o['dollars_per_month']:,.2f} a month.\n"
            f"How often, counted: {over} = {c['per_month']:g} a month. A message and the replies that "
            f"quote it are one time; the {c['messages']} occurrences given came to {c['times']} times.\n")
    if s:
        text += (f"How often, stated: {s['count']:g} a {s['per']} = {s['per_month']:g} a month. "
                 f"The {r['source']} rate is used, as the larger.\n")
    return text


def already_saved(entry: dict, saved: list[dict]) -> list[str]:
    """The same work saved before: half or more of a proposal's occurrences are
    occurrences of one saved opportunity. Two critics can both read decisions.md
    before either saves, so this is checked again when saving."""
    mine = {o["message"] for o in entry["process"]["evidence"]["occurrences"]}
    for s in saved:
        shared = mine & {o["message"] for o in s["process"]["evidence"]["occurrences"]}
        if len(shared) * 2 >= len(mine):
            return [f"{len(shared)} of its {len(mine)} occurrences are already occurrences of the saved "
                    f"“{s['process']['name']}”: the same work is not saved twice"]
    return []


def check(corpus_dir: Path, out_dir: Path, file: str | None) -> tuple[bool, str]:
    """Check the proposal in ``file`` as save would, and show its hours and dollars; save nothing."""
    if file is None:
        return False, NEEDS
    data, problems = _proposal(file)
    if problems:
        return False, "PROBLEMS:\n" + _bullets(problems) + "\n" + NEEDS
    messages = read_messages(out_dir)
    entry, problems, scored = build(data, 0, Checker(corpus_dir, messages), mailbox_months(messages))
    if entry:
        problems += already_saved(entry, read_json(out_dir / "saved.json") or [])
    if problems:
        return False, "PROBLEMS:\n" + _bullets(problems) + (
            "\nFrom the citations that hold: " + figures(scored) if scored and "rate" in scored else "")
    return True, "HOLDS UP (nothing saved): " + figures(scored)


def save(corpus_dir: Path, out_dir: Path, file: str | None) -> tuple[bool, str]:
    """Save the proposal in ``file`` if it holds; return whether it was saved, and what to tell the critic."""
    if file is None:
        return False, NEEDS
    data, problems = _proposal(file)
    if problems:
        return False, "NOT SAVED:\n" + _bullets(problems) + "\n" + NEEDS

    with _saving(out_dir):
        saved = read_json(out_dir / "saved.json") or []
        messages = read_messages(out_dir)
        boxes = mailbox_months(messages)
        entry, problems, _ = build(data, len(saved) + 1, Checker(corpus_dir, messages), boxes)
        if entry:
            problems += already_saved(entry, saved)
        if problems:
            return False, "NOT SAVED:\n" + _bullets(problems)
        saved.append(entry)
        write_json(out_dir / "saved.json", saved)
        write_json(out_dir / "validated.json", {"patterns": [s["pattern"] for s in saved]})
        write_json(out_dir / "estimates" / "saved.json", {"estimates": [s["estimate"] for s in saved]})
        write_json(out_dir / "processes.json", {"processes": [s["process"] for s in saved]})
        score(corpus_dir, out_dir)
        write_decisions(out_dir)
    o = next(o for o in read_json(out_dir / "opportunities.json")["opportunities"]
             if o["process"] == entry["process"]["id"])
    log(out_dir, f"save: {o['name']}: ${o['dollars_per_month']:,.2f} a month")
    return True, f"SAVED as {o['rank']} of {len(saved)} in decisions.md: " + figures(o)


def reject(out_dir: Path, file: str | None) -> tuple[bool, str]:
    """Record the rejection in ``file``; return whether it was recorded, and what to tell the critic."""
    needs = REJECTION_NEEDS
    if file is None:
        return False, needs
    try:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, f"NOT RECORDED: {file} could not be read as JSON ({e}).\n\n{needs}"
    if not isinstance(data, dict):
        problems = ["the file does not hold one JSON object"]
    else:
        text = lambda v: isinstance(v, str) and v.strip()
        problems = [f"{k} is missing" for k in REJECTION if k not in data]
        problems += [f"{k} is not text" for k in ("name", "change", "reason") if k in data and not text(data[k])]
        if "research" in data and data["research"] is not None and not text(data["research"]):
            problems.append("research is not null or text")
    if problems:
        return False, "NOT RECORDED:\n" + "".join(f"- {p}\n" for p in problems) + "\n" + needs
    with _saving(out_dir):
        rejected = read_json(out_dir / "rejected.json") or []
        rejected.append({k: data[k] for k in REJECTION} | {"time": now()})
        write_json(out_dir / "rejected.json", rejected)
        write_decisions(out_dir)
    log(out_dir, f"reject: {data['name']}")
    return True, "RECORDED in decisions.md."


MESSAGE_FILE = re.compile(r"([\w.-]+)[\\/]([\w.-]+)[\\/](\d+)\.eml")


def coverage(out_dir: Path) -> dict:
    """Which messages the agents looked at, read from the run's transcripts, one per analyst.

    A message is read if an agent opened its file, and glimpsed if a search showed
    lines of it without its file being opened; a search that only named or counted
    files shows nothing of them. The analysts' reading and the critics' are kept
    apart, since a critic reads to check a proposal, not to find one. Copies of
    one message count as that message."""
    messages = read_messages(out_dir)
    copies = {d: m["id"] for m in messages.values() for d in m.get("duplicates", [])}

    def ids(text: str) -> set[str]:
        found = (message_id("/".join(m.groups()) + ".eml", messages, copies) for m in MESSAGE_FILE.finditer(text))
        return {copies.get(i, i) for i in found if i}

    seen = {who: {"read": set(), "glimpsed": set()} for who in ("analysts", "critics")}
    by_analyst = []  # what each analyst opened itself
    for path in transcripts(out_dir):
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a run killed at its time can end mid-line
        uses = {}  # tool use id -> (whose, tool, input)
        for e in events:
            if e.get("type") == "assistant":
                whose = "critics" if e.get("parent_tool_use_id") else "analysts"
                for c in e["message"]["content"]:
                    if c["type"] == "tool_use":
                        uses[c["id"]] = (whose, c["name"], c["input"])
        opened = set()
        for e in events:
            content = e.get("message", {}).get("content") if e.get("type") == "user" else None
            for c in content if isinstance(content, list) else []:
                if c.get("type") != "tool_result" or c.get("is_error") or c["tool_use_id"] not in uses:
                    continue
                whose, tool, given = uses[c["tool_use_id"]]
                if tool == "Read":
                    got = ids(given.get("file_path", ""))
                    seen[whose]["read"] |= got
                    if whose == "analysts":
                        opened |= got
                elif tool == "Grep" and given.get("output_mode") == "content":
                    result = c["content"] if isinstance(c["content"], str) else \
                        " ".join(part.get("text", "") for part in c["content"])
                    seen[whose]["glimpsed"] |= ids(result)
        by_analyst.append(opened)
    read = seen["analysts"]["read"] | seen["critics"]["read"]
    glimpsed = seen["analysts"]["glimpsed"] | seen["critics"]["glimpsed"]
    boxes = sorted({m["mailbox"] for m in messages.values()})
    report = {
        "messages": len(messages),
        "read": len(read),
        "glimpsed_only": len(glimpsed - read),
        "analysts": {k: len(v) for k, v in seen["analysts"].items()},
        "critics": {k: len(v) for k, v in seen["critics"].items()},
        "read_by_each_analyst": [len(o) for o in by_analyst],
        "read_by_several_analysts": sum(n > 1 for n in Counter(i for o in by_analyst for i in o).values()),
        "mailboxes": {b: {"messages": sum(m["mailbox"] == b for m in messages.values()),
                          "read": sum(messages[i]["mailbox"] == b for i in read),
                          "glimpsed_only": sum(messages[i]["mailbox"] == b for i in glimpsed - read)}
                      for b in boxes},
        "read_ids": sorted(read),
        "glimpsed_ids": sorted(glimpsed - read),
    }
    write_json(out_dir / "coverage.json", report)
    return report


def coverage_line(report: dict) -> str:
    return (f"read {report['read']} of {report['messages']} messages (analysts {report['analysts']['read']}, "
            f"critics {report['critics']['read']}; {report['read_by_several_analysts']} by more than one analyst), "
            f"{report['glimpsed_only']} more seen only in search results")


def transcripts(out_dir: Path) -> list[Path]:
    return sorted((out_dir / "explore").glob("analyst-*.jsonl"), key=lambda p: int(p.stem.split("-")[1]))


def agent_definitions() -> dict:
    """The analyst and critic as Claude Code's --agents takes them, from their files. The
    critic is also given the forms its files take, from the definitions the code checks."""
    definitions = {}
    for name in ("analyst", "critic"):
        fields = agents.definition(name)
        definitions[name] = {k: fields[k] for k in ("description", "model", "effort", "prompt")} | {
            "tools": [t.strip() for t in fields["tools"].split(",")]}
    definitions["critic"]["prompt"] += "\n\n" + NEEDS + "\n" + REJECTION_NEEDS
    return definitions


def explore(corpus_dir: Path, out_dir: Path, max_minutes: float = EXPLORE_MINUTES, analysts: int = ANALYSTS) -> str:
    """Run ``analysts`` analysts at once until ``max_minutes`` pass; return the status line.
    The run holds the output folder's lock and has prepared the messages and the leads."""
    names = [f"analyst-{i}" for i in range(1, analysts + 1)]
    leads = leads_markdown(out_dir)
    for name in names:
        workspace = out_dir / "workspaces" / name
        if not (workspace / "corpus").exists():
            shutil.copytree(corpus_dir, workspace / "corpus")
        (workspace / "proposals").mkdir(parents=True, exist_ok=True)
        (workspace / "leads.md").write_text(leads, encoding="utf-8")
    write_decisions(out_dir)
    definitions = agent_definitions()
    write_json(out_dir / "agents.json", definitions)
    (out_dir / "explore").mkdir(exist_ok=True)
    log(out_dir, f"explore: started {analysts} analysts, stopping after {max_minutes:g} minutes")

    argv = [agents.CLAUDE, "-p", "--agents", str((out_dir / "agents.json").resolve()), "--agent", "analyst",
            # The analyst runs as the session itself, which takes its effort from the command line.
            "--effort", definitions["analyst"]["effort"], "--permission-mode", "dontAsk", "--setting-sources", "project", "--allowedTools", *ALLOWED,
            "--output-format", "stream-json", "--verbose"]
    env = {"PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8", "PIPELINE_OUT": str(out_dir.resolve())} | agents.ENV

    deadline = time.monotonic() + max_minutes * 60

    def one(name: str) -> tuple[str, int]:
        """Run one analyst until the time is up, in as many sessions as it takes."""
        transcript, sessions = [], 0
        while True:
            sessions += 1
            started, left = time.monotonic(), deadline - time.monotonic()
            try:
                proc = agents.call(argv, TASK, timeout=left, cwd=out_dir / "workspaces" / name, env=env)
                transcript.append(proc.stdout)
                ending, why = ("finished", "") if proc.returncode == 0 else                     ("failed", f": claude exited {proc.returncode}: {(proc.stderr or '').strip()[-300:]}")
            except subprocess.TimeoutExpired as e:
                transcript.append(e.output or "")
                ending, why = f"stopped after {max_minutes:g} minutes", ""
            except OSError as e:
                ending, why = "failed", f": could not start claude: {e}"
            # Headless, an analyst's last reply ends its session, however much is
            # left to find. A new session reads decisions.md and carries on; one that
            # ended at once, or with too little time left, is not started again.
            now_ = time.monotonic()
            if ending != "finished" or now_ - started < MIN_SESSION_S or deadline - now_ < MIN_SESSION_S:
                break
            log(out_dir, f"explore: {name} ended session {sessions} early; starting another")
        (out_dir / "explore" / f"{name}.jsonl").write_text("".join(transcript), encoding="utf-8")
        log(out_dir, f"explore: {name} {ending}{why} after {sessions} session{'s' * (sessions != 1)}")
        return ending, sessions

    with ThreadPoolExecutor(len(names)) as pool:
        results = list(pool.map(one, names))
    endings = Counter(e for e, _ in results)
    sessions = sum(n for _, n in results)
    ending = (f"{analysts} analyst{'s' * (analysts != 1)} in {sessions} session{'s' * (sessions != 1)}: "
              + ", ".join(f"{n} {e}" for e, n in endings.items()))

    totals = (read_json(out_dir / "opportunities.json") or {}).get("totals") or {}
    line = (f"{ending}; {totals.get('ranked', 0)} opportunities saved, "
            f"${totals.get('dollars_per_month', 0):,.0f} a month; {coverage_line(coverage(out_dir))}")
    log(out_dir, f"explore: {line}")
    write_json(explore_done(out_dir), {"ended": now(), "status": line})
    return line
