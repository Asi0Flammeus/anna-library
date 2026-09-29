import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anna import parse_search_results


FIXTURES = Path(__file__).parent / "fixtures"
MIRROR = "https://annas-archive.is"


class SearchParserTests(unittest.TestCase):
    def test_current_book_cards_return_records_without_md5(self):
        html = (FIXTURES / "current-books.html").read_text()

        records = parse_search_results(html, MIRROR, limit=1)

        self.assertEqual(records, [{
            "record_id": "31491243",
            "title": "Harry Potter",
            "author": "J. K. Rowling",
            "metadata": "J. K. Rowling · 2016 · EPUB · 2.8 MB · Books catalog",
            "url": "https://annas-archive.is/books/31491243-31491243-harry-potter-1",
        }])

    def test_page_without_book_cards_returns_empty(self):
        html = (FIXTURES / "no-results.html").read_text()

        self.assertEqual(parse_search_results(html, MIRROR), [])


if __name__ == "__main__":
    unittest.main()
