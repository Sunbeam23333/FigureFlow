import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from cases.paper_rebuilds.fetch_sources import fetch_one, source_catalog


class DownloadTests(unittest.TestCase):
    def test_all_six_papers_are_pinned(self):
        self.assertEqual(
            set(source_catalog()), {"videoworld", "janus", "epona", "graphmimic", "motus", "dynaview"}
        )

    def test_download_and_verify_offline(self):
        data = b"%PDF-test fixture"
        edition = ("https://example.invalid/test", hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp)

            def success(*args, **kwargs):
                return io.BytesIO(data)

            def should_not_download(*args, **kwargs):
                self.fail("should not download when target exists")

            self.assertEqual(fetch_one("test", edition, destination, success), "downloaded and verified")
            self.assertEqual(
                fetch_one("test", edition, destination, should_not_download), "verified existing"
            )
            with self.assertRaisesRegex(ValueError, "existing file left untouched"):
                fetch_one("test", (edition[0], "a" * 64), destination, should_not_download)
            self.assertEqual((destination / "test.pdf").read_bytes(), data)
            with self.assertRaisesRegex(ValueError, "nothing installed"):
                fetch_one("wrong", (edition[0], "0" * 64), destination, success)
            with self.assertRaises(OSError):

                def offline(*args, **kwargs):
                    raise OSError("offline")

                fetch_one("failed", edition, destination, offline)
            self.assertEqual([f.name for f in destination.iterdir()], ["test.pdf"])


if __name__ == "__main__":
    unittest.main()
