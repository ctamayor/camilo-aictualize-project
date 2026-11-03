"""Turn the estimates into ranked opportunities, in hours and dollars a month.

All of the arithmetic is here, none of it in a model. For each process:

- How often it happens. Counted: the times it happened (a message with the
  replies that quote it is one time) over the months of mail the archive holds
  for its mailboxes, since it holds only those months of those people's mail.
  For an episode (a migration, a cleanup), the times over every month, since it
  will not continue. For ongoing work, the gaps between its times over the
  months from its first time to its last: work that runs for four months of a
  mailbox's twenty did not stop for the other sixteen without a reason the
  count cannot see. Its n times mark n - 1 gaps, so a burst of three times in
  one month counts as two a month, not three, and the count still falls short
  rather than over. Stated: the rate the estimator read from a quote, as a count
  per working day, day, week, month or year, turned into a month here; used only
  if the words it gives for the rate are in one of the process's own quotes.
  The larger of the two is used, because most of the mail is not in the archive.
- A process that happened once in the archive is ranked only on a rate one of
  its own quotes states: one message can say that the work recurs, and then it
  is a flow like any other, but a count of one shows nothing recurring.
  Without a stated rate it is listed but not ranked.
- The minutes the change saves each time, from the estimator. An estimate whose
  basis names none of the process's quotes is not used, so the process is listed
  but not ranked; nor is one that saves no time.
- Hours a month = minutes x rate / 60, and dollars a month = hours x $85.

What it has cost so far is dollars a month x the calendar months from the
month it first shows in the mail to the last month its mailboxes hold. The
mail shows when the work was first written about, not when it began, so this
falls short rather than over.

Opportunities are ranked by dollars a month. The top ``DRAFT_TOP`` get a
drafted artifact. Every figure is stored rounded as it is shown, and the
totals add up the stored figures, so the dashboard's numbers agree.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .group import numbered_quotes
from .state import log, read_json, read_messages, write_json
from .validate import find_quote

HOURLY_RATE = 85
DRAFT_TOP = 10
# A stated rate is given as a count per unit, in the quote's own terms; a month
# is a twelfth of a year of 52 five-day weeks.
PER_MONTH = {"working day": 52 * 5 / 12, "day": 365 / 12, "week": 52 / 12, "month": 1, "year": 1 / 12}


def mailbox_months(messages: dict) -> dict:
    """For each mailbox: its messages, the months in which it has mail, and its first and last month."""
    months, counts = defaultdict(set), defaultdict(int)
    for m in messages.values():
        counts[m["mailbox"]] += 1
        if m["date"]:
            months[m["mailbox"]].add(m["date"][:7])
    return {box: {"messages": counts[box], "months": sorted(months[box])} for box in sorted(counts)}


def counted_rate(process: dict, messages: dict, boxes: dict, ongoing: bool) -> dict:
    mailboxes = sorted({messages[o["message"]]["mailbox"] for o in process["evidence"]["occurrences"]})
    held = set().union(*(boxes[b]["months"] for b in mailboxes)) if mailboxes else set()
    span = [process["first"][:7], process["last"][:7]] if ongoing and process.get("first") else None
    months = len([m for m in held if span[0] <= m <= span[1]] if span else held)
    per_month = (process["times"] - (1 if span else 0)) / months if months else 0
    return {"times": process["times"], "messages": process["occurrences"], "months": months,
            "mailboxes": mailboxes, "span": span, "per_month": round(per_month, 2)}


def months_between(first: str, last: str) -> int:
    """The calendar months from one "YYYY-MM" to another, both counted."""
    return (int(last[:4]) - int(first[:4])) * 12 + int(last[5:7]) - int(first[5:7]) + 1


def so_far(process: dict, counted: dict, boxes: dict, dollars: float) -> dict | None:
    if not process.get("first") or not counted["mailboxes"]:
        return None
    start, end = process["first"][:7], max(boxes[b]["months"][-1] for b in counted["mailboxes"])
    months = months_between(start, end)
    return {"from": start, "to": end, "months": months, "dollars": round(dollars * months, 2)}


def quote_id(ref: str, process: dict) -> str:
    """Restore a quote id an estimator wrote with its pattern in front ("chunk-005.p20.q32"),
    as it is laid out under its pattern in the prompt. Quote ids are unique within a
    process, so this is unambiguous."""
    m = re.fullmatch(r"(.+)\.(q\d+)", ref)
    return m[2] if m and m[1] in process["patterns"] else ref


def stated_rate(estimate: dict, process: dict, quotes: dict, problems: list) -> tuple[dict, dict | None]:
    """The rate the estimator read from a quote, and that quote, or None.

    The rate is used only if the words the estimator gave for it are in one of the
    process's quotes: the one it cited, or else the first that holds them, since a
    rate is shown with its quote as the evidence. The stored words are that quote's
    own span, so they can be marked in it."""
    given = estimate["stated_rate"]
    words = given.get("words", "")
    count, per = given.get("count", 0), given.get("per", "month")
    stated = {"per_month": round(count * PER_MONTH.get(per, 0), 2), "count": count, "per": per,
              "quote": quote_id(given["quote"], process), "words": ""}
    if stated["per_month"] <= 0:
        return stated, None
    if stated["quote"] not in quotes:
        problems.append(f"stated rate of {stated['per_month']:g} a month cites "
                        f"{stated['quote'] or 'no quote'}, which the process does not have")
    order = [stated["quote"]] * (stated["quote"] in quotes) + list(quotes)
    found = next(((q, span) for q in order if (span := find_quote(words, quotes[q]["quote"]))), None)
    if found is None:
        problems.append(f"stated rate of {stated['per_month']:g} a month is not used: " +
                        (f"the words given for it, “{words}”, are in none of the process's quotes" if words
                         else "no words saying how often were given for it"))
        return stated, None
    return stated | {"quote": found[0], "words": found[1]}, quotes[found[0]]


def score_process(process: dict, estimate: dict | None, messages: dict, boxes: dict) -> dict:
    quotes = numbered_quotes(process)
    opportunity = {"process": process["id"], "name": process["name"], "summary": process["summary"],
                   "rank": None, "problems": []}
    if estimate is None:
        return opportunity | {"unused": "no estimate was made for this process"}

    named = [quote_id(ref, process) for ref in estimate["basis"]]
    # A quote recorded twice (as an occurrence and an observation) is shown once.
    basis, seen = [], set()
    for qid in (q for q in named if q in quotes):
        if (key := (quotes[qid]["message"], quotes[qid]["quote"])) not in seen:
            seen.add(key)
            basis.append(qid)
    if any(q not in quotes for q in named):
        opportunity["problems"].append(f"basis names quotes the process does not have: "
                                       f"{', '.join(q for q in named if q not in quotes)}")
    stated, stated_quote = stated_rate(estimate, process, quotes, opportunity["problems"])

    opportunity |= {"change": estimate["change"], "explanation": estimate["explanation"],
                    "ongoing": estimate["ongoing"], "not_served": estimate["not_served"],
                    # A saved proposal has no reasoning: its quotes' notes carry the minutes.
                    "reasoning": estimate.get("reasoning"), "minutes": estimate["minutes"],
                    "basis": [quotes[qid] | {"id": qid} for qid in basis]}
    if not basis:
        return opportunity | {"unused": "the estimate names none of the process's quotes"}
    if process["times"] == 1 and not stated_quote:
        return opportunity | {"unused": "it happened once in the archive, and nothing in it says the work recurs"}
    if estimate["minutes"] <= 0:
        return opportunity | {"unused": "the change saves no time"}

    counted = counted_rate(process, messages, boxes, estimate["ongoing"])
    if stated_quote and stated["per_month"] > counted["per_month"]:
        rate = {"per_month": round(stated["per_month"], 2), "source": "stated"}
    else:
        rate = {"per_month": counted["per_month"], "source": "counted"}
    rate |= {"counted": counted,
             "stated": stated | {"quote": stated_quote | {"id": stated["quote"]}} if stated_quote else None}
    hours = round(estimate["minutes"] * rate["per_month"] / 60, 2)
    dollars = round(hours * HOURLY_RATE, 2)
    return opportunity | {"rate": rate, "hours_per_month": hours, "dollars_per_month": dollars,
                          "so_far": so_far(process, counted, boxes, dollars)}


def score(corpus_dir: Path, out_dir: Path) -> str:
    processes = read_json(out_dir / "processes.json")["processes"]
    messages = read_messages(out_dir)
    boxes = mailbox_months(messages)

    estimates, ignored = {}, 0
    known = {p["id"] for p in processes}
    for e in (e for path in sorted((out_dir / "estimates").glob("*.json")) for e in read_json(path)["estimates"]):
        if e["process"] in known and e["process"] not in estimates:
            estimates[e["process"]] = e
        else:
            ignored += 1

    scored = [score_process(p, estimates.get(p["id"]), messages, boxes) for p in processes]
    ranked = sorted((o for o in scored if "unused" not in o), key=lambda o: (-o["dollars_per_month"], o["process"]))
    for rank, o in enumerate(ranked, 1):
        o |= {"rank": rank, "draft": rank <= DRAFT_TOP and o["dollars_per_month"] > 0}
    unused = [o for o in scored if "unused" in o]
    opportunities = [{"id": f"opp-{i:02d}"} | o for i, o in enumerate(ranked + unused, 1)]

    totals = {
        "hourly_rate": HOURLY_RATE,
        "ranked": len(ranked),
        "unused": len(unused),
        "happened_once": sum(o["unused"].startswith("it happened once") for o in unused),
        "ranked_on_one_time": sum(o["rate"]["counted"]["times"] == 1 for o in ranked),
        "hours_per_month": round(sum(o["hours_per_month"] for o in ranked), 2),
        "dollars_per_month": round(sum(o["dollars_per_month"] for o in ranked), 2),
        "dollars_so_far": round(sum(o["so_far"]["dollars"] for o in ranked if o["so_far"]), 2),
        "drafted": sum(bool(o["draft"]) for o in ranked),
        "drafted_dollars_per_month": round(sum(o["dollars_per_month"] for o in ranked if o["draft"]), 2),
        "stated_rates_used": sum(o["rate"]["source"] == "stated" for o in ranked),
        "estimates_ignored": ignored,
    }
    write_json(out_dir / "opportunities.json", {"totals": totals, "mailboxes": boxes, "opportunities": opportunities})

    summary = (f"{len(ranked)} opportunities ranked, ${totals['dollars_per_month']:,.0f}/month "
               f"({totals['hours_per_month']:,.1f} hours) at ${HOURLY_RATE}/hour; top {totals['drafted']} "
               f"to draft (${totals['drafted_dollars_per_month']:,.0f}/month); {len(unused)} not ranked, "
               f"{ignored} estimates ignored")
    log(out_dir, f"score: {summary}")
    return summary
