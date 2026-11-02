import unittest

from pipeline.estimate import estimate_prompt, numbered_quotes, slices


def cite(n: int, pattern: str, quote: str, note: str | None = None) -> dict:
    c = {"message": f"box/{n}.", "quote": quote, "pattern": pattern}
    return c if note is None else c | {"note": note}


PATTERNS = {
    "chunk-001.p01": {"name": "Daily report", "summary": "Kim sends the report."},
    "chunk-002.p03": {"name": "Report chase", "summary": "Raj asks for it."},
}
PROCESS = {
    "id": "proc-001", "name": "Daily report", "summary": "Kim sends the report every day.",
    "patterns": ["chunk-001.p01", "chunk-002.p03"],
    "senders": {"kim@enron.com": 3, "raj@enron.com": 1}, "recipients": {"team@enron.com": 4},
    "median_recipients": 2.5, "occurrences": 3, "times": 2,
    "first": "2001-03-01T09:00:00", "last": "2001-04-02T09:00:00", "months": {"2001-03": 1, "2001-04": 1},
    "evidence": {
        "occurrences": [cite(1, "chunk-001.p01", "Here is the report."),
                        cite(4, "chunk-002.p03", "Where is the report?"),
                        cite(2, "chunk-001.p01", "Report attached.")],
        "observations": [cite(1, "chunk-001.p01", "I build it by hand", "Built by hand each day.")],
        "stalls": [cite(4, "chunk-002.p03", "Still waiting on it", "Raj has to chase.")],
    },
}


class EstimatePromptTest(unittest.TestCase):
    def test_quotes_are_numbered_by_pattern_occurrences_first(self):
        quotes = numbered_quotes(PROCESS)
        self.assertEqual([(qid, c["quote"]) for qid, c in quotes.items()], [
            ("q1", "Here is the report."), ("q2", "Report attached."), ("q3", "I build it by hand"),
            ("q4", "Where is the report?"), ("q5", "Still waiting on it")])

    def test_each_process_shows_its_people_patterns_and_quotes(self):
        prompt = estimate_prompt([PROCESS], PATTERNS)
        self.assertTrue(prompt.startswith("1 processes follow. Estimate every one.\n\n## proc-001: Daily report\n"
                                          "Kim sends the report every day.\nHappened 2 times in the archive "
                                          "(3 messages, a reply counted with what it answers), "
                                          "between 2001-03-01 and 2001-04-02. Times begun each month: "
                                          "2001-03: 1, 2001-04: 1.\nMost often from"))
        self.assertIn("Most often from kim@enron.com (3), raj@enron.com (1); most often to team@enron.com (4); "
                      "a median of 2.5 addresses per message.", prompt)
        self.assertIn('\nPattern chunk-001.p01 | Daily report | Kim sends the report.\nq1: "Here is the report."\n'
                      'q2: "Report attached."\nq3: "I build it by hand" Reader\'s note: Built by hand each day.\n', prompt)
        self.assertIn('\nPattern chunk-002.p03 | Report chase | Raj asks for it.\nq4: "Where is the report?"\n'
                      'q5: Stall: "Still waiting on it" Reader\'s note: Raj has to chase.', prompt)
        self.assertNotIn("box/1.", prompt)
        self.assertNotIn("for scale only", prompt)

    def test_each_estimator_gets_a_slice_spanning_every_size_and_sees_the_rest_for_scale(self):
        processes = [PROCESS | {"id": f"proc-{i:03d}", "name": f"Work {i}"} for i in range(1, 42)]
        parts = slices(processes)
        self.assertEqual([len(p) for p in parts], [14, 14, 13])
        self.assertEqual(parts[0][:3], ["proc-001", "proc-004", "proc-007"])
        prompt = estimate_prompt(processes, PATTERNS, parts[1])
        self.assertTrue(prompt.startswith("14 processes follow. Estimate every one.\n\n## proc-002: Work 2\n"))
        self.assertIn("# The other 27 processes, estimated by others: for scale only\n\n"
                      "proc-001: Work 1 (2 times). Kim sends the report every day.\n", prompt)
        self.assertNotIn("## proc-001", prompt)


if __name__ == "__main__":
    unittest.main()
