import csv
import json
import unittest
from pathlib import Path

CASE = Path(__file__).resolve().parents[1] / "cases/care_transformer_fig1"


class CareReconstructionTest(unittest.TestCase):
    def test_data_provenance_and_positive_coordinates(self):
        with (CASE / "data.csv").open(newline="") as source:
            rows = list(csv.DictReader(source))
        provenance = json.loads((CASE / "provenance.json").read_text())
        self.assertEqual(len(rows), provenance["point_count"])
        self.assertEqual(len({row["model"] for row in rows}), len(rows))
        self.assertTrue(all(float(row["latency_ms"]) > 0 and float(row["gmac"]) > 0 for row in rows))
        self.assertIn("Inferred", provenance["latency_interpretation"])
        self.assertIn("not pixel-identical", provenance["fidelity"])


if __name__ == "__main__":
    unittest.main()
