#!/usr/bin/env python3
"""Create a privacy-minimized public example from a completed FigureFlow run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from PIL import Image


SENSITIVE_KEYS = {"response_id", "input_tokens", "output_tokens"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scrub(value: object, *, base: Path) -> object:
    if isinstance(value, dict):
        return {
            key: scrub(item, base=base)
            for key, item in value.items()
            if key not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [scrub(item, base=base) for item in value]
    if isinstance(value, str) and os.path.isabs(value):
        path = Path(value).resolve()
        try:
            return path.relative_to(base.resolve()).as_posix()
        except ValueError:
            return path.name
    return value


def copy_png_without_metadata(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        cleaned = image.copy()
    destination.parent.mkdir(parents=True, exist_ok=True)
    cleaned.save(destination, format="PNG", optimize=True)


def export(run_dir: Path, output_dir: Path) -> None:
    run_dir = run_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "figure_plan.json").read_text(encoding="utf-8"))
    layout = str(manifest["selected_layout"])
    stem = f"figureflow_{layout.replace('-', '_')}"
    selected_dir = run_dir / "candidates" / layout
    first_key = str(plan["stages"][0]["asset_key"])

    (output_dir / "figure_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    copy_png_without_metadata(selected_dir / f"{stem}.png", output_dir / "figureflow_live.png")
    shutil.copyfile(selected_dir / f"{stem}.svg", output_dir / "figureflow_live.svg")
    shutil.copyfile(selected_dir / f"{stem}.pdf", output_dir / "figureflow_live.pdf")
    copy_png_without_metadata(run_dir / "assets" / "asset_pipeline.png", output_dir / "asset_pipeline.png")
    copy_png_without_metadata(
        run_dir / "assets" / "raw" / f"{first_key}.png",
        output_dir / "live_icon_raw.png",
    )
    copy_png_without_metadata(
        run_dir / "assets" / "processed" / f"{first_key}.png",
        output_dir / "live_icon_processed.png",
    )

    public_manifest = scrub(manifest, base=run_dir)
    public_manifest["public_export"] = True
    public_manifest["public_export_notice"] = (
        "Response identifiers, token counts, serving route, raw prompt and absolute paths are not retained."
    )
    public_manifest["planning"] = {
        "mode": manifest.get("planning", {}).get("mode"),
        "requested_mode": manifest.get("planning", {}).get("requested_mode"),
        "model": manifest.get("planning", {}).get("model"),
    }
    public_manifest["assets"] = [
        {
            "key": item.get("key"),
            "source": item.get("source"),
            "generation_ms": item.get("generation_ms"),
            "cutout_ms": item.get("cutout_ms"),
        }
        for item in manifest.get("assets", [])
    ]
    if isinstance(public_manifest.get("live_icon"), dict):
        public_manifest["live_icon"].pop("response_id", None)
    artifact_names = (
        "figure_plan.json",
        "figureflow_live.png",
        "figureflow_live.svg",
        "figureflow_live.pdf",
        "asset_pipeline.png",
        "live_icon_raw.png",
        "live_icon_processed.png",
    )
    public_manifest["artifacts"] = {
        name: sha256(output_dir / name) for name in artifact_names
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(public_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        "# GPT-5.6-sol 在线示例\n\n"
        "该目录来自一次真实 `gpt-5.6-sol` 语义规划与一次 `gpt-image-2` 无文字 Icon 生成。"
        "仓库代码仍使用官方 OpenAI Responses API 与默认 URL；本公开样例不记录实际服务路由、"
        "响应标识、token 数、原始提示词或绝对路径。\n\n"
        "证据状态为 `implemented`：它证明工作流已经执行并通过三布局 QA，不证明团队提效比例。"
        "提效结论仍需按 `benchmark/` 的三方法同任务协议实测。\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    export(args.run_dir, args.output_dir)


if __name__ == "__main__":
    main()
