import tempfile
import unittest
from pathlib import Path

from pipeline import CORPUS_DIR
from pipeline.ingest import dedupe, ingest, original_path, parse_date, parse_message


def raw(msg_id="<1@x>", date="Mon, 6 Mar 2000 04:35:00 -0800 (PST)", sender="a@enron.com",
        subject="Hello", body="Body text."):
    headers = [f"Message-ID: {msg_id}"]
    if date is not None:
        headers.append(f"Date: {date}")
    headers += [f"From: {sender}", "To: b@enron.com", f"Subject: {subject}"]
    return "\n".join(headers) + "\n\n" + body


class ParseDateTest(unittest.TestCase):
    def test_valid_date_is_converted_to_utc(self):
        self.assertEqual(parse_date("Mon, 6 Mar 2000 04:35:00 -0800 (PST)"), ("2000-03-06T12:35:00", None))

    def test_missing_date(self):
        self.assertEqual(parse_date(None), (None, "missing"))

    def test_impossible_date(self):
        self.assertEqual(parse_date("Tues, 32 Febuary 2001 25:61:00"), (None, "unparseable"))

    def test_date_outside_archive_window(self):
        self.assertEqual(parse_date("Wed, 12 Mar 2031 08:14:00 -0600 (CST)"), (None, "out_of_range"))


class OriginalPathTest(unittest.TestCase):
    def test_windows_safe_name_maps_back(self):
        self.assertEqual(original_path("farmer-d/logistics/1.eml"), "farmer-d/logistics/1.")

    def test_original_name_is_unchanged(self):
        self.assertEqual(original_path("farmer-d/logistics/1."), "farmer-d/logistics/1.")


class ParseMessageTest(unittest.TestCase):
    def test_quoted_printable_body_is_decoded(self):
        text = raw(body="please send me the name of your administrative as=\nsistant.=20\n")
        text = text.replace("Subject:", "Content-Transfer-Encoding: quoted-printable\nSubject:")
        self.assertEqual(parse_message("a/1.", text)["body"], "please send me the name of your administrative assistant. \n")

    def test_plain_body_is_kept_as_written(self):
        self.assertEqual(parse_message("a/1.", raw(body="Total =20 units\n"))["body"], "Total =20 units\n")

    def test_the_messages_a_reply_answers_are_read_from_its_headers(self):
        text = raw().replace("Subject:", "In-Reply-To: <2@x>\nReferences: <1@x>\n <2@x>\nSubject:")
        self.assertEqual(parse_message("a/1.", text)["replies_to"], ["<2@x>", "<1@x>", "<2@x>"])
        self.assertEqual(parse_message("a/1.", raw())["replies_to"], [])


class DedupeTest(unittest.TestCase):
    def msg(self, path, **kw):
        return parse_message(path, raw(**kw))

    def test_same_message_id_collapses(self):
        out = dedupe([self.msg("a/1.", msg_id="<1@x>"), self.msg("b/1.", msg_id="<1@x>", body="Other")])
        self.assertEqual([(m["id"], m["duplicates"]) for m in out], [("a/1.", ["b/1."])])

    def test_reexport_with_different_wrapping_and_timezone_collapses(self):
        a = self.msg("a/1.", msg_id="<1@x>", date="Tue, 20 Mar 2001 04:55:00 -0800",
                     body="We have had \ncontinued flow.\n")
        b = self.msg("a/2.", msg_id="<2@x>", date="Tue, 20 Mar 2001 15:55:00 -0800",
                     body="We have had continued flow.\n\n<Embedded StdOleLink>")
        self.assertEqual(len(dedupe([a, b])), 1)

    def test_identical_daily_mail_on_different_days_is_kept(self):
        days = [self.msg(f"a/{d}.", msg_id=f"<{d}@x>", date=f"Mon, {d} Jul 2000 00:20:00 -0700",
                         subject="Calpine Daily Gas Nomination", body="<<nomination.doc>>")
                for d in (24, 25, 26)]
        self.assertEqual(len(dedupe(days)), 3)

    def test_different_senders_are_kept(self):
        out = dedupe([self.msg("a/1.", msg_id="<1@x>", body="Thanks"),
                      self.msg("a/2.", msg_id="<2@x>", sender="c@enron.com", body="Thanks")])
        self.assertEqual(len(out), 2)


class IngestTest(unittest.TestCase):
    def test_reads_both_file_layouts_and_reports_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "x" / "inbox"
            box.mkdir(parents=True)
            (box / "1.eml").write_text(raw(msg_id="<1@x>"), encoding="latin-1")
            (box / "2.eml").write_text(raw(msg_id="<2@x>", date=None, body="Other"), encoding="latin-1")
            (box / "3.eml").write_text(raw(msg_id="<1@x>"), encoding="latin-1")
            (Path(tmp) / "manifest.csv").write_text("ignored", encoding="utf-8")
            messages, report = ingest(Path(tmp))
        self.assertEqual([m["id"] for m in messages], ["x/inbox/1.", "x/inbox/2."])
        self.assertEqual(report["files_read"], 3)
        self.assertEqual(report["duplicate_groups"], [["x/inbox/1.", "x/inbox/3."]])
        self.assertEqual(report["date_issues"], [{"id": "x/inbox/2.", "issue": "missing", "raw": None}])


@unittest.skipUnless((CORPUS_DIR / "farmer-d").exists(), "corpus not extracted")
class RealCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.messages, cls.report = ingest(CORPUS_DIR)

    def test_reads_every_file(self):
        self.assertEqual(self.report["files_read"], 3240)

    def test_known_bad_dates(self):
        issues = {d["id"]: d["issue"] for d in self.report["date_issues"]}
        self.assertEqual(issues, {
            "giron-d/sent/795.": "missing",
            "lokay-m/inbox/74.": "out_of_range",
            "williams-w3/inbox/142.": "unparseable",
        })

    def test_cross_mailbox_copy_is_collapsed(self):
        self.assertIn(["farmer-d/logistics/880.", "williams-w3/inbox/143."], self.report["duplicate_groups"])

    def test_quoted_printable_message_reads_cleanly(self):
        qp = [m for m in self.messages if m["id"] == "williams-w3/sent_items/108."][0]
        self.assertIn("the name of your administrative assistant", " ".join(qp["body"].split()))

    def test_daily_calpine_nominations_are_not_collapsed(self):
        ids = {m["id"] for m in self.messages}
        for n in (1310, 1312, 1316, 1318, 1329, 1336, 1348):
            self.assertIn(f"farmer-d/logistics/{n}.", ids)


if __name__ == "__main__":
    unittest.main()
