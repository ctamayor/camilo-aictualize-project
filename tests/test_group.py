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

    def test_replies_that_quote_a_message_are_the_same_time(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)
        mail = [(1, "Meter 5", "Please fix meter 5."), (2, "RE: Meter 5", "Done.\n> Please fix meter 5."),
                (3, "Meter 5", "Please fix meter 5."), (4, "RE: Meter 5", "Fixed.\n\nPlease fix\nmeter 5."),
                (5, "Lunch", "Please fix meter 5. Pizza?")]
        with open(out / "messages.jsonl", "w", encoding="utf-8") as fh:
            for n, subject, body in mail:
                fh.write(json.dumps({"id": f"box/{n}.", "date": f"2001-03-0{n}T09:00:00", "from": "kim@enron.com",
                                     "to": "", "cc": "", "subject": subject, "body": body}) + "\n")
        stall = cite(2, "Done.", "Fixed only after a chase.")
        put(out / "validated.json", {"patterns": [
            pattern("chunk-001.p01", [cite(n) for n in range(1, 6)]) | {"stalls": [stall]}]})
        put(merge_paths(out)[1], {"processes": []})
        group(None, out)
        p = read_json(out / "processes.json")["processes"][0]
        self.assertEqual([o["time"] for o in p["evidence"]["occurrences"]], [1, 1, 2, 2, 3])
        self.assertEqual((p["occurrences"], p["times"]), (5, 3))
        self.assertEqual(p["evidence"]["stalls"][0]["note"], "Fixed only after a chase.")


if __name__ == "__main__":
    unittest.main()
