import unittest

from pipeline.group import build_process, numbered_quotes


def cite(n: int, quote: str = "q", note: str | None = None) -> dict:
    c = {"message": f"box/{n}.", "quote": quote}
    return c if note is None else c | {"note": note}


def pattern(occurrences: list, observations: list = (), stalls: list = ()) -> dict:
    return {"id": "saved-01", "chunk": "saved", "name": "n", "summary": "s",
            "occurrences": occurrences, "observations": list(observations), "stalls": list(stalls)}


def headers(mail: list, threads: dict = {}) -> dict:
    return {f"box/{n}.": {"id": f"box/{n}.", "date": date and f"2001-{date}:00:00", "from": f"{sender}@enron.com",
                          "to": to, "cc": "", "subject": subject, "body": body} | threads.get(n, {})
            for n, (date, sender, to, subject, body) in enumerate(mail, 1)}


class ProcessTest(unittest.TestCase):
    def test_counts_its_messages_people_and_dates_from_the_citations(self):
        mail = headers([("03-01T09", "kim", "team@enron.com, Raj@enron.com", "Report", "a"),
                        ("04-02T09", "raj", "team@enron.com", "Volumes", "b"),
                        (None, "kim", "", "Other", "c")])
        p = build_process("Daily report", "Kim collects numbers.", ["saved-01"], {"saved-01": pattern(
            [cite(1), cite(2), cite(3), cite(1)], [cite(1, "late again", "Late."), cite(1, "late  again", "Late.")],
            [cite(2, "waiting", "Held up.")])}, mail)
        self.assertEqual((p["occurrences"], p["times"]), (3, 3))
        self.assertEqual((p["first"], p["last"]), ("2001-03-01T09:00:00", "2001-04-02T09:00:00"))
        self.assertEqual(p["senders"], {"kim@enron.com": 2, "raj@enron.com": 1})
        self.assertEqual(p["recipients"], {"team@enron.com": 2, "raj@enron.com": 1})
        # The same quote recorded twice is kept once; quotes are numbered occurrences first.
        self.assertEqual(len(p["evidence"]["observations"]), 1)
        self.assertEqual([q["quote"] for q in numbered_quotes(p).values()], ["q", "q", "q", "late again", "waiting"])


class TimesTest(unittest.TestCase):
    """A message and the replies that answer it are one time; a new message with the same subject is another."""

    def test_replies_forwards_and_copies_are_the_same_time_and_new_mail_is_a_new_one(self):
        header = "\n-----Original Message-----\nFrom: Kim\nSent: Thursday, March 01, 2001 9:00 AM\n"
        mail = [
            ("03-01T09", "kim", "Meter 5", "Please fix meter 5."),
            ("03-01T11", "raj", "RE: Meter 5", "Done." + header + "Please fix meter 5."),  # quotes 1
            ("03-05T09", "kim", "Meter 5", "Please fix meter 5."),                          # asked again
            ("03-05T10", "raj", "RE: Meter 5", "Fixed."),                                   # bare Notes reply to 3
            ("03-05T12", "kim", "Lunch", "Please fix meter 5. Pizza?"),                    # another subject
            ("03-06T08", "kim", "Nomination", "- NOMINATION 1.doc"),                       # daily mail
            ("03-07T08", "kim", "Nomination", "- NOMINATION 1.doc\nRevised volumes"),     # next day's
            ("03-08T09", "kim", "RE: Report", "Agree.\n> The report is late."),            # two replies to one
            ("03-08T13", "raj", "RE: Report", "Disagree.\n> The report is late."),         # message not cited
            ("03-09T09", "ops", "Notice", "All hands at noon."),                           # one broadcast
            ("03-09T12", "hr", "Notice", "All hands at noon."),                            # and its copy
            ("03-10T09", "kim", "Invoice", "Please send the March invoice."),
            ("03-20T09", "raj", "RE: Invoice", "Sent.\n> Please send the April invoice."),  # quotes other mail
            ("03-11T09", "raj", "Status", "Done, see attached."),                          # answers 12 by header
        ]
        threads = {12: {"message_id": "<12@x>"}, 14: {"replies_to": ["<12@x>"]}}
        stall = cite(2, "Done.", "Fixed only after a chase.")
        p = build_process("n", "s", ["saved-01"], {"saved-01": pattern(
            [cite(n) for n in range(1, len(mail) + 1)], stalls=[stall])},
            headers([(d, s, "", subject, body) for d, s, subject, body in mail], threads))
        self.assertEqual([o["time"] for o in p["evidence"]["occurrences"]], [1, 1, 2, 2, 3, 4, 5, 6, 6, 7, 7, 8, 9, 8])
        self.assertEqual((p["occurrences"], p["times"], p["months"]), (14, 9, {"2001-03": 9}))
        self.assertEqual(p["evidence"]["stalls"][0]["note"], "Fixed only after a chase.")


if __name__ == "__main__":
    unittest.main()
