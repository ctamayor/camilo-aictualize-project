import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import run as runner
from pipeline.__main__ import STEPS, prepare, reset, status
from pipeline.agents import Task
from pipeline.state import (draft_paths, explore_done, format_action, leads_output, next_action, progress,
                            read_json, run_active, run_lock)


def write_message(corpus: Path, name: str, subject: str, body: str) -> None:
    path = corpus / "box" / "inbox" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"Message-ID: <{name}@x>\nDate: Mon, 6 Mar 2000 04:35:00 -0800\n"
                    f"From: a@enron.com\nTo: b@enron.com\nSubject: {subject}\n\n{body}", encoding="latin-1")


def put(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


class CorpusCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.tmp.name) / "corpus"
        self.out = Path(self.tmp.name) / "out"
        # Three messages too large to share a chunk -> three chunks.
        for i in range(3):
            write_message(self.corpus, f"{i}.eml", f"Subject {i}", f"line {i}\n" * 60_000)

    def tearDown(self):
        self.tmp.cleanup()

    def next(self):
        return next_action(self.corpus, self.out)

    def chunks(self):
        return read_json(self.out / "chunks.json")["chunks"]

    def finish_readers(self):
        for c in self.chunks():
            put(leads_output(self.out, c), {"leads": []})

    def finish_explore(self, opportunities):
        self.finish_readers()
        put(self.out / "opportunities.json", {"opportunities": opportunities})
        put(explore_done(self.out), {"status": "done"})


class NextActionTest(CorpusCase):
    def test_empty_output_starts_with_prepare(self):
        self.assertEqual(self.next(), {"action": "RUN", "step": "prepare"})

    def test_after_prepare_every_chunk_needs_a_reader(self):
        prepare(self.corpus, self.out)
        a = self.next()
        self.assertEqual(a["action"], "READERS")
        self.assertEqual(format_action(a), "READERS 3 pending: chunk-001 chunk-002 chunk-003")

    def test_only_chunks_without_leads_are_pending(self):
        prepare(self.corpus, self.out)
        put(leads_output(self.out, self.chunks()[0]), {"leads": []})
        self.assertEqual([c["id"] for c in self.next()["chunks"]], ["chunk-002", "chunk-003"])

    def test_full_sequence_to_done(self):
        prepare(self.corpus, self.out)
        self.finish_readers()
        self.assertEqual(self.next(), {"action": "EXPLORE"})
        opps = [{"id": "opp-01", "draft": True}, {"id": "opp-02", "draft": False}]
        self.finish_explore(opps)
        a = self.next()
        self.assertEqual((a["action"], [o["id"] for o in a["opportunities"]]), ("DRAFTERS", ["opp-01"]))
        put(draft_paths(self.out, opps[0])[0], {})
        self.assertEqual(self.next(), {"action": "RUN", "step": "finalize"})
        put(self.out / "report.json", {})
        self.assertEqual(self.next(), {"action": "DONE"})

    def test_an_exploration_that_saved_nothing_goes_on_to_finalize(self):
        prepare(self.corpus, self.out)
        self.finish_readers()
        put(explore_done(self.out), {"status": "done"})
        self.assertEqual(self.next(), {"action": "RUN", "step": "finalize"})

    def test_unchanged_rerun_repeats_nothing(self):
        prepare(self.corpus, self.out)
        self.finish_explore([])
        put(self.out / "report.json", {})
        self.assertEqual(self.next()["action"], "DONE")
        prepare(self.corpus, self.out)  # same corpus: nothing is cleared
        self.assertEqual(self.next()["action"], "DONE")

    def test_added_message_reads_only_the_new_chunk_and_explores_again(self):
        prepare(self.corpus, self.out)
        self.finish_explore([])
        write_message(self.corpus, "3.eml", "New thread", "hello")
        self.assertEqual(self.next(), {"action": "RUN", "step": "prepare"})
        prepare(self.corpus, self.out)
        self.assertFalse((self.out / "opportunities.json").exists())
        self.assertFalse(explore_done(self.out).exists())
        self.assertEqual([c["id"] for c in self.next()["chunks"]], ["chunk-004"])
        self.assertTrue(all(leads_output(self.out, {"id": f"chunk-00{i}"}).exists() for i in (1, 2, 3)))

    def test_edited_message_rereads_only_its_chunk(self):
        prepare(self.corpus, self.out)
        self.finish_readers()
        write_message(self.corpus, "1.eml", "Subject 1", "edited\n" * 60_000)
        prepare(self.corpus, self.out)
        self.assertFalse(leads_output(self.out, {"id": "chunk-002"}).exists())
        self.assertEqual([c["id"] for c in self.next()["chunks"]], ["chunk-004"])


OPPORTUNITIES = [{"id": "opp-01", "draft": True, "rank": 1, "name": "Daily schedule", "dollars_per_month": 10},
                 {"id": "opp-02", "draft": False, "rank": 2, "name": "Other", "dollars_per_month": 5}]


def fake_agent(task):
    """Stand-in for a worker: a reader records one lead on the first message of its
    batch; a drafter writes a draft."""
    if task.agent == "reader":
        chunk = next(c for c in read_json(task.output.parent.parent / "chunks.json")["chunks"] if c["id"] == task.name)
        put(task.output, {"leads": [{"work": "w", "why": "y", "files": [chunk["message_ids"][0]]}]})
    else:
        put(task.output, {"kind": "Email", "audience": "the scheduler", "title": "Automate it", "body": "Please."})
    return {"name": task.name, "ok": True, "seconds": 0, "error": None, "usage": {}}


def fake_explore(corpus, out, minutes, analysts):
    put(out / "opportunities.json", {"totals": {"ranked": 2}, "opportunities": OPPORTUNITIES})
    put(explore_done(out), {"status": "explored"})
    return "explored"


def drafter_tasks(out, opportunities):
    return [Task(o["id"], "drafter", "analysis", draft_paths(out, o)[0], {}) for o in opportunities]


class RunTest(CorpusCase):
    def run_pipeline(self, agent=fake_agent, **kwargs):
        lines = []
        with mock.patch.object(runner.agents, "run_one", agent), \
                mock.patch.object(runner, "explore", side_effect=fake_explore) as explore, \
                mock.patch.object(runner, "drafter_tasks", drafter_tasks):
            line = runner.run(self.corpus, self.out, STEPS, echo=lines.append, **kwargs)
        return line, lines, explore

    def test_runs_to_done_reading_every_chunk_exploring_and_drafting(self):
        line, lines, explore = self.run_pipeline(explore_minutes=20, analysts=8)
        self.assertEqual(line, "DONE")
        self.assertTrue(all(leads_output(self.out, c).exists() for c in self.chunks()))
        self.assertTrue(any(text.startswith("prepare: read 3 files") for text in lines))
        self.assertIn("readers: running 3 of 3", lines)
        self.assertEqual(explore.call_args.args[2:], (20, 8))
        self.assertIn("drafters: running 1 of 1", lines)
        self.assertTrue((self.out / "drafts" / "opp-01.md").read_text(encoding="utf-8").startswith("# Automate it"))
        self.assertFalse((self.out / "drafts" / "opp-02.md").exists())
        self.assertEqual(list(read_json(self.out / "report.json")["drafts"]), ["opp-01"])
        self.assertIn("DONE", (self.out / "run.log").read_text(encoding="utf-8"))

    def test_a_finished_run_run_again_repeats_nothing(self):
        self.run_pipeline()
        calls = []
        line, _, explore = self.run_pipeline(agent=lambda task: calls.append(task) or fake_agent(task))
        self.assertEqual((line, calls, explore.call_count), ("DONE", [], 0))

    def test_a_worker_without_a_usable_reply_fails_the_run(self):
        def broken(task):
            return {"name": task.name, "ok": False, "seconds": 0, "error": "claude exited 1", "usage": {}}
        line, _, explore = self.run_pipeline(agent=broken)
        self.assertTrue(line.startswith("FAILED no usable reply for chunk-001"))
        self.assertIn("trying again: chunk-001", (self.out / "run.log").read_text(encoding="utf-8"))
        self.assertEqual(explore.call_count, 0)

    def test_a_worker_that_fails_once_is_tried_again(self):
        tries = []

        def flaky(task):
            tries.append(task.name)
            if tries.count(task.name) == 1 and task.name in ("chunk-002", "opp-01"):
                return {"name": task.name, "ok": False, "seconds": 0, "error": "no reply", "usage": {}}
            return fake_agent(task)
        line, _, _ = self.run_pipeline(agent=flaky)
        self.assertEqual(line, "DONE")
        self.assertEqual((tries.count("chunk-002"), tries.count("opp-01")), (2, 2))

    def test_a_second_run_on_the_same_folder_is_refused_while_the_first_holds_it(self):
        with run_lock(self.out):
            self.assertTrue(run_active(self.out))
            line, _, _ = self.run_pipeline()
            self.assertEqual(line, "FAILED another run is in progress on this output folder")
            self.assertFalse((self.out / "chunks.json").exists())
        self.assertFalse(run_active(self.out))

    def test_the_run_record_says_what_happened(self):
        self.run_pipeline()
        record = read_json(self.out / "run.json")
        self.assertEqual((record["status"], record["step"], record["working_on"]), ("DONE", None, []))
        self.assertTrue(record["started"] <= record["ended"])


class ProgressAndRestartTest(CorpusCase):
    def test_progress_follows_the_steps_in_order(self):
        steps = lambda: {st["step"]: (st["done"], st["count"]) for st in progress(self.out)}
        self.assertEqual(steps()["prepare"], (False, None))
        prepare(self.corpus, self.out)
        put(leads_output(self.out, self.chunks()[0]), {})
        self.assertEqual(steps()["readers"], (False, [1, 3]))
        self.assertEqual(steps()["explore"], (False, None))
        self.finish_explore([{"id": "opp-01", "draft": True}, {"id": "opp-02", "draft": False}])
        self.assertEqual(steps()["explore"], (True, None))
        self.assertEqual(steps()["drafters"], (False, [0, 1]))
        self.assertEqual(steps()["finalize"], (False, None))

    def test_status_tells_an_earlier_run_apart_from_none(self):
        self.assertTrue(status(self.corpus, self.out).startswith("NONE"))
        prepare(self.corpus, self.out)
        self.assertTrue(status(self.corpus, self.out).startswith("STOPPED the earlier run stopped before READERS"))
        write_message(self.corpus, "3.eml", "New thread", "hello")
        self.assertTrue(status(self.corpus, self.out).startswith("CHANGED"))
        with run_lock(self.out):
            self.assertTrue(status(self.corpus, self.out).startswith("RUNNING"))

    def test_reset_removes_the_runs_outputs_and_nothing_else(self):
        prepare(self.corpus, self.out)
        self.finish_explore([])
        put(self.out / "notes.txt", "kept")
        self.assertIn("removed", reset(self.out))
        self.assertEqual([p.name for p in self.out.iterdir()], ["notes.txt"])
        self.assertTrue(status(self.corpus, self.out).startswith("NONE"))

    def test_reset_refuses_while_a_run_is_in_progress(self):
        prepare(self.corpus, self.out)
        with run_lock(self.out), self.assertRaises(SystemExit):
            reset(self.out)
        self.assertTrue((self.out / "chunks.json").exists())


if __name__ == "__main__":
    unittest.main()
