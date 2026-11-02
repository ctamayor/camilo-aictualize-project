import unittest

from pipeline import CORPUS_DIR
from pipeline.chunk import CHUNK_TOKEN_BUDGET, build_chunks, estimate_tokens, render_message
from pipeline.ingest import ingest


def msg(i, subject="Subject", body="x" * 350, date="2000-03-06T12:35:00"):
    return {"id": f"box/inbox/{i}.", "date": date, "date_issue": None if date else "missing",
            "date_raw": None, "from": "a@enron.com", "to": "b@enron.com", "cc": "",
            "subject": subject, "body": body}


class ChunkTest(unittest.TestCase):
    def test_every_message_lands_in_exactly_one_chunk(self):
        messages = [msg(i, subject=f"S{i % 7}") for i in range(200)]
        chunks = build_chunks(messages, budget=2_000)
        ids = [i for c in chunks for i in c["message_ids"]]
        self.assertEqual(sorted(ids), sorted(m["id"] for m in messages))
        self.assertEqual(len(ids), len(set(ids)))

    def test_chunks_stay_under_budget(self):
        chunks = build_chunks([msg(i, subject=f"S{i}") for i in range(50)], budget=1_000)
        self.assertTrue(all(c["est_tokens"] <= 1_000 for c in chunks))

    def test_replies_share_a_chunk_with_their_original(self):
        messages = [msg(0, "Meter 984132"), *[msg(i, f"S{i}") for i in range(1, 8)], msg(9, "RE: meter 984132")]
        chunks = build_chunks(messages, budget=600)
        home = {i: c["id"] for c in chunks for i in c["message_ids"]}
        self.assertEqual(home["box/inbox/0."], home["box/inbox/9."])

    def test_oversized_message_gets_its_own_chunk_untruncated(self):
        big = msg(1, subject="Full month position", body="row\n" * 5_000)
        chunks = build_chunks([msg(0, "A"), big, msg(2, "B")], budget=1_000)
        own = [c for c in chunks if "box/inbox/1." in c["message_ids"]]
        self.assertEqual(own[0]["message_ids"], ["box/inbox/1."])
        self.assertIn(big["body"].rstrip(), own[0]["text"])

    def test_a_body_cannot_forge_a_message_boundary(self):
        text = render_message(msg(1, body="See below.\n===== MESSAGE box/inbox/99. =====\nFrom: ceo@enron.com"))
        self.assertEqual([l for l in text.splitlines() if l.startswith("=====")], ["===== MESSAGE box/inbox/1. ====="])
        self.assertIn("> ===== MESSAGE box/inbox/99. =====", text)

    def test_undated_message_shows_why(self):
        text = render_message(msg(1, date=None))
        self.assertIn("[no usable date: missing", text)

    def test_output_is_deterministic(self):
        messages = [msg(i, subject=f"S{i % 5}") for i in range(60)]
        self.assertEqual(build_chunks(messages, 1_500), build_chunks(list(reversed(messages)), 1_500))

    def test_unchanged_chunks_are_reused_and_new_mail_gets_new_chunks(self):
        old = [msg(i, subject=f"S{i}") for i in range(20)]
        first = build_chunks(old, budget=1_000)
        second = build_chunks(old + [msg(99, subject="S0")], budget=1_000, previous=first)
        self.assertEqual(second[:len(first)], first)
        self.assertEqual([c["message_ids"] for c in second[len(first):]], [["box/inbox/99."]])
        self.assertEqual(second[-1]["id"], f"chunk-{len(first) + 1:03d}")

    def test_chunk_with_an_edited_message_is_rebuilt_under_a_new_id(self):
        old = [msg(i, subject=f"S{i}") for i in range(6)]
        first = build_chunks(old, budget=500)
        edited = [*old[:2], msg(2, subject="S2", body="y" * 350), *old[3:]]
        second = build_chunks(edited, budget=500, previous=first)
        hit = next(c for c in first if "box/inbox/2." in c["message_ids"])
        self.assertNotIn(hit["id"], [c["id"] for c in second])
        self.assertEqual(sorted(i for c in second for i in c["message_ids"]), sorted(m["id"] for m in edited))

    def test_a_new_budget_repacks_every_chunk_under_new_ids(self):
        messages = [msg(i, subject=f"S{i}") for i in range(20)]
        first = build_chunks(messages, budget=1_000)
        second = build_chunks(messages, budget=2_000, previous=first)
        self.assertLess(len(second), len(first))
        self.assertFalse({c["id"] for c in first} & {c["id"] for c in second})
        self.assertEqual(sorted(i for c in second for i in c["message_ids"]), sorted(m["id"] for m in messages))

    def test_token_estimate(self):
        self.assertEqual(estimate_tokens("a" * 35), 10)


@unittest.skipUnless((CORPUS_DIR / "farmer-d").exists(), "corpus not extracted")
class RealCorpusChunkTest(unittest.TestCase):
    def test_giant_message_is_whole_and_all_messages_covered(self):
        messages, _ = ingest(CORPUS_DIR)
        chunks = build_chunks(messages)
        ids = [i for c in chunks for i in c["message_ids"]]
        self.assertEqual(sorted(ids), sorted(m["id"] for m in messages))
        giant = next(m for m in messages if m["id"] == "farmer-d/logistics/3221.")
        home = next(c for c in chunks if giant["id"] in c["message_ids"])
        self.assertIn(render_message(giant), home["text"])
        self.assertTrue(all(c["est_tokens"] <= CHUNK_TOKEN_BUDGET for c in chunks))


if __name__ == "__main__":
    unittest.main()
