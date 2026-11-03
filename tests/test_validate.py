import unittest

from pipeline.validate import find_quote, normalize


class FindQuoteTest(unittest.TestCase):
    def test_case_line_breaks_reply_markers_curly_quotes_and_control_bytes_are_ignored(self):
        text = normalize("> Please send the\n>  “volumes” by noon\x07 so I can\n> build the report.")
        self.assertEqual(find_quote('please send the "volumes" by noon so I can build the report', text),
                         'Please send the "volumes" by noon so I can build the report')

    def test_a_quote_not_in_the_text_or_empty_is_not_found(self):
        self.assertIsNone(find_quote("send the invoices", normalize("Please send the volumes.")))
        self.assertIsNone(find_quote("  ", normalize("Please send the volumes.")))


if __name__ == "__main__":
    unittest.main()
