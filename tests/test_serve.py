import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from pipeline import serve
from pipeline.__main__ import prepare
from pipeline.state import explore_done, leads_output, read_json, read_messages
from pipeline.validate import normalize
from tests.test_state import put, write_message

BODY = "Thanks.\n\n> Please send the\n>   “final” nominations\n> by 9am every Monday.\n"
QUOTE = 'please send the "final" nominations by 9am'
# The corpus is Latin-1, so a raw file has straight quotes, while a reader may quote them curly.
RAW_BODY = BODY.replace("“", '"').replace("”", '"')
CURLY_QUOTE = "Please send the “final” nominations by 9am"


class LocateTest(unittest.TestCase):
    def test_finds_a_quote_across_reply_markers_line_breaks_curly_quotes_and_case(self):
        start, end = serve.locate(QUOTE, BODY)
        self.assertEqual(normalize(BODY[start:end]).lower(), QUOTE)
        self.assertTrue(BODY[start:end].startswith("Please") and BODY[start:end].endswith("nominations\n> by 9am"))

    def test_a_quote_not_in_the_text_is_not_found(self):
        self.assertIsNone(serve.locate("send the draft nominations", BODY))
        self.assertIsNone(serve.locate("", BODY))


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.corpus = Path(self.tmp.name) / "corpus"
        self.out = Path(self.tmp.name) / "out"
        write_message(self.corpus, "1.eml", "Nominations", RAW_BODY)
        write_message(self.corpus, "2.eml", "Lunch", "Pizza on Friday.")
        prepare(self.corpus, self.out)
        self.cited = next(i for i, m in read_messages(self.out).items() if m["subject"] == "Nominations")
        occurrence = {"message": self.cited, "quote": CURLY_QUOTE, "pattern": "chunk-001.p01"}
        put(self.out / "validated.json", {"patterns": [{"id": "chunk-001.p01", "name": "Monday nominations"},
                                                       {"id": "chunk-002.p01", "name": "Not in a process"}]})
        put(self.out / "processes.json", {"stats": {"processes": 1}, "processes": [
            {"id": "proc-001", "name": "Weekly nominations", "patterns": ["chunk-001.p01"],
             "evidence": {"occurrences": [occurrence], "observations": []}}]})
        put(self.out / "opportunities.json", {"totals": {"dollars_per_month": 10}, "mailboxes": {},
                                              "opportunities": [{"id": "opp-01", "process": "proc-001"}]})
        put(self.out / "drafts" / "opp-01.md", "# Draft")

        self.server = ThreadingHTTPServer((serve.HOST, 0), serve.make_handler(self.out, self.corpus))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://{serve.HOST}:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def get(self, path, **query):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        with urllib.request.urlopen(url, timeout=5) as reply:
            body = reply.read()
            return json.loads(body) if reply.headers.get_content_type() == "application/json" else body.decode()

    def status(self, path, **query):
        try:
            self.get(path, **query)
            return 200
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def test_the_page_and_the_report_are_served(self):
        self.assertIn("<!doctype html>", self.get("/"))
        r = self.get("/api/report")
        self.assertTrue(r["scored"])
        self.assertEqual(r["drafts"], ["opp-01"])
        self.assertEqual(list(r["messages"]), [self.cited])
        self.assertEqual(r["messages"][self.cited]["subject"], "Nominations")
        self.assertEqual(r["patterns"], {"chunk-001.p01": "Monday nominations"})

    def test_a_message_comes_with_where_each_quote_sits_in_it(self):
        m = self.get("/api/message", id=self.cited, q=[CURLY_QUOTE, "not in this message"])
        self.assertTrue(m["text"].startswith("From: a@enron.com\nTo: b@enron.com\nCc: \nSubject: Nominations\n\n"))
        (start, end), missing = m["spans"]
        self.assertEqual(normalize(m["text"][start:end]).lower(), QUOTE)
        self.assertIsNone(missing)
        start, end = m["raw_spans"][0]
        self.assertEqual(normalize(m["raw"][start:end]).lower(), QUOTE)
        self.assertEqual(m["file"], "corpus/box/inbox/1.eml")

    def test_only_messages_of_the_run_are_served(self):
        self.assertEqual(self.status("/api/message", id="box/inbox/9."), 404)
        self.assertEqual(self.status("/api/message", id="../out/opportunities.json"), 404)
        self.assertEqual(self.status("/api/draft", id="../opportunities"), 404)
        self.assertEqual(self.get("/api/draft", id="opp-01"), "# Draft")

    def test_progress_says_how_far_the_run_has_got_and_changes_version_with_the_results(self):
        self.assertEqual([s["step"] for s in self.get("/api/progress")["steps"] if s["done"]], ["prepare"])
        for c in read_json(self.out / "chunks.json")["chunks"]:
            put(leads_output(self.out, c), {"leads": []})
        put(explore_done(self.out), {})
        live = self.get("/api/progress")
        self.assertFalse(live["active"])
        self.assertEqual([s["step"] for s in live["steps"] if s["done"]], ["prepare", "readers", "explore", "drafters"])
        before = live["version"]
        put(self.out / "drafts" / "opp-02.md", "# Another")
        self.assertNotEqual(self.get("/api/progress")["version"], before)

    def test_a_report_before_scoring_says_so(self):
        (self.out / "opportunities.json").unlink()
        self.assertFalse(self.get("/api/report")["scored"])


class EnsureRunningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.want = str(self.out.resolve())

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_dashboard_already_showing_this_run_is_reused(self):
        with mock.patch.object(serve, "serving", return_value=self.want), \
                mock.patch.object(serve, "_start") as start:
            self.assertEqual(serve.ensure_running(self.out, self.out), f"http://{serve.HOST}:{serve.PORT}/")
        start.assert_not_called()

    def test_another_runs_dashboard_is_left_running_and_the_next_free_port_used(self):
        shows = {serve.PORT: "elsewhere"}
        started = []

        def start(out, corpus, port):
            started.append(port)
            shows[port] = self.want

        with mock.patch.object(serve, "serving", side_effect=lambda port: shows.get(port)), \
                mock.patch.object(serve, "_port_free", return_value=True), \
                mock.patch.object(serve, "_start", side_effect=start):
            self.assertEqual(serve.ensure_running(self.out, self.out), f"http://{serve.HOST}:{serve.PORT + 1}/")
        self.assertEqual(started, [serve.PORT + 1])


if __name__ == "__main__":
    unittest.main()
