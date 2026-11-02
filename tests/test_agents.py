import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import agents, schemas


def envelope(**fields) -> str:
    return json.dumps({"type": "result", "is_error": False, "usage": {"input_tokens": 10, "output_tokens": 2}} | fields)


def completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class RunOneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "scout" / "chunk-001.json"
        self.task = agents.Task("chunk-001", "scout", "the batch text", self.out, schemas.SCOUT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_runs_the_agent_headless_without_tools_and_writes_the_reply(self):
        reply = {"patterns": [], "untrusted": []}
        with mock.patch.object(agents.subprocess, "run", return_value=completed(envelope(structured_output=reply))) as run:
            result = agents.run_one(self.task)
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:7], ["-p", "--agent", "scout", "--tools", "", "--output-format"])
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), schemas.SCOUT)
        self.assertEqual(run.call_args.kwargs["input"], "the batch text")
        self.assertTrue(result["ok"])
        self.assertEqual(json.loads(self.out.read_text(encoding="utf-8")), reply)
        self.assertEqual(result["usage"]["output_tokens"], 2)

    def test_the_log_line_names_the_model_the_agent_ran_on(self):
        reply = completed(envelope(structured_output={"patterns": [], "untrusted": []}, num_turns=2,
                                   modelUsage={"claude-opus-5-5": {"outputTokens": 2}}))
        with mock.patch.object(agents.subprocess, "run", return_value=reply):
            result = agents.run_one(self.task)
        self.assertTrue(agents.describe(result).endswith(", 10 in / 2 out, 2 turns, claude-opus-5-5)"))

    def test_falls_back_to_json_in_the_result_text(self):
        reply = {"patterns": [], "untrusted": []}
        with mock.patch.object(agents.subprocess, "run", return_value=completed(envelope(result=json.dumps(reply)))):
            result = agents.run_one(self.task)
        self.assertTrue(result["ok"])
        self.assertEqual(json.loads(self.out.read_text(encoding="utf-8")), reply)

    def test_failures_write_nothing_and_say_why(self):
        cases = {
            "exited": completed("", returncode=1, stderr="boom"),
            "not json": completed("Sorry, I could not"),
            "is_error": completed(envelope(is_error=True, result="rate limited")),
            "not an object": completed(envelope(result="[1, 2]")),
        }
        for label, proc in cases.items():
            with self.subTest(label), mock.patch.object(agents.subprocess, "run", return_value=proc):
                result = agents.run_one(self.task)
            self.assertFalse(result["ok"], label)
            self.assertTrue(result["error"], label)
            self.assertFalse(self.out.exists(), label)

    def test_timeout_is_a_failure(self):
        with mock.patch.object(agents.subprocess, "run", side_effect=subprocess.TimeoutExpired("claude", 1)):
            result = agents.run_one(self.task)
        self.assertFalse(result["ok"])
        self.assertIn("no reply", result["error"])


class RunWaveTest(unittest.TestCase):
    def test_runs_every_task_and_keeps_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = [agents.Task(f"chunk-{i}", "scout", "x", Path(tmp) / f"{i}.json", schemas.SCOUT) for i in range(5)]
            reply = completed(envelope(structured_output={"patterns": [], "untrusted": []}))
            with mock.patch.object(agents.subprocess, "run", return_value=reply):
                results = agents.run_wave(tasks, parallel=2)
            self.assertEqual([r["name"] for r in results], [t.name for t in tasks])
            self.assertTrue(all(t.output.exists() for t in tasks))


if __name__ == "__main__":
    unittest.main()
