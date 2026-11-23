#!/usr/bin/env python3
"""Validate FigureFlow's source-grounded main-figure registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo_core.mainfigure_registry import load_mainfigure_registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=None)
    args = parser.parse_args()
    try:
        payload = load_mainfigure_registry(args.registry) if args.registry else load_mainfigure_registry()
    except Exception as exc:  # noqa: BLE001 - CLI must report a compact validation failure
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "schema_version": payload["schema_version"], "templates": len(payload["templates"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
