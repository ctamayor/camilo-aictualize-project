import unittest

from pipeline import schemas
from pipeline.draft import drafter_tasks, finalize
from pipeline.state import draft_paths, read_json
from tests.test_explore import SaveTest, proposal
from tests.test_state import put


class DraftTest(unittest.TestCase):
    # The mail and the saving of a proposal are SaveTest's; its tests are not run again here.
    tearDown, save = SaveTest.tearDown, SaveTest.save

    def setUp(self):
        SaveTest.setUp(self)
        self.save(proposal())
        self.opportunity = read_json(self.out / "opportunities.json")["opportunities"][0]

    def test_a_drafter_is_given_the_analysis_and_no_message_beyond_its_quotes(self):
        [task] = drafter_tasks(self.out, [self.opportunity])
        self.assertEqual((task.name, task.agent, task.schema, task.output),
                         ("opp-01", "drafter", schemas.DRAFT, draft_paths(self.out, self.opportunity)[0]))
        for text in ("Opportunity 1: Daily schedule", "How the work is done today: Sent by hand each day",
                     "The change: Send it automatically", "A report is generated and mailed.",
                     "30 minutes x 2 times a month", "2000-03-06, a@enron.com: “I rebuild it from three sheets” (manual work)",
                     "Who sends them, with how many: a@enron.com (2)"):
            self.assertIn(text, task.prompt)
        # Text of a cited message that no quote holds is not given.
        self.assertNotIn("Hi,", task.prompt)

    def test_finalize_writes_each_draft_and_the_report(self):
        put(draft_paths(self.out, self.opportunity)[0],
            {"kind": "Email", "audience": "the scheduling team", "title": "Send the schedule automatically", "body": "Please.\n"})
        self.assertIn("1 drafted", finalize(self.corpus, self.out))
        page = draft_paths(self.out, self.opportunity)[1].read_text(encoding="utf-8")
        self.assertEqual(page, "# Send the schedule automatically\n\n*Email, drafted for opportunity 1: Daily schedule, "
                               "$85 a month.*\n\n**For:** the scheduling team\n\n---\n\nPlease.\n")
        report = read_json(self.out / "report.json")
        self.assertEqual((list(report["drafts"]), report["totals"]["ranked"]), (["opp-01"], 1))


if __name__ == "__main__":
    unittest.main()
