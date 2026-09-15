from __future__ import annotations

import json
import csv
import importlib.util
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from demo_core.alphaedit_reproduction import CASE, compose_svg, load_case, run_reproduction, sha256


class AlphaEditReproductionTests(unittest.TestCase):
    def test_exact_source_and_semantic_inventory(self):
        scene, rows = load_case()
        self.assertEqual(len(rows), 55)
        self.assertEqual(scene["counts"]["bars"], 55)
        self.assertEqual(scene["counts"]["paths"], 71)
        self.assertEqual(scene["source_sha256"], sha256(CASE / "reference/intro_part2.pdf"))
        self.assertEqual(len({e["id"] for e in scene["elements"]}), len(scene["elements"]))

    def test_output_is_reconstructed_primitives_not_image_or_embedded_pdf(self):
        scene, rows = load_case()
        svg = compose_svg(scene, rows)
        root = ET.fromstring(svg)
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertFalse(root.findall(".//s:image", ns))
        self.assertFalse(root.findall(".//s:use", ns))
        bars = [e for e in root.iter() if "data-metric" in e.attrib]
        self.assertEqual(len(bars), 55)
        self.assertIn("CC BY 4.0", svg)
        self.assertNotIn("data:application/pdf", svg)

    def test_mutated_csv_must_not_silently_reuse_artwork(self):
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp)
            shutil.copyfile(CASE / "scene.json", case / "scene.json")
            text = (CASE / "data.csv").read_text().replace("98.9", "88.9")
            (case / "data.csv").write_text(text)
            with self.assertRaisesRegex(ValueError, "Changed data"):
                load_case(case)

    def test_conflicts_remain_explicit(self):
        audit = json.loads((CASE / "source_audit.json").read_text())
        self.assertEqual(len(audit["substantive_discrepancies"]), 4)
        self.assertEqual(audit["figure"]["displayed_values"]["Fluency"][0], "499.1")

    def test_every_csv_label_is_bound_to_actual_white_glyph_text_without_fitz(self):
        scene, rows = load_case()
        glyphs = {element["id"]: element for element in scene["elements"] if element["tag"] == "use"}
        labels = scene["numeric_labels"]
        values = {(row["metric"], row["method"]): row for row in rows}
        self.assertEqual(len(labels), 55)
        self.assertEqual(len(glyphs), 555)
        self.assertEqual(len({(label["metric"], label["method"]) for label in labels}), 55)
        bound = []
        for label in labels:
            row = values[(label["metric"], label["method"])]
            run = [glyphs[identity] for identity in label["glyph_ids"]]
            self.assertEqual(label["text"], row["label"])
            self.assertEqual(float(label["text"]), float(row["value"]))
            self.assertEqual("".join(glyph["attrs"]["data-text"] for glyph in run), row["label"])
            self.assertTrue(all(glyph["attrs"]["fill"] == "#ffffff" for glyph in run))
            self.assertTrue(all(glyph["role"] == "numeric-label" for glyph in run))
            self.assertTrue(all(
                glyph["attrs"]["data-label-key"] == f"{row['metric']}/{row['method']}" for glyph in run
            ))
            self.assertEqual(len(label["bounds"]), 4)
            self.assertEqual(len(label["origin"]), 2)
            bound.extend(label["glyph_ids"])
        self.assertEqual(len(bound), 198)
        self.assertEqual(len(set(bound)), 198)
        self.assertEqual(set(bound), {identity for identity, glyph in glyphs.items()
                                     if glyph["attrs"].get("fill") == "#ffffff"})
        self.assertTrue(all(glyph["role"] == "annotation" for identity, glyph in glyphs.items()
                            if identity not in set(bound)))
        self.assertEqual(scene["counts"]["annotation_glyphs"], 357)

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "Source glyph audit needs optional PyMuPDF")
    def test_numeric_bindings_match_independently_read_official_pdf(self):
        import fitz

        scene, _ = load_case()
        with fitz.open(CASE / "reference/intro_part2.pdf") as document:
            spans = [span for block in document[0].get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]
                     if span["color"] == 0xFFFFFF]
        self.assertEqual(len(spans), 55)
        spans.sort(key=lambda span: (math.degrees(math.atan2(
            (span["bbox"][1] + span["bbox"][3]) / 2 - 222,
            (span["bbox"][0] + span["bbox"][2]) / 2 - 217.8,
        )) + 90) % 360)
        for label, span in zip(scene["numeric_labels"], spans):
            self.assertEqual(label["text"], span["text"])
            for actual, expected in zip(label["bounds"], span["bbox"]):
                self.assertAlmostEqual(actual, expected, delta=0.01)
            for actual, expected in zip(label["origin"], span["origin"]):
                self.assertAlmostEqual(actual, expected, delta=0.001)

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "Source extraction needs optional PyMuPDF")
    def test_extractor_binds_reference_glyphs_and_rejects_a_false_transcription(self):
        from scripts.extract_alphaedit_scene import extract

        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)
            shutil.copyfile(CASE / "data.csv", case / "data.csv")
            extracted = extract(CASE / "reference/intro_part2.pdf", case)
            self.assertEqual(extracted["counts"]["numeric_labels"], 55)
            self.assertEqual(extracted["counts"]["numeric_glyphs"], 198)
            with (case / "data.csv").open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                columns = reader.fieldnames
                rows = list(reader)
            for row in rows:
                if row["metric"] == "Efficacy" and row["method"] == "AlphaEdit":
                    row["value"] = row["label"] = "88.9"
            with (case / "data.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "Source numeric label disagrees"):
                extract(CASE / "reference/intro_part2.pdf", case)

    @unittest.skipUnless(shutil.which("pdftoppm"), "PDF visual test needs Poppler")
    def test_end_to_end_offline_and_pixel_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "unrelated-secret.txt").write_text("not part of this run")
            result = run_reproduction(Path(temp), dpi=144)
            for path in result.values():
                self.assertTrue(Path(path).is_file())
            report = json.loads(Path(result["report"]).read_text())
            self.assertFalse(report["model_experiments_rerun"])
            self.assertLess(report["fidelity"]["mean_absolute_channel_error_0_255"], 2)
            self.assertLess(report["fidelity"]["foreground_mean_absolute_channel_error_0_255"], 12)
            manifest = Path(result["manifest"]).read_text()
            self.assertNotIn(str(Path(temp)), manifest)
            self.assertNotIn("unrelated-secret", manifest)
            with zipfile.ZipFile(result["zip"]) as archive:
                self.assertFalse(any("unrelated-secret" in name for name in archive.namelist()))
                self.assertIn("replay/demo_core/alphaedit_reproduction.py", archive.namelist())
                archive.extractall(Path(temp) / "unpacked")
            # Prove the ZIP is independently runnable without the original repository import path.
            replay = Path(temp) / "unpacked/replay"
            env = {**os.environ, "PYTHONPATH": ""}
            subprocess.run([sys.executable, "-m", "demo_core.alphaedit_reproduction", "--dpi", "72",
                            "--output-dir", "../rebuilt"], cwd=replay, env=env,
                           check=True, capture_output=True, timeout=30)
            self.assertTrue((replay.parent / "rebuilt/alphaedit_figure2.pdf").is_file())

    def test_symlink_output_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "keep.svg"
            source.write_text("keep me")
            output = root / "output"
            output.mkdir()
            (output / "alphaedit_figure2.svg").symlink_to(source)
            with self.assertRaisesRegex(ValueError, "symbolic-link"):
                run_reproduction(output)
            self.assertEqual(source.read_text(), "keep me")

    def test_glyph_mutation_cannot_pass_same_csv_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)
            scene, _ = load_case()
            identity = scene["numeric_labels"][0]["glyph_ids"][0]
            next(e for e in scene["elements"] if e["id"] == identity)["attrs"]["data-text"] = "7"
            (case / "scene.json").write_text(json.dumps(scene))
            shutil.copyfile(CASE / "data.csv", case / "data.csv")
            with self.assertRaisesRegex(ValueError, "Numeric vector glyphs"):
                load_case(case)


if __name__ == "__main__":
    unittest.main()
