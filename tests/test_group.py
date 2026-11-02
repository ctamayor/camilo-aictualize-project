import json
import tempfile
import unittest
from pathlib import Path

from pipeline.group import group
from pipeline.state import merge_paths, read_json
from tests.test_state import put


def cite(n: int, quote: str = "q", note: str | None = None) -> dict:
    c = {"message": f"box/{n}.", "quote": quote}
    return c if note is None else c | {"note": note}


def pattern(pid: str, occurrences: list, observations: list = ()) -> dict:
    return {"id": pid, "chunk": pid.split(".")[0], "name": f"name {pid}", "summary": f"summary {pid}",
            "occurrences": occurrences, "observations": list(observations)}


class GroupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        dates = {1: "2001-03-01T09:00:00", 2: "2001-03-02T09:00:00", 4: "2001-04-02T09:00:00",
                 5: None, 6: "2001-04-09T09:00:00"}
        with open(self.out / "messages.jsonl", "w", encoding="utf-8") as fh:
            for n, date in dates.items():
                sender = "kim@enron.com" if n != 4 else "raj@enron.com"
                fh.write(json.dumps({"id": f"box/{n}.", "date": date, "from": sender,
                                     "to": "team@enron.com, Raj@enron.com", "cc": ""}) + "\n")
        put(self.out / "validated.json", {"patterns": [
            pattern("chunk-001.p01", [cite(1), cite(2)], [cite(1, "late again", "Late.")]),
            pattern("chunk-002.p01", [cite(2), cite(4)], [cite(1, "late  again", "Late."), cite(4, "redo it", "Redone.")]),
            pattern("chunk-003.p01", [cite(6)]),
            pattern("chunk-002.p02", [cite(5)]),
        ]})
        put(merge_paths(self.out)[1], {"processes": [
            {"name": "Daily report", "summary": "Kim collects numbers.",
             "patterns": ["chunk-001.p01", "chunk-002.p01", "chunk-003.p01", "chunk-009.p99"]},
            {"name": "Again", "summary": "Listed twice.", "patterns": ["chunk-001.p01"]},
        ]})
        group(None, self.out)
        self.result = read_json(self.out / "processes.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_merged_patterns_become_one_process_counted_from_citations(self):
        daily, alone = self.result["processes"]
        self.assertEqual((daily["id"], daily["name"], daily["occurrences"]), ("proc-001", "Daily report", 4))
        self.assertEqual(daily["chunks"], ["chunk-001", "chunk-002", "chunk-003"])
        self.assertEqual([o["quote"] for o in daily["evidence"]["observations"]], ["late again", "redo it"])
        self.assertEqual(daily["months"], {"2001-03": 2, "2001-04": 2})
        self.assertEqual((daily["first"], daily["last"]), ("2001-03-01T09:00:00", "2001-04-09T09:00:00"))
        self.assertEqual(daily["senders"], {"kim@enron.com": 3, "raj@enron.com": 1})
        self.assertEqual(daily["recipients"], {"raj@enron.com": 4, "team@enron.com": 4})
        self.assertEqual(daily["median_recipients"], 2)
        self.assertEqual([o["pattern"] for o in daily["evidence"]["occurrences"]],
                         ["chunk-001.p01", "chunk-001.p01", "chunk-002.p01", "chunk-003.p01"])

    def test_unlisted_pattern_stays_its_own_process(self):
        alone = self.result["processes"][1]
        self.assertEqual((alone["id"], alone["name"], alone["patterns"]), ("proc-002", "name chunk-002.p02", ["chunk-002.p02"]))
        self.assertEqual((alone["occurrences"], alone["first"], alone["months"]), (1, None, {}))

    def test_stats_measure_whether_one_message_patterns_recur(self):
        self.assertEqual(self.result["stats"], {
            "patterns": 4, "processes": 2, "merged": 1,
            "one_message_patterns": 2, "one_message_patterns_recurring": 1, "one_message_processes": 1,
            "one_time_processes": 1, "messages": 5, "times": 5,
            "merge_problems": {"unknown pattern id": 1, "pattern listed twice": 1},
        })


class TimesTest(unittest.TestCase):
    """A message and the replies that quote it are one time; a new message with the same subject is another."""

    def test_replies_forwards_and_copies_are_the_same_time_and_new_mail_is_a_new_one(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)
        header = "\n-----Original Message-----\nFrom: Kim\nSent: Thursday, March 01, 2001 9:00 AM\n"
        mail = [
            ("03-01T09", "kim", "Meter 5", "Please fix meter 5."),
            ("03-01T11", "raj", "RE: Meter 5", "Done." + header + "Please fix meter 5."),  # quotes 1
            ("03-05T09", "kim", "Meter 5", "Please fix meter 5."),                          # asked again
            ("03-05T10", "raj", "RE: Meter 5", "Fixed."),                                   # bare Notes reply to 3
            ("03-05T12", "kim", "Lunch", "Please fix meter 5. Pizza?"),                    # another subject
            ("03-06T08", "kim", "Nomination", "- NOMINATION 1.doc"),                       # daily mail
            ("03-07T08", "kim", "Nomination", "- NOMINATION 1.doc\nRevised volumes"),     # next day's
            ("03-08T09", "kim", "RE: Report", "Agree.\n> The report is late."),            # two replies to one
            ("03-08T13", "raj", "RE: Report", "Disagree.\n> The report is late."),         # message not cited
            ("03-09T09", "ops", "Notice", "All hands at noon."),                           # one broadcast
            ("03-09T12", "hr", "Notice", "All hands at noon."),                            # and its copy
        ]
        with open(out / "messages.jsonl", "w", encoding="utf-8") as fh:
            for n, (date, sender, subject, body) in enumerate(mail, 1):
                fh.write(json.dumps({"id": f"box/{n}.", "date": f"2001-{date}:00:00", "from": f"{sender}@enron.com",
                                     "to": "", "cc": "", "subject": subject, "body": body}) + "\n")
        stall = cite(2, "Done.", "Fixed only after a chase.")
        put(out / "validated.json", {"patterns": [
            pattern("chunk-001.p01", [cite(n) for n in range(1, len(mail) + 1)]) | {"stalls": [stall]}]})
        put(merge_paths(out)[1], {"processes": []})
        group(None, out)
        p = read_json(out / "processes.json")["processes"][0]
        self.assertEqual([o["time"] for o in p["evidence"]["occurrences"]], [1, 1, 2, 2, 3, 4, 5, 6, 6, 7, 7])
        self.assertEqual((p["occurrences"], p["times"], p["months"]), (11, 7, {"2001-03": 7}))
        self.assertEqual(p["evidence"]["stalls"][0]["note"], "Fixed only after a chase.")


if __name__ == "__main__":
    unittest.main()
