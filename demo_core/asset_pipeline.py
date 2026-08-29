"""Safe semantic-icon generation, chroma removal, and preview utilities."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

from .schemas import StagePlan


ROOT = Path(__file__).resolve().parents[1]
RAW_ASSET_DIR = ROOT / "assets" / "icons" / "raw"
CHROMA_SCRIPT = ROOT / "skill" / "design-research-figures" / "scripts" / "remove_chroma.py"
DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
GENERIC_ASSET_KEYS = {"data", "process", "decision", "store", "output"}


@dataclass(frozen=True)
class AssetResult:
    key: str
    raw_path: str
    processed_path: str
    manifest_path: str
    source: str
    generation_ms: int
    cutout_ms: int


class AssetPipelineError(RuntimeError):
    """Raised when a generated or bundled icon cannot be processed safely."""


def create_fallback_asset(key: str, output_path: Path) -> None:
    """Draw a transparent, text-free fallback for general SOP plans."""
    scale = 2
    size = 512
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    navy, blue, teal, orange, white = "#142B4A", "#2A6FBB", "#16827A", "#E58B2A", "#FFFFFF"

    def box(xy, *, radius=28, fill=white, outline=navy, width=12):
        draw.rounded_rectangle(tuple(value * scale for value in xy), radius=radius * scale, fill=fill, outline=outline, width=width * scale)

    if key == "data":
        box((105, 105, 407, 407), fill="#E8F2FC")
        for index, height in enumerate((88, 150, 118)):
            x = (165 + index * 76) * scale
            draw.rounded_rectangle((x, (355 - height) * scale, x + 42 * scale, 355 * scale), radius=12 * scale, fill=(blue, teal, orange)[index])
        draw.ellipse((145 * scale, 125 * scale, 365 * scale, 190 * scale), fill=white, outline=navy, width=10 * scale)
    elif key == "decision":
        draw.polygon([(256 * scale, 70 * scale), (442 * scale, 256 * scale), (256 * scale, 442 * scale), (70 * scale, 256 * scale)], fill="#FFF1DF", outline=navy)
        draw.line((170 * scale, 256 * scale, 238 * scale, 324 * scale, 350 * scale, 190 * scale), fill=teal, width=24 * scale, joint="curve")
    elif key == "store":
        draw.rectangle((118 * scale, 145 * scale, 394 * scale, 365 * scale), fill="#E8F2FC", outline=navy, width=12 * scale)
        draw.ellipse((118 * scale, 100 * scale, 394 * scale, 190 * scale), fill=white, outline=navy, width=12 * scale)
        draw.ellipse((118 * scale, 320 * scale, 394 * scale, 410 * scale), fill="#D9EAF8", outline=navy, width=12 * scale)
        draw.arc((118 * scale, 210 * scale, 394 * scale, 300 * scale), 0, 180, fill=blue, width=8 * scale)
    elif key == "output":
        box((120, 68, 392, 444), fill=white)
        draw.polygon([(310 * scale, 68 * scale), (392 * scale, 150 * scale), (310 * scale, 150 * scale)], fill="#D9EAF8", outline=navy)
        draw.ellipse((230 * scale, 238 * scale, 420 * scale, 428 * scale), fill=teal, outline=navy, width=12 * scale)
        draw.line((272 * scale, 330 * scale, 315 * scale, 370 * scale, 380 * scale, 285 * scale), fill=white, width=22 * scale, joint="curve")
    else:
        box((90, 90, 422, 422), fill="#E8F2FC")
        center = 256 * scale
        draw.ellipse((155 * scale, 155 * scale, 357 * scale, 357 * scale), fill=white, outline=navy, width=14 * scale)
        for angle in range(0, 360, 45):
            import math

            x1 = center + int(math.cos(math.radians(angle)) * 105 * scale)
            y1 = center + int(math.sin(math.radians(angle)) * 105 * scale)
            x2 = center + int(math.cos(math.radians(angle)) * 148 * scale)
            y2 = center + int(math.sin(math.radians(angle)) * 148 * scale)
            draw.line((x1, y1, x2, y2), fill=orange, width=22 * scale)
        draw.ellipse((218 * scale, 218 * scale, 294 * scale, 294 * scale), fill=blue)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.resize((size, size), Image.Resampling.LANCZOS).save(output_path, optimize=True)


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        raise AssetPipelineError(message[-1200:] or "asset processing failed")
    return completed


def generate_live_icon(stage: StagePlan, output_path: Path, *, model: str = DEFAULT_MODEL) -> dict[str, object]:
    """Generate one text-free component through the GPT-5.6-sol Responses API."""
    if not os.getenv("OPENAI_API_KEY"):
        raise AssetPipelineError("实时 Icon 生成需要服务端 OPENAI_API_KEY。")

    semantic_prompt = stage.asset_prompt or f"{stage.title}：{stage.subtitle}"
    prompt = f"""
Create one isolated semantic icon for a professional technical workflow diagram.
Meaning: {semantic_prompt}
Style: refined miniature 3D/isometric object, navy blue, cobalt, teal, warm amber and white,
soft studio lighting, crisp silhouette, restrained detail, no people.
Composition: exactly one centered object, generous empty margin, square canvas.
Background: perfectly flat solid #FF00FF magenta from edge to edge.
Strictly no letters, words, numbers, formulas, watermarks, logos, borders, or shadows outside the object.
""".strip()
    client = OpenAI(timeout=180.0, max_retries=1)
    image_model = os.getenv("OPENAI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    started = perf_counter()
    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            tools=[
                {
                    "type": "image_generation",
                    "model": image_model,
                    "quality": "medium",
                    "size": "1024x1024",
                    "background": "opaque",
                    "output_format": "png",
                }
            ],
            tool_choice={"type": "image_generation"},
            max_tool_calls=1,
            store=False,
        )
    except Exception as exc:
        raise AssetPipelineError(
            "实时 Icon 生成失败（IMAGE_REQUEST_FAILED）。请检查服务端 API 与图像模型配置。"
        ) from exc
    image_call = next(
        (
            item
            for item in response.output
            if getattr(item, "type", None) == "image_generation_call" and getattr(item, "result", None)
        ),
        None,
    )
    if image_call is None:
        raise AssetPipelineError("GPT-5.6-sol 未返回可用的图像生成结果。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(image_call.result))
    with Image.open(output_path) as image:
        image.verify()
    return {
        "response_id": getattr(response, "id", None),
        "model": model,
        "image_model": image_model,
        "prompt_template": "isolated-semantic-icon-v1",
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "generation_ms": round((perf_counter() - started) * 1000),
    }


def process_asset(raw_path: Path, output_path: Path, manifest_path: Path) -> int:
    started = perf_counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            str(CHROMA_SCRIPT),
            str(raw_path),
            str(output_path),
            "--auto-key",
            "border",
            "--transparent-distance",
            "18",
            "--opaque-distance",
            "115",
            "--despill",
            "0.92",
            "--trim",
            "--padding",
            "28",
            "--trim-threshold",
            "8",
            "--max-size",
            "720",
            "--manifest",
            str(manifest_path),
        ]
    )
    with Image.open(output_path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        if alpha.getbbox() is None:
            raise AssetPipelineError(f"{raw_path.name} became fully transparent")
    return round((perf_counter() - started) * 1000)


def prepare_assets(
    stages: list[StagePlan],
    run_dir: Path,
    *,
    live_icon: bool = False,
    model: str = DEFAULT_MODEL,
) -> tuple[list[AssetResult], dict[str, object] | None]:
    """Process whitelisted stage assets and optionally replace the first one live."""
    raw_run = run_dir / "assets" / "raw"
    processed_run = run_dir / "assets" / "processed"
    manifest_run = run_dir / "assets" / "manifests"
    unique: dict[str, StagePlan] = {}
    for stage in stages:
        unique.setdefault(stage.asset_key, stage)

    live_metadata: dict[str, object] | None = None
    live_key = next(iter(unique)) if live_icon and unique else None
    results: list[AssetResult] = []
    for key, stage in unique.items():
        source = "bundled-generated-illustration"
        generation_ms = 0
        bundled_path = RAW_ASSET_DIR / f"{key}.png"
        raw_path = raw_run / f"{key}.png"
        if key == live_key:
            live_metadata = generate_live_icon(stage, raw_path, model=model)
            generation_ms = int(live_metadata["generation_ms"])
            source = "live-openai-image-generation"
        elif bundled_path.is_file():
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled_path, raw_path)
        elif key in GENERIC_ASSET_KEYS:
            create_fallback_asset(key, raw_path)
            source = "deterministic-vector-fallback"
        if not raw_path.is_file():
            raise AssetPipelineError(f"缺少白名单素材：{key}.png")
        output_path = processed_run / f"{key}.png"
        manifest_path = manifest_run / f"{key}.json"
        cutout_ms = process_asset(raw_path, output_path, manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        edge_excess = float(manifest.get("stats", {}).get("mean_edge_key_excess", 0.0))
        if edge_excess > 25.0:
            raise AssetPipelineError(f"素材 {key} 的色边残留未通过质量门禁：{edge_excess:.1f}")
        with Image.open(output_path) as checked:
            alpha = checked.convert("RGBA").getchannel("A")
            corners = [
                alpha.getpixel((0, 0)),
                alpha.getpixel((alpha.width - 1, 0)),
                alpha.getpixel((0, alpha.height - 1)),
                alpha.getpixel((alpha.width - 1, alpha.height - 1)),
            ]
        if max(corners) > 16:
            raise AssetPipelineError(f"素材 {key} 的透明边界未通过质量门禁")
        manifest["asset_key"] = key
        manifest["source_type"] = source
        manifest["generation_ms"] = generation_ms
        if key == live_key and live_metadata:
            manifest["generation"] = live_metadata
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(
            AssetResult(
                key=key,
                raw_path=str(raw_path),
                processed_path=str(output_path),
                manifest_path=str(manifest_path),
                source=source,
                generation_ms=generation_ms,
                cutout_ms=cutout_ms,
            )
        )
    return results, live_metadata


def _checkerboard(size: tuple[int, int], cell: int = 18) -> Image.Image:
    canvas = Image.new("RGB", size, "#FFFFFF")
    draw = ImageDraw.Draw(canvas)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill="#E7ECF2")
    return canvas


def create_contact_sheet(results: list[AssetResult], output_path: Path) -> Path:
    """Create a compact raw/processed comparison used by the demo UI and video."""
    cell_w, cell_h, header_h = 360, 230, 48
    rows = max(1, len(results))
    sheet = Image.new("RGB", (cell_w * 2, header_h + rows * cell_h), "#F4F7FB")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=14)
    draw.text((16, 13), "RAW / CHROMA", fill="#142B4A", font=font)
    draw.text((cell_w + 16, 13), "SOFT MATTE / RGBA", fill="#142B4A", font=font)
    for row, result in enumerate(results):
        top = header_h + row * cell_h
        for column, path_text in enumerate((result.raw_path, result.processed_path)):
            panel = _checkerboard((cell_w - 20, cell_h - 34))
            with Image.open(path_text) as source:
                icon = source.convert("RGBA")
                icon.thumbnail((cell_w - 64, cell_h - 72), Image.Resampling.LANCZOS)
            x = (panel.width - icon.width) // 2
            y = (panel.height - icon.height) // 2
            panel.paste(icon, (x, y), icon)
            sheet.paste(panel, (column * cell_w + 10, top + 24))
        draw.text((16, top + 4), result.key, fill="#536579", font=small)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def public_asset_records(results: list[AssetResult], base: Path) -> list[dict[str, object]]:
    records = []
    for result in results:
        item = asdict(result)
        for field in ("raw_path", "processed_path", "manifest_path"):
            path = Path(str(item[field])).resolve()
            try:
                item[field] = path.relative_to(base.resolve()).as_posix()
            except ValueError:
                item[field] = path.name
        records.append(item)
    return records
