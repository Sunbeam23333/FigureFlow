"""Offline, replayable edits to FigureFlow scenes; never calls a model.

The editable source is scene JSON plus explicitly local assets, not an arbitrary
flattened SVG imported as inferred diagram semantics. SVG is a delivery format.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil

from .scene import render_scene, validate_scene
from .scene_patch import apply_scene_patch, hash_scene, validate_symbol_consistency


def _read_json(path: Path):
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("scene or patch exceeds 8 MB")
    return json.loads(path.read_text(encoding="utf-8"))


def _assets(scenes: list[dict], root: Path) -> dict[str, Path]:
    selected = {}
    total = 0
    for scene in scenes:
        for item in scene["items"]:
            if item.get("type") != "image" or item["source"].startswith("data:"):
                continue
            name = item["source"]
            relative = PurePosixPath(name)
            # A reserved assets/ subtree prevents collisions with package files.
            if relative.is_absolute() or ".." in relative.parts or "\\" in name or relative.parts[0] != "assets":
                raise ValueError("portable scenes require relative assets/... image paths")
            path = (root / name).resolve(strict=True)
            if root not in path.parents or not path.is_file():
                raise ValueError("asset is outside the explicit scene directory")
            if path.suffix.lower() not in {".svg", ".png", ".jpg", ".jpeg", ".webp"}:
                raise ValueError("unsupported local asset format")
            if name not in selected:
                size = path.stat().st_size
                if size > 25 * 1024 * 1024:
                    raise ValueError("asset exceeds 25 MB")
                total += size
                if total > 100 * 1024 * 1024:
                    raise ValueError("selected assets exceed 100 MB")
                selected[name] = path
    return selected


def edit_scene_file(scene_file: str | Path, output_dir: str | Path, *, patch_file: str | Path | None = None) -> dict:
    source = Path(scene_file).resolve(strict=True)
    scene = _read_json(source)
    updated = scene
    patch = None
    receipt = None
    if patch_file is not None:
        patch = _read_json(Path(patch_file))
        updated, receipt = apply_scene_patch(scene, patch)
    assets = _assets([scene, updated], source.parent)
    # Both geometry and symbols are validated before creating a delivery folder.
    validate_scene(updated, base_dir=source.parent)
    symbols = validate_symbol_consistency(updated)
    if not symbols["pass"]:
        raise ValueError("declared symbol consistency failed: " + json.dumps(symbols["errors"]))
    dest = Path(output_dir).resolve()
    if dest == source.parent or source.parent in dest.parents and dest.name == "assets":
        raise ValueError("choose a separate output directory")
    dest.mkdir(parents=True, exist_ok=False)
    for name, path in assets.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    def save(name, value):
        (dest / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    save("before.scene.json", scene)
    save("figure.scene.json", updated)
    if patch is not None:
        save("edit.patch.json", patch)
        save("edit.receipt.json", receipt)
    result = render_scene(updated, dest / "figure", formats=("svg", "png", "pdf"), base_dir=dest)
    qa = result["qa"]
    # Geometry/symbol checks are not a human semantic or aesthetic approval.
    manifest = {"mode": "offline-scoped-edit" if patch is not None else "offline-scene-render",
        "status": "needs-human-review" if qa["ok"] else "draft-only",
        "before_sha256": hash_scene(scene), "after_sha256": hash_scene(updated),
        "geometry_qa": qa, "symbol_qa": symbols, "human_approval": "pending",
        "files": [p.name for p in dest.iterdir() if p.is_file()],
        "assets": sorted(assets), "edit_receipt": receipt}
    save("manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("render", "edit"):
        p = sub.add_parser(command)
        p.add_argument("scene")
        p.add_argument("--output", required=True)
        if command == "edit":
            p.add_argument("--patch", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("scene")
    search = sub.add_parser("search-brand")
    search.add_argument("query")
    imp = sub.add_parser("import-brand")
    imp.add_argument("asset_id")
    imp.add_argument("--output", required=True)
    imp.add_argument("--allow-network", action="store_true", help="Permit one catalog download; verify the owner's brand-use terms before sharing.")
    args = parser.parse_args(argv)
    if args.command == "search-brand":
        from .official_assets import search_official
        result = search_official(args.query)
    elif args.command == "import-brand":
        if not args.allow_network:
            parser.error("import-brand requires explicit --allow-network")
        from .official_assets import import_official
        result = import_official(args.asset_id, args.output)
    elif args.command == "inspect":
        scene = _read_json(Path(args.scene))
        result = {"sha256": hash_scene(scene), "items": [{k: i[k] for k in ("id", "type", "bounds", "text", "source") if k in i} for i in scene["items"]],
            "symbol_qa": validate_symbol_consistency(scene)}
    else:
        result = edit_scene_file(args.scene, args.output, patch_file=getattr(args, "patch", None))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and result.get("status") == "draft-only":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
