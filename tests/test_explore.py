import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import agents, explore
from pipeline.__main__ import prepare
from pipeline.ingest import message_id
from pipeline.state import explore_done, read_json
from tests.test_state import put, write_message


def proposal(**fields) -> dict:
    return {"name": "Daily schedule", "today": "Sent by hand each day", "change": "Send it automatically",
            "explanation": "A report is generated and mailed.",
            "occurrences": [{"file": "corpus/box/inbox/0.eml", "quote": "please find the schedule"},
                            {"file": "box/inbox/1.eml", "quote": "updated volumes"}],
            "evidence": [{"file": "box/inbox/0.", "quote": "I rebuild it from three sheets", "note": "manual work"}],
            "ongoing": False, "stated_rate": None, "minutes": 30} | fields


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.tmp.name) / "corpus"
        self.out = Path(self.tmp.name) / "out"
        write_message(self.corpus, "0.eml", "Schedule", "Hi, please find the schedule.\nI rebuild it from three sheets.")
        write_message(self.corpus, "1.eml", "Volumes", "Here are the updated volumes. We send these every day.")
        write_message(self.corpus, "2.eml", "Invoices", "The invoices are keyed in by hand.")
        write_message(self.corpus, "3.eml", "Invoices", "More invoices to key in.")
        prepare(self.corpus, self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, data) -> tuple[bool, str]:
        put(self.out / "workspaces" / "analyst-1" / "proposals" / "p.json", data)
        return explore.save(self.corpus, self.out, str(self.out / "workspaces" / "analyst-1" / "proposals" / "p.json"))

    def test_a_proposal_that_holds_is_scored_like_the_pipeline(self):
        saved, text = self.save(proposal())
        self.assertTrue(saved, text)
        o = read_json(self.out / "opportunities.json")["opportunities"][0]
        # Two times in the one month of mail the mailbox holds; 30 min x 2 / 60 = 1 hour.
        self.assertEqual((o["rank"], o["rate"]["per_month"], o["hours_per_month"], o["dollars_per_month"]),
                         (1, 2.0, 1.0, 85.0))
        self.assertEqual(o["basis"][0]["message"], "box/inbox/0.")
        self.assertIn("SAVED as 1 of 1 in decisions.md: 30 minutes x 2 times a month", text)
        self.assertIn("1. Daily schedule", (self.out / "workspaces" / "analyst-1" / "decisions.md").read_text(encoding="utf-8"))

    def test_check_shows_how_the_figures_were_worked_out_and_saves_nothing(self):
        put(self.out / "workspaces" / "analyst-1" / "proposals" / "p.json", proposal())
        held, text = explore.check(self.corpus, self.out, str(self.out / "workspaces" / "analyst-1" / "proposals" / "p.json"))
        self.assertTrue(held, text)
        self.assertIn("HOLDS UP (nothing saved): 30 minutes x 2 times a month = 1 hours = $85.00 a month.", text)
        self.assertIn("How often, counted: 2 times over the 1 months of mail the archive holds for box", text)
        self.assertFalse((self.out / "saved.json").exists())

    def test_check_names_the_problems_and_the_figures_from_what_holds(self):
        evidence = [{"file": "box/inbox/0.eml", "quote": "I rebuild it from three sheets", "note": "manual work"},
                    {"file": "box/inbox/0.eml", "quote": "not there", "note": "x"}]
        put(self.out / "workspaces" / "analyst-1" / "proposals" / "p.json", proposal(evidence=evidence))
        held, text = explore.check(self.corpus, self.out, str(self.out / "workspaces" / "analyst-1" / "proposals" / "p.json"))
        self.assertFalse(held)
        self.assertIn("evidence 2: the quote “not there” is not in box/inbox/0.eml", text)
        self.assertIn("From the citations that hold: 30 minutes x 2 times a month", text)

    def test_a_quote_not_in_its_message_stops_the_save(self):
        saved, text = self.save(proposal(evidence=[{"file": "box/inbox/0.eml", "quote": "not there", "note": "x"}]))
        self.assertFalse(saved)
        self.assertIn("evidence 1: the quote “not there” is not in box/inbox/0.eml", text)
        self.assertFalse((self.out / "saved.json").exists())

    def test_an_unknown_file_stops_the_save(self):
        saved, text = self.save(proposal(occurrences=[{"file": "box/inbox/7.eml", "quote": "x"}]))
        self.assertFalse(saved)
        self.assertIn("box/inbox/7.eml is not a message file", text)

    def test_work_seen_once_needs_a_stated_rate(self):
        once = [{"file": "box/inbox/0.eml", "quote": "please find the schedule"}]
        saved, text = self.save(proposal(occurrences=once))
        self.assertFalse(saved)
        self.assertIn("happened once", text)
        stated = {"count": 1, "per": "working day", "file": "box/inbox/1.eml", "quote": "We send these every day"}
        saved, text = self.save(proposal(occurrences=once, stated_rate=stated))
        self.assertTrue(saved, text)
        o = read_json(self.out / "opportunities.json")["opportunities"][0]
        self.assertEqual((o["rate"]["source"], o["rate"]["per_month"]), ("stated", 21.67))
        self.assertEqual(o["rate"]["stated"]["words"], "We send these every day")

    def test_a_malformed_proposal_is_told_the_format(self):
        saved, text = self.save({"name": "x", "minutes": "ten"})
        self.assertFalse(saved)
        self.assertIn("today is missing", text)
        self.assertIn("minutes is not a number", text)
        self.assertIn('"stated_rate"', text)

    def test_without_a_file_it_says_what_it_needs(self):
        saved, text = explore.save(self.corpus, self.out, None)
        self.assertFalse(saved)
        self.assertEqual(text, explore.NEEDS)

    def test_a_rejection_is_recorded_for_every_agent_to_read(self):
        self.save(proposal())
        put(self.out / "workspaces" / "analyst-1" / "proposals" / "r.json",
            {"name": "Volumes", "change": "Send them automatically", "reason": "The count is of copies.",
             "research": "A message saying how often they are sent."})
        recorded, text = explore.reject(self.out, str(self.out / "workspaces" / "analyst-1" / "proposals" / "r.json"))
        self.assertTrue(recorded, text)
        decisions = (self.out / "workspaces" / "analyst-1" / "decisions.md").read_text(encoding="utf-8")
        self.assertEqual(text, "RECORDED in decisions.md.")
        self.assertIn("1. Daily schedule: Send it automatically ($85.00 a month). Cites box/inbox/0.eml, box/inbox/1.eml",
                      decisions)
        self.assertIn("- Volumes: Send them automatically. Why: The count is of copies. "
                      "Research that could settle it: A message saying how often they are sent.", decisions)

    def test_a_malformed_rejection_is_told_the_format(self):
        put(self.out / "workspaces" / "analyst-1" / "proposals" / "r.json", {"name": "x", "research": ""})
        recorded, text = explore.reject(self.out, str(self.out / "workspaces" / "analyst-1" / "proposals" / "r.json"))
        self.assertFalse(recorded)
        self.assertIn("reason is missing", text)
        self.assertIn("research is not null or text", text)
        self.assertFalse((self.out / "rejected.json").exists())

    def test_the_same_work_is_not_saved_twice(self):
        self.save(proposal())
        saved, text = self.save(proposal(name="Schedule again", minutes=45))
        self.assertFalse(saved)
        self.assertIn("2 of its 2 occurrences are already occurrences of the saved “Daily schedule”", text)
        put(self.out / "workspaces" / "analyst-1" / "proposals" / "q.json", proposal(name="Schedule again"))
        held, text = explore.check(self.corpus, self.out, str(self.out / "workspaces" / "analyst-1" / "proposals" / "q.json"))
        self.assertFalse(held)
        self.assertIn("the same work is not saved twice", text)

    def test_saves_add_up(self):
        self.save(proposal())
        invoices = [{"file": "box/inbox/2.eml", "quote": "The invoices are keyed in by hand"},
                    {"file": "box/inbox/3.eml", "quote": "More invoices to key in"}]
        self.save(proposal(name="Second", minutes=60, occurrences=invoices))
        doc = read_json(self.out / "opportunities.json")
        self.assertEqual([o["name"] for o in doc["opportunities"]], ["Second", "Daily schedule"])
        self.assertEqual(doc["totals"]["dollars_per_month"], 255.0)


class ExploreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.tmp.name) / "corpus"
        self.out = Path(self.tmp.name) / "out"
        write_message(self.corpus, "0.eml", "Schedule", "please find the schedule")

    def tearDown(self):
        self.tmp.cleanup()

    def explore(self, minutes, analysts):
        """Explore as a run does, once the mail is prepared."""
        prepare(self.corpus, self.out)
        return explore.explore(self.corpus, self.out, minutes, analysts=analysts)

    def test_the_analysts_run_in_their_own_folder_with_a_copy_of_the_corpus(self):
        done = subprocess.CompletedProcess([], 0, '{"type":"result"}\n', "")
        with mock.patch.object(agents, "call", return_value=done) as call:
            line = self.explore(1, 2)
        self.assertEqual(call.call_count, 2)
        argv, kwargs = call.call_args.args[0], call.call_args.kwargs
        self.assertEqual(argv[argv.index("--agent") + 1], "analyst")
        # Each agent runs at the effort its file in .claude/agents gives it.
        definitions = read_json(self.out / "agents.json")
        self.assertEqual(argv[argv.index("--effort") + 1], definitions["analyst"]["effort"])
        self.assertIn(definitions["critic"]["effort"], ("low", "medium", "high", "xhigh", "max"))
        self.assertEqual({c.kwargs["cwd"] for c in call.call_args_list},
                         {self.out / "workspaces" / "analyst-1", self.out / "workspaces" / "analyst-2"})
        self.assertAlmostEqual(kwargs["timeout"], 60, delta=1)
        for name in ("analyst-1", "analyst-2"):
            self.assertTrue((self.out / "workspaces" / name / "corpus" / "box" / "inbox" / "0.eml").exists())
            self.assertIn("Nothing yet", (self.out / "workspaces" / name / "decisions.md").read_text(encoding="utf-8"))
            self.assertTrue((self.out / "workspaces" / name / "leads.md").read_text(encoding="utf-8").startswith("# Leads"))
        self.assertTrue(line.startswith("2 analysts in 2 sessions: 2 finished; 0 opportunities saved"))
        self.assertEqual(read_json(explore_done(self.out))["status"], line)
        for name in ("analyst-1", "analyst-2"):
            self.assertEqual((self.out / "explore" / f"{name}.jsonl").read_text(encoding="utf-8"), '{"type":"result"}\n')

    def test_a_run_stopped_at_its_time_keeps_what_was_written(self):
        stopped = subprocess.TimeoutExpired("claude", 60, output="partial\n")
        with mock.patch.object(agents, "call", side_effect=stopped):
            line = self.explore(1, 1)
        self.assertTrue(line.startswith("1 analyst in 1 session: 1 stopped after 1 minutes"))
        self.assertEqual((self.out / "explore" / "analyst-1.jsonl").read_text(encoding="utf-8"), "partial\n")

    def test_an_analyst_that_ends_early_is_started_again_until_the_time_is_up(self):
        done = subprocess.CompletedProcess([], 0, '{"type":"result"}\n', "")
        stopped = subprocess.TimeoutExpired("claude", 60, output="last\n")
        # Sessions here end at once, so any session counts as long enough.
        with mock.patch.object(explore, "MIN_SESSION_S", 0), \
                mock.patch.object(agents, "call", side_effect=[done, done, stopped]) as call:
            line = self.explore(1, 1)
        timeouts = [c.kwargs["timeout"] for c in call.call_args_list]
        self.assertTrue(60 >= timeouts[0] >= timeouts[1] >= timeouts[2] > 55, timeouts)
        self.assertTrue(line.startswith("1 analyst in 3 sessions: 1 stopped after 1 minutes"), line)
        self.assertEqual((self.out / "explore" / "analyst-1.jsonl").read_text(encoding="utf-8"),
                         '{"type":"result"}\n{"type":"result"}\nlast\n')

    def test_an_analyst_that_ends_at_once_is_not_started_again(self):
        done = subprocess.CompletedProcess([], 0, '{"type":"result"}\n', "")
        with mock.patch.object(agents, "call", return_value=done) as call:
            self.explore(5, 1)
        self.assertEqual(call.call_count, 1)

    def test_coverage_counts_what_each_agent_opened_and_what_searches_showed(self):
        # Both analysts are given the same transcript, so each opened the same message.
        write_message(self.corpus, "1.eml", "Other", "other")
        write_message(self.corpus, "2.eml", "Third", "third")
        use = lambda i, name, given, parent=None: {"type": "assistant", "parent_tool_use_id": parent, "message": {
            "content": [{"type": "tool_use", "id": i, "name": name, "input": given}]}}
        result = lambda i, text, error=False: {"type": "user", "message": {
            "content": [{"type": "tool_result", "tool_use_id": i, "content": text, "is_error": error}]}}
        events = [
            use("a", "Read", {"file_path": "C:\\w\\corpus\\box\\inbox\\0.eml"}), result("a", "text"),
            use("b", "Grep", {"output_mode": "content"}), result("b", "corpus\\box\\inbox\\1.eml:Subject: Other"),
            use("c", "Grep", {"output_mode": "files_with_matches"}), result("c", "corpus/box/inbox/2.eml"),
            use("d", "Read", {"file_path": "corpus/box/inbox/1.eml"}, parent="x"), result("d", "text"),
            use("e", "Read", {"file_path": "corpus/box/inbox/2.eml"}), result("e", "denied", error=True),
        ]
        done = subprocess.CompletedProcess([], 0, "".join(json.dumps(e) + "\n" for e in events), "")
        with mock.patch.object(agents, "call", return_value=done):
            line = self.explore(1, 2)
        report = read_json(self.out / "coverage.json")
        self.assertEqual((report["messages"], report["read"], report["glimpsed_only"]), (3, 2, 0))
        self.assertEqual((report["analysts"], report["critics"]), ({"read": 1, "glimpsed": 1}, {"read": 1, "glimpsed": 0}))
        self.assertEqual((report["read_by_each_analyst"], report["read_by_several_analysts"]), ([1, 1], 1))
        self.assertEqual(report["read_ids"], ["box/inbox/0.", "box/inbox/1."])
        self.assertIn("read 2 of 3 messages (analysts 1, critics 1; 1 by more than one analyst)", line)

    def test_the_agents_come_from_their_files(self):
        defs = explore.agent_definitions()
        self.assertIn("Agent(critic)", defs["analyst"]["tools"])
        self.assertNotIn("Bash", defs["analyst"]["tools"])
        self.assertIn("Bash", defs["critic"]["tools"])
        self.assertIn("py -m pipeline save", defs["critic"]["prompt"])
        self.assertIn("py -m pipeline reject", defs["critic"]["prompt"])
        self.assertIn("py -m pipeline check", defs["critic"]["prompt"])
        self.assertTrue(defs["critic"]["prompt"].endswith(explore.NEEDS + "\n" + explore.REJECTION_NEEDS))
        self.assertIn("Bash(py -m pipeline reject:*)", explore.ALLOWED)
        self.assertIn("Bash(py -m pipeline check:*)", explore.ALLOWED)


class MessageIdTest(unittest.TestCase):
    def test_a_file_named_any_usual_way_is_found(self):
        messages = {"box/inbox/0.": {}}
        for name in ("corpus/box/inbox/0.eml", "box/inbox/0.eml", "./box/inbox/0.eml", "box/inbox/0.",
                     "box/inbox/0", "C:\\x\\workspace\\corpus\\box\\inbox\\0.eml"):
            self.assertEqual(message_id(name, messages, {}), "box/inbox/0.", name)
        self.assertIsNone(message_id("box/inbox/9.eml", messages, {}))


if __name__ == "__main__":
    unittest.main()
