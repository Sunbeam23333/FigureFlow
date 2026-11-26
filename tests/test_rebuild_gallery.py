import unittest
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory

from cases.paper_rebuilds.gallery import write_gallery


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.links = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "img":
            self.images.append(attr["src"])
        if tag == "a":
            self.links.append(attr["href"])
        if tag == "script":
            self.scripts.append(attr)


class RebuildGalleryTests(unittest.TestCase):
    def setUp(self):
        self.spec = {
            "id": "demo_fig1",
            "paper": "A & B",
            "figure": "Figure 1",
            "venue": "CVPR",
            "page": 1,
            "url": "https://example.com/paper",
            "palette": {"ink": "#abc123"},
            "claim": "<no new measurement>",
            "limitations": ["Font metrics differ."],
        }

    def test_local_pairs_and_editable_downloads(self):
        with TemporaryDirectory() as d:
            target = write_gallery([self.spec], Path(d) / "gallery")
            page = target.read_text()
            parser = Assets()
            parser.feed(page)
            self.assertEqual(parser.images, ["demo_fig1/reference.png", "demo_fig1/candidate.png"])
            self.assertTrue(
                {
                    "demo_fig1/candidate.svg",
                    "demo_fig1/candidate.pdf",
                    "demo_fig1/comparison.pdf",
                    "demo_fig1/provenance.json",
                }
                <= set(parser.links)
            )
            self.assertFalse(parser.scripts)
            self.assertIn("&lt;no new measurement&gt;", page)
            self.assertIn("#ABC123", page)

    def test_rejects_broken_case_or_unsafe_color(self):
        with TemporaryDirectory() as d:
            for change in [
                {"id": "../bad"},
                {"url": "javascript:alert(1)"},
                {"palette": {"ink": "red; display:none"}},
            ]:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    write_gallery([dict(self.spec, **change)], Path(d))
