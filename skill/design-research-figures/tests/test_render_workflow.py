from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from render_workflow import fallback_icon  # noqa: E402


class WorkflowRendererTests(unittest.TestCase):
    def test_generic_fallback_cross_uses_vertical_center(self) -> None:
        svg = fallback_icon("process", 100, 240, "#2A6FBB")
        self.assertIn("M 100.0 184.0 V 296.0", svg)
        self.assertNotIn("V 156.0", svg)


if __name__ == "__main__":
    unittest.main()
