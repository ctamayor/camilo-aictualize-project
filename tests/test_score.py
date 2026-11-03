import json
import tempfile
import unittest
from pathlib import Path

from pipeline.score import score
from pipeline.state import read_json
from tests.test_state import put

# Mailbox "a" has mail in four months, mailbox "b" in two (one shared with "a").
MONTHS = {"a": ["2001-01", "2001-02", "2001-03", "2001-04"], "b": ["2001-04", "2001-05"]}


def cite(box: str, n: int, quote: str, note: str | None = None) -> dict:
    c = {"message": f"{box}/inbox/{n}.", "quote": quote, "pattern": "chunk-001.p01"}
    return c if note is None else c | {"note": note}


def process(pid: str, occurrences: list, times: int | None = None, first="2001-01-03T09:00:00",
            last="2001-04-03T09:00:00") -> dict:
    return {"id": pid, "name": f"name {pid}", "summary": f"summary {pid}", "patterns": ["chunk-001.p01"],
            "occurrences": len(occurrences), "times": len(occurrences) if times is None else times,
            "first": first, "last": last, "evidence": {"occurrences": occurrences, "observations": []}}


def twice(pid: str) -> dict:
    return process(pid, [cite("a", 0, "x"), cite("a", 1, "y")])


def estimate(pid: str, minutes: float, basis=("q1",), stated=0, stated_quote="", words="", ongoing=False,
             per="month") -> dict:
    return {"process": pid, "change": f"change {pid}", "explanation": f"explanation {pid}", "not_served": [],
            "ongoing": ongoing, "basis": list(basis),
            "stated_rate": {"count": stated, "per": per, "quote": stated_quote, "words": words},
            "reasoning": "because", "minutes": minutes}


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        with open(self.out / "messages.jsonl", "w", encoding="utf-8") as fh:
            for box, months in MONTHS.items():
                for n, month in enumerate(months):
                    fh.write(json.dumps({"id": f"{box}/inbox/{n}.", "mailbox": box, "date": f"{month}-03T09:00:00"}) + "\n")
            fh.write(json.dumps({"id": "a/inbox/9.", "mailbox": "a", "date": None}) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_score(self, processes, estimates):
        put(self.out / "processes.json", {"processes": processes})
        put(self.out / "estimates" / "slice-01.json", {"estimates": estimates[:1]})
        put(self.out / "estimates" / "slice-02.json", {"estimates": estimates[1:]})
        score(None, self.out)
        doc = read_json(self.out / "opportunities.json")
        return doc, {o["process"]: o for o in doc["opportunities"]}

    def test_an_episodes_counted_rate_divides_its_times_by_the_months_its_mailboxes_have_mail(self):
        # Three times across mailboxes a and b, which have mail in five distinct months.
        p = process("proc-001", [cite("a", 0, "x"), cite("a", 1, "y"), cite("b", 1, "z")])
        _, opps = self.run_score([p], [estimate("proc-001", 30)])
        o = opps["proc-001"]
        self.assertEqual(o["rate"]["counted"], {"times": 3, "messages": 3, "months": 5, "mailboxes": ["a", "b"],
                                                "span": None, "per_month": 0.6})
        self.assertEqual(o["rate"]["source"], "counted")
        self.assertEqual((o["hours_per_month"], o["dollars_per_month"]), (0.3, 25.5))
        self.assertEqual((o["change"], o["explanation"]), ("change proc-001", "explanation proc-001"))

    def test_ongoing_work_counts_the_gaps_between_its_times_over_the_months_it_spans(self):
        # Four messages that are three times, from January to February: two of mailbox a's four months.
        p = process("proc-001", [cite("a", n, "x") for n in range(4)], times=3, last="2001-02-20T09:00:00")
        _, opps = self.run_score([p], [estimate("proc-001", 30, ongoing=True)])
        counted = opps["proc-001"]["rate"]["counted"]
        self.assertEqual((counted["times"], counted["messages"], counted["span"], counted["months"], counted["per_month"]),
                         (3, 4, ["2001-01", "2001-02"], 2, 1.0))

    def test_a_burst_in_one_month_is_not_a_monthly_rate_of_its_size(self):
        p = process("proc-001", [cite("a", n, "x") for n in range(3)], last="2001-01-20T09:00:00")
        _, opps = self.run_score([p], [estimate("proc-001", 30, ongoing=True)])
        self.assertEqual(opps["proc-001"]["rate"]["counted"]["per_month"], 2.0)

    def test_work_that_happened_once_is_ranked_only_on_a_rate_its_own_quote_states(self):
        # Two messages, but a reply and what it answers: one time each.
        stated = process("proc-001", [cite("a", 0, "it eats half my week, every week"), cite("a", 1, "y")], times=1)
        silent = process("proc-002", [cite("a", 2, "please approve this one"), cite("a", 3, "z")], times=1)
        doc, opps = self.run_score([stated, silent, twice("proc-003")],
                                   [estimate("proc-001", 300, stated=4.3, stated_quote="q1", words="every week", ongoing=True),
                                    estimate("proc-002", 30, ongoing=True), estimate("proc-003", 5)])
        self.assertEqual(opps["proc-001"]["rate"]["source"], "stated")
        self.assertEqual(opps["proc-001"]["hours_per_month"], 21.5)
        self.assertEqual(opps["proc-002"]["rank"], None)
        self.assertIn("happened once", opps["proc-002"]["unused"])
        self.assertEqual(opps["proc-002"]["change"], "change proc-002")
        totals = doc["totals"]
        self.assertEqual((totals["ranked"], totals["happened_once"], totals["ranked_on_one_time"]), (2, 1, 1))

    def test_a_quote_named_twice_in_the_basis_is_shown_once(self):
        p = process("proc-001", [cite("a", 0, "x"), cite("a", 1, "y")])
        p["evidence"]["observations"] = [cite("a", 0, "x", "Takes a while.")]
        _, opps = self.run_score([p], [estimate("proc-001", 5, basis=("q1", "q3", "q2"))])
        self.assertEqual([b["id"] for b in opps["proc-001"]["basis"]], ["q1", "q2"])
        self.assertEqual(opps["proc-001"]["problems"], [])

    def test_a_stated_rate_is_used_when_higher_and_its_quote_is_the_processs_own(self):
        p = process("proc-001", [cite("a", 0, "we do it every day"), cite("a", 1, "y")])
        _, opps = self.run_score([p], [estimate("proc-001", 10, stated=20, stated_quote="q1", words="Every Day")])
        o = opps["proc-001"]
        self.assertEqual((o["rate"]["source"], o["rate"]["per_month"]), ("stated", 20))
        self.assertEqual(o["rate"]["stated"]["quote"]["quote"], "we do it every day")
        # The words are stored as the quote has them, so they can be marked in it.
        self.assertEqual(o["rate"]["stated"]["words"], "every day")
        self.assertEqual((o["hours_per_month"], o["dollars_per_month"]), (3.33, 283.05))

    def test_a_stated_rate_whose_words_are_in_another_quote_cites_that_quote(self):
        p = process("proc-001", [cite("a", 0, "start at seven"), cite("a", 1, "we check out each night")])
        _, opps = self.run_score([p], [estimate("proc-001", 10, stated=21, stated_quote="q1", words="each night")])
        o = opps["proc-001"]
        self.assertEqual((o["rate"]["source"], o["rate"]["stated"]["quote"]["id"]), ("stated", "q2"))
        self.assertEqual(o["problems"], [])

    def test_a_stated_rate_whose_words_are_in_no_quote_is_not_used(self):
        p = process("proc-001", [cite("a", 0, "start at seven"), cite("a", 1, "y")])
        once = process("proc-002", [cite("a", 2, "the report for today")], times=1)
        _, opps = self.run_score([p, once], [estimate("proc-001", 10, stated=21, stated_quote="q1", words="every night"),
                                             estimate("proc-002", 10, stated=21, stated_quote="q1", words="daily")])
        o = opps["proc-001"]
        self.assertEqual((o["rate"]["source"], o["rate"]["stated"]), ("counted", None))
        self.assertIn("every night", o["problems"][0])
        self.assertIn("happened once", opps["proc-002"]["unused"])

    def test_a_stated_rate_given_without_its_words_is_not_used(self):
        e = estimate("proc-001", 10, stated=21, stated_quote="q1")
        del e["stated_rate"]["words"]
        _, opps = self.run_score([twice("proc-001")], [e])
        self.assertEqual(opps["proc-001"]["rate"]["source"], "counted")

    def test_a_stated_rate_lower_than_the_count_is_shown_but_not_used(self):
        p = process("proc-001", [cite("a", n, "x") for n in range(4)])
        _, opps = self.run_score([p], [estimate("proc-001", 60, stated=0.5, stated_quote="q2", words="x")])
        o = opps["proc-001"]
        self.assertEqual((o["rate"]["source"], o["rate"]["per_month"]), ("counted", 1.0))
        self.assertEqual(o["rate"]["stated"]["per_month"], 0.5)

    def test_a_stated_rate_citing_an_unknown_quote_is_ignored_and_reported(self):
        _, opps = self.run_score([twice("proc-001")], [estimate("proc-001", 60, stated=30, stated_quote="q7")])
        o = opps["proc-001"]
        self.assertEqual((o["rate"]["source"], o["rate"]["stated"]), ("counted", None))
        self.assertIn("q7", o["problems"][0])

    def test_a_quote_id_written_with_its_pattern_in_front_is_restored(self):
        _, opps = self.run_score([twice("proc-001")], [estimate("proc-001", 60, basis=["chunk-001.p01.q2", "chunk-009.p01.q1"],
                                                                stated=30, stated_quote="chunk-001.p01.q1", words="x")])
        o = opps["proc-001"]
        self.assertEqual(([b["id"] for b in o["basis"]], o["rate"]["stated"]["quote"]["id"]), (["q2"], "q1"))
        self.assertIn("chunk-009.p01.q1", o["problems"][0])

    def test_an_estimate_naming_none_of_its_quotes_is_not_ranked(self):
        doc, opps = self.run_score([twice("proc-001"), twice("proc-002")],
                                   [estimate("proc-001", 60, basis=["q9"]), estimate("proc-009", 5)])
        self.assertEqual(opps["proc-001"]["rank"], None)
        self.assertIn("names none", opps["proc-001"]["unused"])
        self.assertIn("no estimate", opps["proc-002"]["unused"])
        self.assertEqual((doc["totals"]["ranked"], doc["totals"]["unused"], doc["totals"]["estimates_ignored"]), (0, 2, 1))

    def test_ranked_by_dollars_with_the_top_ten_drafted(self):
        processes = [twice(f"proc-{i:03d}") for i in range(1, 13)]
        estimates = [estimate(p["id"], minutes) for p, minutes in zip(processes, [5, 60, 10, 20, 0, 1, 2, 3, 4, 6, 7, 8])]
        doc, _ = self.run_score(processes, estimates)
        ranked = doc["opportunities"]
        self.assertEqual([o["process"] for o in ranked[:3]], ["proc-002", "proc-004", "proc-003"])
        self.assertEqual([o["id"] for o in ranked[:2]], ["opp-01", "opp-02"])
        self.assertEqual(doc["totals"]["dollars_per_month"], round(sum(o["dollars_per_month"] for o in ranked[:-1]), 2))
        self.assertEqual([o["draft"] for o in ranked if o["rank"]], [True] * 10 + [False])
        self.assertEqual(ranked[-1]["unused"], "the change saves no time")
        self.assertEqual(doc["mailboxes"]["a"], {"messages": 5, "months": MONTHS["a"]})

    def test_the_cost_so_far_runs_from_its_first_month_in_the_mail_to_the_last_its_mailboxes_hold(self):
        # First in January 2001 in mailboxes a and b, whose mail ends in May 2001: five months.
        p = process("proc-001", [cite("a", 0, "x"), cite("b", 1, "y")])
        doc, opps = self.run_score([p, twice("proc-002")], [estimate("proc-001", 60), estimate("proc-002", 30)])
        o = opps["proc-001"]
        self.assertEqual(o["so_far"], {"from": "2001-01", "to": "2001-05", "months": 5,
                                       "dollars": round(o["dollars_per_month"] * 5, 2)})
        self.assertEqual(opps["proc-002"]["so_far"]["to"], "2001-04")
        self.assertEqual(doc["totals"]["dollars_so_far"], round(o["so_far"]["dollars"] + opps["proc-002"]["so_far"]["dollars"], 2))

    def test_an_opportunity_that_saves_nothing_is_not_ranked_or_drafted(self):
        processes = [twice("proc-001"), twice("proc-002")]
        doc, opps = self.run_score(processes, [estimate("proc-001", 5), estimate("proc-002", 0)])
        self.assertEqual((opps["proc-001"]["draft"], opps["proc-002"]["rank"]), (True, None))
        self.assertEqual((doc["totals"]["drafted"], doc["totals"]["ranked"]), (1, 1))

    def test_a_stated_rate_is_turned_into_a_month_from_the_unit_the_quote_uses(self):
        p = process("proc-001", [cite("a", 0, "we check them every working day"), cite("a", 1, "y")])
        _, opps = self.run_score([p], [estimate("proc-001", 6, stated=1, per="working day", stated_quote="q1",
                                                words="every working day")])
        stated = opps["proc-001"]["rate"]["stated"]
        self.assertEqual((stated["count"], stated["per"], stated["per_month"]), (1, "working day", 21.67))
        self.assertEqual(opps["proc-001"]["hours_per_month"], 2.17)


if __name__ == "__main__":
    unittest.main()
