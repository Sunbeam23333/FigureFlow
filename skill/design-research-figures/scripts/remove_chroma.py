#!/usr/bin/env python3
"""Remove a solid chroma background with a soft matte and edge despill."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def parse_hex(value: str) -> np.ndarray:
    text = value.strip().removeprefix("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError("color must be a 6-digit hex value")
    try:
        return np.array([int(text[index : index + 2], 16) for index in (0, 2, 4)], dtype=np.float32)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("color must be a 6-digit hex value") from exc


def smoothstep(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 0.0, 1.0)
    return clipped * clipped * (3.0 - 2.0 * clipped)


def sample_border_key(image: Image.Image, border: int = 12) -> np.ndarray:
    """Estimate a flat key color from the outer border using a robust median."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    border = max(1, min(border, rgb.shape[0] // 4, rgb.shape[1] // 4))
    samples = np.concatenate(
        [
            rgb[:border].reshape(-1, 3),
            rgb[-border:].reshape(-1, 3),
            rgb[:, :border].reshape(-1, 3),
            rgb[:, -border:].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(samples, axis=0).astype(np.float32)


def border_alpha(image: Image.Image, border: int = 12) -> float:
    """Return the median border alpha so existing transparency is not re-keyed."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    border = max(1, min(border, rgba.shape[0] // 4, rgba.shape[1] // 4))
    samples = np.concatenate(
        [
            rgba[:border, :, 3].reshape(-1),
            rgba[-border:, :, 3].reshape(-1),
            rgba[:, :border, 3].reshape(-1),
            rgba[:, -border:, 3].reshape(-1),
        ]
    )
    return float(np.median(samples))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def remove_chroma(
    image: Image.Image,
    key: np.ndarray,
    transparent_distance: float,
    opaque_distance: float,
    despill: float,
) -> tuple[Image.Image, dict[str, float | int]]:
    if not 0 <= transparent_distance < opaque_distance <= 441.7:
        raise ValueError("require 0 <= transparent-distance < opaque-distance <= 441.7")
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    rgb = rgba[..., :3]
    original_alpha = rgba[..., 3] / 255.0
    distance = np.linalg.norm(rgb - key.reshape(1, 1, 3), axis=2)
    matte = smoothstep((distance - transparent_distance) / (opaque_distance - transparent_distance))
    alpha = original_alpha * matte

    dominant_channels = np.flatnonzero(key >= float(np.max(key)) - 8.0).tolist()
    other_channels = [index for index in range(3) if index not in dominant_channels]
    edge_strength = (matte < 0.995).astype(np.float32) * float(np.clip(despill, 0.0, 1.0))
    if other_channels:
        neutral_edge = np.max(rgb[..., other_channels], axis=2)
        shared_key_component = np.min(rgb[..., dominant_channels], axis=2)
        spill = np.maximum(shared_key_component - neutral_edge, 0.0)
        for channel in dominant_channels:
            rgb[..., channel] -= spill * edge_strength

    output = np.dstack([np.clip(rgb, 0, 255), np.clip(alpha * 255.0, 0, 255)]).astype(np.uint8)
    semitransparent = (output[..., 3] > 0) & (output[..., 3] < 255)
    visible = output[..., 3] > 0
    edge_key_excess = 0.0
    if np.any(semitransparent) and other_channels:
        edge = output[..., :3][semitransparent].astype(np.float32)
        neutral = np.max(edge[:, other_channels], axis=1)
        shared_key = np.min(edge[:, dominant_channels], axis=1)
        edge_key_excess = float(np.mean(np.maximum(shared_key - neutral, 0.0)))
    stats: dict[str, float | int] = {
        "width": int(output.shape[1]),
        "height": int(output.shape[0]),
        "transparent_pixels": int(np.count_nonzero(output[..., 3] == 0)),
        "semitransparent_pixels": int(np.count_nonzero(semitransparent)),
        "visible_pixels": int(np.count_nonzero(visible)),
        "mean_edge_key_excess": round(edge_key_excess, 4),
    }
    return Image.fromarray(output), stats


def trim_alpha(image: Image.Image, padding: int, threshold: int = 8) -> tuple[Image.Image, list[int] | None]:
    alpha_image = image.getchannel("A").filter(ImageFilter.MedianFilter(3))
    alpha = np.asarray(alpha_image)
    ys, xs = np.nonzero(alpha > threshold)
    if len(xs) == 0:
        return image, None
    left = max(0, int(xs.min()) - padding)
    top = max(0, int(ys.min()) - padding)
    right = min(image.width, int(xs.max()) + 1 + padding)
    bottom = min(image.height, int(ys.max()) + 1 + padding)
    return image.crop((left, top, right, bottom)), [left, top, right, bottom]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key", default="#00ff00", help="solid chroma color")
    parser.add_argument("--auto-key", choices=["border"], help="estimate the key from image borders")
    parser.add_argument("--border-sample", type=int, default=12)
    parser.add_argument("--transparent-distance", type=float, default=24.0)
    parser.add_argument("--opaque-distance", type=float, default=105.0)
    parser.add_argument("--despill", type=float, default=0.88)
    parser.add_argument("--trim", action="store_true", help="trim transparent borders")
    parser.add_argument("--padding", type=int, default=24)
    parser.add_argument("--trim-threshold", type=int, default=8)
    parser.add_argument("--max-size", type=int, default=0, help="downscale longest output edge; 0 keeps size")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve() if args.manifest else None
    if source == output:
        raise ValueError("input and output must be different files")
    if manifest_path is not None and manifest_path in {source, output}:
        raise ValueError("manifest must not overwrite the input or output image")
    source_hash = sha256(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_image = Image.open(source)
    existing_alpha = source_image.mode in {"RGBA", "LA"} and border_alpha(source_image, args.border_sample) < 16.0
    if args.auto_key == "border" and existing_alpha:
        key = None
        processed = source_image.convert("RGBA")
        alpha = np.asarray(processed.getchannel("A"))
        stats = {
            "width": processed.width,
            "height": processed.height,
            "transparent_pixels": int(np.count_nonzero(alpha == 0)),
            "semitransparent_pixels": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
            "visible_pixels": int(np.count_nonzero(alpha > 0)),
            "mean_edge_key_excess": 0.0,
        }
    else:
        key = sample_border_key(source_image, args.border_sample) if args.auto_key == "border" else parse_hex(args.key)
        processed, stats = remove_chroma(
            source_image,
            key,
            args.transparent_distance,
            args.opaque_distance,
            args.despill,
        )
    crop_box = None
    if args.trim:
        processed, crop_box = trim_alpha(processed, max(0, args.padding), max(0, min(254, args.trim_threshold)))
        stats["trimmed_width"] = processed.width
        stats["trimmed_height"] = processed.height
    if args.max_size > 0 and max(processed.size) > args.max_size:
        before_resize = list(processed.size)
        processed.thumbnail((args.max_size, args.max_size), Image.Resampling.LANCZOS)
        stats["pre_resize_size"] = before_resize
        stats["resized_width"] = processed.width
        stats["resized_height"] = processed.height
    processed.save(output, optimize=True)
    manifest_base = manifest_path.parent if manifest_path else output.parent
    manifest = {
        "schema_version": 1,
        "source": portable_path(source, manifest_base),
        "output": portable_path(output, manifest_base),
        "source_sha256": source_hash,
        "output_sha256": sha256(output),
        "key": None if key is None else "#" + "".join(f"{int(round(value)):02x}" for value in key),
        "key_source": "existing-alpha" if key is None else ("border-median" if args.auto_key == "border" else "explicit"),
        "transparent_distance": args.transparent_distance,
        "opaque_distance": args.opaque_distance,
        "despill": args.despill,
        "crop_box": crop_box,
        "stats": stats,
    }
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
