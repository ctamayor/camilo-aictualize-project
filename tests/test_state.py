import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import run as runner
from pipeline.__main__ import STEPS, prepare, reset, status
from pipeline.state import (draft_paths, format_action, merge_paths, next_action, progress, read_json,
                            run_active, run_lock, scout_output)


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

    def finish_scouts(self):
        for c in self.chunks():
            put(scout_output(self.out, c), {"patterns": [], "untrusted": []})

    def finish_through_score(self, opportunities):
        self.finish_scouts()
        names, mapping = merge_paths(self.out)
        put(names, {"names": []})
        put(mapping, {"processes": []})
        put(self.out / "processes.json", {"processes": []})
        put(self.out / "opportunities.json", {"opportunities": opportunities})


class NextActionTest(CorpusCase):
    def test_empty_output_starts_with_prepare(self):
        self.assertEqual(self.next(), {"action": "RUN", "step": "prepare"})

    def test_after_prepare_every_chunk_needs_a_scout(self):
        prepare(self.corpus, self.out)
        a = self.next()
        self.assertEqual(a["action"], "SCOUTS")
        self.assertEqual([c["id"] for c in a["chunks"]], ["chunk-001", "chunk-002", "chunk-003"])
        self.assertEqual(format_action(a), "SCOUTS 3 pending: chunk-001 chunk-002 chunk-003")

    def test_only_chunks_without_output_are_pending(self):
        prepare(self.corpus, self.out)
        put(scout_output(self.out, self.chunks()[0]), {})
        self.assertEqual([c["id"] for c in self.next()["chunks"]], ["chunk-002", "chunk-003"])

    def test_full_sequence_to_done(self):
        prepare(self.corpus, self.out)
        self.finish_scouts()
        self.assertEqual(self.next(), {"action": "RUN", "step": "validate"})

        names, mapping = merge_paths(self.out)
        put(names, {"names": []})
        self.assertEqual(self.next(), {"action": "MERGE", "input": names, "output": mapping})
        put(mapping, {"processes": []})
        self.assertEqual(self.next(), {"action": "RUN", "step": "group"})
        put(self.out / "processes.json", {"processes": [{"id": f"proc-{i:03d}"} for i in range(1, 26)]})
        a = self.next()
        self.assertEqual(format_action(a), "ESTIMATE 2 pending: slice-01 slice-02")
        self.assertEqual(a["slices"][1]["processes"], [f"proc-{i:03d}" for i in range(2, 26, 2)])
        put(a["slices"][0]["output"], {"estimates": []})
        self.assertEqual([s["id"] for s in self.next()["slices"]], ["slice-02"])
        put(a["slices"][1]["output"], {"estimates": []})
        self.assertEqual(self.next(), {"action": "RUN", "step": "score"})

        opps = [{"id": "opp-01", "draft": True}, {"id": "opp-02", "draft": False}]
        self.finish_through_score(opps)
        a = self.next()
        self.assertEqual((a["action"], [o["id"] for o in a["opportunities"]]), ("DRAFTERS", ["opp-01"]))

        put(draft_paths(self.out, opps[0])[1], "# SOP")
        self.assertEqual(self.next(), {"action": "RUN", "step": "finalize"})
        put(self.out / "report.json", {})
        self.assertEqual(self.next(), {"action": "DONE"})

    def test_unchanged_rerun_repeats_nothing(self):
        prepare(self.corpus, self.out)
        self.finish_through_score([])
        put(self.out / "report.json", {})
        self.assertEqual(self.next()["action"], "DONE")
        prepare(self.corpus, self.out)  # same corpus: nothing is cleared
        self.assertEqual(self.next()["action"], "DONE")

    def test_added_message_scouts_only_the_new_chunk(self):
        prepare(self.corpus, self.out)
        self.finish_through_score([])
        write_message(self.corpus, "3.eml", "New thread", "hello")
        self.assertEqual(self.next(), {"action": "RUN", "step": "prepare"})
        prepare(self.corpus, self.out)
        self.assertFalse((self.out / "opportunities.json").exists())
        self.assertEqual([c["id"] for c in self.next()["chunks"]], ["chunk-004"])
        self.assertTrue(all(scout_output(self.out, {"id": f"chunk-00{i}"}).exists() for i in (1, 2, 3)))

    def test_edited_message_rescouts_only_its_chunk(self):
        prepare(self.corpus, self.out)
        self.finish_scouts()
        write_message(self.corpus, "1.eml", "Subject 1", "edited\n" * 60_000)
        prepare(self.corpus, self.out)
        self.assertFalse(scout_output(self.out, {"id": "chunk-002"}).exists())
        self.assertEqual([c["id"] for c in self.next()["chunks"]], ["chunk-004"])


EMPTY_REPLY = {"merger": {"processes": []}, "estimator": {"estimates": []}}


def fake_agent(task):
    """Stand-in for a worker: a scout records one pattern on the first message of its
    batch, so there are processes to estimate; the others reply empty but valid."""
    if task.agent == "scout":
        chunk = next(c for c in read_json(task.output.parent.parent / "chunks.json")["chunks"] if c["id"] == task.name)
        occurrence = {"message": chunk["message_ids"][0], "quote": "line"}
        put(task.output, {"patterns": [{"name": "n", "summary": "s", "occurrences": [occurrence],
                                        "observations": [], "stalls": []}], "untrusted": []})
    else:
        put(task.output, EMPTY_REPLY[task.agent])
    return {"name": task.name, "ok": True, "seconds": 0, "error": None, "usage": {}}


class RunTest(CorpusCase):
    def fake_steps(self):
        def score(corpus, out):
            put(out / "opportunities.json", {"opportunities": []})
            return "scored"

        def finalize(corpus, out):
            put(out / "report.json", {})
            return "finalized"

        return STEPS | {"score": score, "finalize": finalize}

    def test_runs_to_done_reading_every_chunk(self):
        lines = []
        with mock.patch.object(runner.agents, "run_one", fake_agent):
            status = runner.run(self.corpus, self.out, self.fake_steps(), parallel=2, echo=lines.append)
        self.assertEqual(status, "DONE")
        self.assertTrue(all(scout_output(self.out, c).exists() for c in self.chunks()))
        self.assertTrue(any(line.startswith("prepare: read 3 files") for line in lines))
        self.assertIn("merge: running 1 of 1", lines)
        self.assertIn("estimate: running 1 of 1", lines)
        self.assertTrue((self.out / "processes.json").exists())
        self.assertIn("DONE", (self.out / "run.log").read_text(encoding="utf-8"))

    def test_a_worker_without_a_usable_reply_fails_the_run(self):
        def broken(task):
            return {"name": task.name, "ok": False, "seconds": 0, "error": "claude exited 1", "usage": {}}
        with mock.patch.object(runner.agents, "run_one", broken):
            status = runner.run(self.corpus, self.out, self.fake_steps(), echo=lambda _: None)
        self.assertTrue(status.startswith("FAILED no usable reply for chunk-001"))

    def test_stops_between_waves_when_the_time_budget_is_spent_and_resumes(self):
        def once():
            return runner.run(self.corpus, self.out, self.fake_steps(), parallel=2, max_minutes=0, echo=lambda _: None)

        with mock.patch.object(runner.agents, "run_one", fake_agent):
            self.assertEqual(once(), "CONTINUE 1 scout tasks still to run")
            self.assertEqual([c["id"] for c in self.next()["chunks"]], ["chunk-003"])
            self.assertEqual(once(), "CONTINUE 1 merger tasks still to run")
            self.assertEqual(once(), "CONTINUE 1 estimator tasks still to run")
            self.assertEqual(once(), "DONE")

    def test_a_second_run_on_the_same_folder_is_refused_while_the_first_holds_it(self):
        with run_lock(self.out):
            self.assertTrue(run_active(self.out))
            with mock.patch.object(runner.agents, "run_one", fake_agent):
                line = runner.run(self.corpus, self.out, self.fake_steps(), echo=lambda _: None)
            self.assertEqual(line, "FAILED another run is in progress on this output folder")
            self.assertFalse((self.out / "chunks.json").exists())
        self.assertFalse(run_active(self.out))

    def test_the_run_record_says_what_happened(self):
        with mock.patch.object(runner.agents, "run_one", fake_agent):
            runner.run(self.corpus, self.out, self.fake_steps(), echo=lambda _: None)
        record = read_json(self.out / "run.json")
        self.assertEqual((record["status"], record["step"], record["working_on"]), ("DONE", None, []))
        self.assertTrue(record["started"] <= record["ended"])

    def test_an_unbuilt_step_fails_clearly(self):
        with mock.patch.object(runner.agents, "run_one", fake_agent):
            status = runner.run(self.corpus, self.out, STEPS, echo=lambda _: None)
        # Nothing was estimated, so nothing is drafted and the run goes from score to finalize.
        self.assertTrue((self.out / "opportunities.json").exists())
        self.assertEqual(status, "FAILED step 'finalize' is not built yet")



class ProgressAndRestartTest(CorpusCase):
    def test_progress_follows_the_steps_in_order(self):
        steps = lambda: {st["step"]: (st["done"], st["count"]) for st in progress(self.out)}
        self.assertEqual(steps()["prepare"], (False, None))
        prepare(self.corpus, self.out)
        put(scout_output(self.out, self.chunks()[0]), {})
        self.assertEqual(steps()["scouts"], (False, [1, 3]))
        self.finish_through_score([{"id": "opp-01", "draft": True}, {"id": "opp-02", "draft": False}])
        self.assertEqual(steps()["score"], (True, None))
        self.assertEqual(steps()["drafters"], (False, [0, 1]))
        self.assertEqual(steps()["finalize"], (False, None))

    def test_status_tells_an_earlier_run_apart_from_none(self):
        self.assertTrue(status(self.corpus, self.out).startswith("NONE"))
        prepare(self.corpus, self.out)
        self.assertTrue(status(self.corpus, self.out).startswith("STOPPED the earlier run stopped before SCOUTS"))
        write_message(self.corpus, "3.eml", "New thread", "hello")
        self.assertTrue(status(self.corpus, self.out).startswith("CHANGED"))
        with run_lock(self.out):
            self.assertTrue(status(self.corpus, self.out).startswith("RUNNING"))

    def test_reset_removes_the_runs_outputs_and_nothing_else(self):
        prepare(self.corpus, self.out)
        self.finish_through_score([])
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
