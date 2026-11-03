import tempfile
import unittest
from pathlib import Path

from pipeline import schemas
from pipeline.__main__ import prepare
from pipeline.leads import checked_leads, leads_markdown, reader_task
from pipeline.state import leads_output, read_json
from tests.test_state import put, write_message


class LeadsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.tmp.name) / "corpus"
        self.out = Path(self.tmp.name) / "out"
        # Two messages too large to share a chunk -> two batches.
        for i in range(2):
            write_message(self.corpus, f"{i}.eml", f"Subject {i}", f"line {i}\n" * 60_000)
        prepare(self.corpus, self.out)
        self.chunks = read_json(self.out / "chunks.json")["chunks"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_reader_is_given_its_whole_batch(self):
        task = reader_task(self.out, self.chunks[0])
        self.assertEqual((task.agent, task.schema, task.output), ("reader", schemas.READER, leads_output(self.out, self.chunks[0])))
        self.assertIn("===== MESSAGE box/inbox/0. =====", task.prompt)
        self.assertIn("===== END OF chunk-001", task.prompt)

    def test_only_files_of_the_readers_own_batch_are_kept(self):
        put(leads_output(self.out, self.chunks[0]), {"leads": [
            {"work": "Daily schedule", "why": "sent by hand", "files": ["box/inbox/0.", "corpus/box/inbox/0.eml", "box/inbox/1."]},
            {"work": "Elsewhere", "why": "not read here", "files": ["box/inbox/1.", "box/inbox/9."]},
        ]})
        put(leads_output(self.out, self.chunks[1]), {"leads": [{"work": "Volumes", "why": "asked again", "files": ["box/inbox/1"]}]})
        leads, files_dropped, leads_dropped = checked_leads(self.out)
        self.assertEqual(leads, [{"work": "Daily schedule", "why": "sent by hand", "files": ["corpus/box/inbox/0.eml"]},
                                 {"work": "Volumes", "why": "asked again", "files": ["corpus/box/inbox/1.eml"]}])
        self.assertEqual((files_dropped, leads_dropped), (3, 1))
        text = leads_markdown(self.out)
        self.assertTrue(text.startswith("# Leads"))
        self.assertIn("- Daily schedule: sent by hand Files: corpus/box/inbox/0.eml\n", text)
        self.assertNotIn("Elsewhere", text)
        self.assertIn("leads: 2 kept; 1 dropped", (self.out / "run.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
