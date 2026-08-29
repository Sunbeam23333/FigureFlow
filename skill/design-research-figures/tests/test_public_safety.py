from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from check_public_release import inspect_manifest, inspect_zip, scan_text  # noqa: E402
from public_safety import portable_path, sanitize_log_text  # noqa: E402
from qa_pdf import audit_log, audit_pdf  # noqa: E402
from visual_common import write_artifact_manifest  # noqa: E402


class PublicSafetyTests(unittest.TestCase):
    def test_manifest_paths_are_portable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = root / "private-input" / "figure.yaml"
            output_dir = root / "public-output"
            output = output_dir / "figure.pdf"
            spec.parent.mkdir()
            output_dir.mkdir()
            spec.write_text("evidence_status: illustrative\n", encoding="utf-8")
            output.write_bytes(b"pdf")

            manifest_path = write_artifact_manifest(
                output_dir / "figure",
                spec,
                {"evidence_status": "illustrative"},
                [output],
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["source_spec"], "figure.yaml")
            self.assertEqual(manifest["inputs"], ["figure.yaml"])
            self.assertEqual(manifest["outputs"], ["figure.pdf"])
            self.assertNotIn(str(root), json.dumps(manifest))

    def test_log_redaction_and_qa_labels(self) -> None:
        secret = "sk-" + "proj-" + "A" * 24
        endpoint = "https" + "://relay.example/v1"
        header = "Author" + "ization: " + "Bear" + "er abcdefghijklmnop"
        local_path = "/" + "Users/employee/project/figure.tex"
        system_path = "/" + "opt/texlive/fonts/font.tfm"
        raw = (
            f"{secret}\n{endpoint}\n{header}\n"
            f"Overfull \\hbox in {local_path} via {system_path}\n"
        )
        sanitized = sanitize_log_text(raw)
        self.assertNotIn(secret, sanitized)
        self.assertNotIn(endpoint, sanitized)
        self.assertNotIn(local_path, sanitized)
        self.assertNotIn(system_path, sanitized)
        self.assertIn("<redacted-api-key>", sanitized)
        self.assertIn("<redacted-url>", sanitized)
        self.assertIn("<local-path>", sanitized)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "nested" / "missing.pdf"
            pdf_result = audit_pdf(missing, None, None, None, None)
            self.assertEqual(pdf_result["file"], "missing.pdf")

            log = root / "compile.log"
            log.write_text(raw, encoding="utf-8")
            log_result = audit_log(log)
            self.assertEqual(log_result["file"], "compile.log")
            report_text = json.dumps(log_result)
            self.assertNotIn(secret, report_text)
            self.assertNotIn(local_path, report_text)

    def test_release_patterns_detect_sensitive_configuration_without_echoing_it(self) -> None:
        field = "OPENAI_" + "BASE_" + "URL"
        endpoint = "https" + "://relay.example/v1"
        issues = scan_text(f"{field}={endpoint}\n", "settings.env")
        self.assertEqual({issue.rule for issue in issues}, {"custom-endpoint-setting"})
        self.assertTrue(all(issue.file == "settings.env" for issue in issues))

    def test_online_manifest_response_id_is_rejected(self) -> None:
        response_key = "response" + "_id"
        payload = {
            "planning": {
                "mode": "online",
                response_key: "resp_test_public_boundary",
            }
        }
        issues = inspect_manifest(json.dumps(payload), "run_manifest.json")
        self.assertEqual([issue.rule for issue in issues], ["provider-response-id"])

        payload["planning"][response_key] = None
        self.assertEqual(inspect_manifest(json.dumps(payload), "run_manifest.json"), [])

    def test_zip_traversal_and_nested_manifest_are_rejected(self) -> None:
        response_key = "response" + "_id"
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "delivery.zip"
            secret = "sk-" + "proj-" + "B" * 24
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "safe")
                archive.writestr("logs/compile.log", f"token={secret}\n")
                archive.writestr(
                    "run_manifest.json",
                    json.dumps(
                        {
                            "planning": {
                                "mode": "online",
                                response_key: "resp_test_public_boundary",
                            }
                        }
                    ),
                )
            issues = inspect_zip(archive_path, "delivery.zip")
            self.assertEqual(
                {issue.rule for issue in issues},
                {"api-key", "provider-response-id", "zip-path-traversal"},
            )

    def test_portable_path_falls_back_to_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(portable_path(root / "out" / "a.json", root), "out/a.json")
            self.assertEqual(portable_path(root.parent / "outside.json", root), "outside.json")


if __name__ == "__main__":
    unittest.main()
