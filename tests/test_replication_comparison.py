import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill/design-research-figures/scripts/compare_replication.py"
spec = importlib.util.spec_from_file_location("compare_replication", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ComparisonTest(unittest.TestCase):
    def test_comparison_records_hashes_and_preserves_aspect(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            ref, cand, out = p / "reference.png", p / "candidate.png", p / "comparison.png"
            Image.new("RGB", (200, 100), "red").save(ref)
            Image.new("RGB", (100, 200), "blue").save(cand)
            with Image.open(ref) as image:
                self.assertEqual(module.fit(image, (100, 100)).size, (100, 50))
            with Image.open(cand) as image:
                self.assertEqual(module.fit(image, (100, 100)).size, (50, 100))
            module.compare(ref, cand, out)
            with Image.open(out) as image:
                self.assertEqual(image.size, (2880, 1170))
            metadata = json.loads(out.with_suffix(".json").read_text())
            self.assertEqual(metadata["fidelity"], "not assessed automatically")
            self.assertEqual(metadata["reference_sha256"], module.digest(ref))
            self.assertEqual(metadata["candidate_sha256"], module.digest(cand))


if __name__ == "__main__":
    unittest.main()
