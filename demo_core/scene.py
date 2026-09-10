"""Safe declarative renderer for model-authored paper-figure scenes.

The scene is plain JSON-compatible data.  Geometry is never inferred: canvas,
panels, asset bounds, text boxes, ports, and edge paths are explicit.  The
renderer deliberately supports a small vocabulary rather than executing model
code or accepting arbitrary SVG fragments.
"""

from __future__ import annotations

import base64
import html
import math
import mimetypes
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .math_svg import MathSVGError, compile_math_svg
from .svg_assets import SVGAssetError, inspect_svg, raster_preview, safe_svg_bytes


ITEM_TYPES = {"shape", "text", "image", "formula", "edge"}
SHAPES = {"rect", "ellipse", "polygon", "line"}
FITS = {"contain", "cover", "stretch"}
SEVERITIES = {"error", "warning"}


class SceneError(ValueError):
    """Raised when a scene violates the finite, non-executable schema."""


@lru_cache(maxsize=64)
def _resolve_font(font_family: str, font_weight: str) -> tuple[str, str, bool]:
    requested = font_family.split(",", 1)[0].strip().strip("'\"") or "Arial"
    weight = "Bold" if font_weight == "bold" else "Regular"
    query = f"{requested}:style={weight}"
    try:
        found = subprocess.run(["fc-match", "-f", "%{file}\n%{family}\n", query], check=True,
                               capture_output=True, text=True, timeout=3).stdout.splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        raise SceneError("fontconfig is required for deterministic SVG font resolution") from exc
    if len(found) < 2 or not Path(found[0]).is_file():
        raise SceneError(f"font is unavailable: {requested}")
    actual = found[1].split(",", 1)[0]
    substituted = actual.casefold() != requested.casefold()
    if substituted:
        fallback = subprocess.run(["fc-match", "-f", "%{file}\n%{family}\n", "Arial Unicode MS"], check=True,
                                  capture_output=True, text=True, timeout=3).stdout.splitlines()
        if len(fallback) >= 2 and Path(fallback[0]).is_file():
            found, actual = fallback, fallback[1].split(",", 1)[0]
    return found[0], actual, substituted


def _font_info(font_family: str, font_weight: int | str) -> tuple[str, str, bool]:
    weight = "bold" if str(font_weight).lower() in {"bold", "600", "700", "800", "900"} else "normal"
    return _resolve_font(font_family, weight)


def font_environment() -> dict[str, Any]:
    """Return stable family names that both fontconfig/Cairo and QA can resolve.

    Paths are intentionally omitted so this can be exposed directly to a model.
    Choosing one of ``available_families`` prevents a substitution warning.
    """
    preferred = ["Arial Unicode MS", "Arial", "Helvetica", "Times New Roman", "Courier New"]
    available: list[str] = []
    for family in preferred:
        _, actual, substituted = _resolve_font(family, "normal")
        if not substituted and actual not in available:
            available.append(actual)
    if not available:
        _, actual, _ = _resolve_font("sans-serif", "normal")
        available.append(actual)
    recommended = "Arial Unicode MS" if "Arial Unicode MS" in available else available[0]
    return {"recommended_family": recommended, "available_families": available}


def measure_text(text: str, font_size: float, font_family: str = "Arial", font_weight: int | str = 400,
                 line_height: float = 1.2) -> tuple[float, float]:
    """Measure explicit lines with the installed font requested by the scene."""
    from PIL import ImageFont

    path, _, _ = _font_info(font_family, font_weight)
    requested = _number(font_size, "font_size")
    pixel_size = max(1, round(requested))
    font = ImageFont.truetype(path, pixel_size)
    scale = requested / pixel_size
    lines = text.splitlines() or [""]
    return max((font.getlength(line) * scale for line in lines), default=0.0), len(lines) * requested * _number(line_height, "line_height")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SceneError(f"{label} must be a finite number")
    return float(value)


def _box(value: Any, label: str) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise SceneError(f"{label} must be [x, y, width, height]")
    x, y, w, h = (_number(v, label) for v in value)
    if w <= 0 or h <= 0:
        raise SceneError(f"{label} width and height must be positive")
    return x, y, w, h


def _point(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SceneError(f"{label} must be [x, y]")
    return _number(value[0], label), _number(value[1], label)


def _color(value: Any, label: str, *, allow_none: bool = True) -> str:
    if value is None and allow_none:
        return "none"
    if not isinstance(value, str) or not value or len(value) > 80:
        raise SceneError(f"{label} must be a short CSS color")
    if re.fullmatch(r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})", value) or re.fullmatch(r"[A-Za-z]+", value):
        return value
    function = re.fullmatch(r"(rgba?|hsla?)\(([^()]*)\)", value)
    if not function:
        raise SceneError(f"{label} must be hex, a named color, rgb(a), or hsl(a)")
    name, body = function.groups()
    parts = [part.strip() for part in body.split(",")]
    expected = 4 if name in {"rgba", "hsla"} else 3
    if len(parts) != expected:
        raise SceneError(f"{label} has the wrong number of color components")
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    if name.startswith("rgb"):
        if not all(re.fullmatch(number + r"%?", part) for part in parts[:3]):
            raise SceneError(f"{label} has invalid RGB components")
        for part in parts[:3]:
            limit = 100 if part.endswith("%") else 255
            if not 0 <= float(part.rstrip("%")) <= limit:
                raise SceneError(f"{label} RGB component is out of range")
    else:
        if not re.fullmatch(number + r"(?:deg)?", parts[0]) or not all(
            re.fullmatch(number + r"%", part) for part in parts[1:3]
        ) or not all(0 <= float(part.rstrip("%")) <= 100 for part in parts[1:3]):
            raise SceneError(f"{label} has invalid HSL components")
    if expected == 4 and (not re.fullmatch(number + r"%?", parts[3]) or not 0 <= float(parts[3].rstrip("%")) <= (100 if parts[3].endswith("%") else 1)):
        raise SceneError(f"{label} alpha component is out of range")
    return value


def _style(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("style", {})
    if not isinstance(raw, dict):
        raise SceneError("style must be an object")
    allowed = {
        "fill", "stroke", "stroke_width", "dash", "opacity", "radius",
        "font_family", "font_weight", "font_style", "text_anchor", "line_height", "color",
    }
    extra = set(raw) - allowed
    if extra:
        raise SceneError(f"unsupported style keys: {sorted(extra)}")
    return raw


def _item_bounds(item: dict[str, Any]) -> tuple[float, float, float, float]:
    if item["type"] == "edge":
        points = _edge_points(item)
        xs, ys = zip(*points)
        pad = float(item.get("style", {}).get("stroke_width", 2)) / 2 + (8 if item.get("arrow_end") else 0)
        return min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad
    if "bounds" in item:
        return _box(item["bounds"], f"{item['id']}.bounds")
    raise SceneError(f"{item['id']} requires bounds")


def _edge_points(item: dict[str, Any]) -> list[tuple[float, float]]:
    if "points" in item:
        points = [_point(p, f"{item['id']}.points") for p in item["points"]]
        if len(points) < 2:
            raise SceneError(f"{item['id']}.points requires at least two points")
        return points
    curve = item.get("curve")
    if not isinstance(curve, (list, tuple)) or len(curve) != 4:
        raise SceneError(f"{item['id']} requires points or a four-point cubic curve")
    return [_point(p, f"{item['id']}.curve") for p in curve]


def validate_scene(scene: dict[str, Any], *, base_dir: str | Path | None = None) -> dict[str, Any]:
    """Validate schema and actual authored geometry; return a structured QA report.

    Errors are objective delivery failures (invalid schema, crop overflow, or
    undersized type).  Warnings expose possible visual ambiguity (edge through
    protected content, edge crossings, crowded arrowheads) without preventing a
    model from submitting and redesigning a candidate.
    """
    if not isinstance(scene, dict):
        raise SceneError("scene must be an object")
    allowed_top = {"version", "canvas", "items", "metadata", "qa"}
    if set(scene) - allowed_top:
        raise SceneError(f"unsupported scene keys: {sorted(set(scene) - allowed_top)}")
    if scene.get("version", 1) != 1:
        raise SceneError("only scene version 1 is supported")
    canvas = scene.get("canvas")
    if not isinstance(canvas, dict):
        raise SceneError("canvas must be an object")
    width = _number(canvas.get("width"), "canvas.width")
    height = _number(canvas.get("height"), "canvas.height")
    if min(width, height) < 1 or max(width, height) > 16384 or width * height > 16_777_216:
        raise SceneError("canvas dimensions must be 1–16384 with at most 16 megapixels")
    include_width_pt = _number(canvas.get("include_width_pt", width), "canvas.include_width_pt")
    min_font_pt = _number(scene.get("qa", {}).get("min_font_pt", 6.5), "qa.min_font_pt")
    parent_padding = _number(scene.get("qa", {}).get("parent_padding", 8), "qa.parent_padding")
    if parent_padding < 0:
        raise SceneError("qa.parent_padding must be nonnegative")
    margin = _number(scene.get("qa", {}).get("margin", 0), "qa.margin")
    items = scene.get("items")
    if not isinstance(items, list) or not items or len(items) > 2000:
        raise SceneError("items must be a non-empty array with at most 2000 entries")
    ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SceneError(f"items[{index}] must be an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,99}", item_id):
            raise SceneError(f"items[{index}].id must be a safe SVG identifier")
        if item_id in ids:
            raise SceneError(f"duplicate item id: {item_id}")
        ids.add(item_id)
        if item.get("type") not in ITEM_TYPES:
            raise SceneError(f"{item_id}.type must be one of {sorted(ITEM_TYPES)}")
        common = {"id", "type", "z", "bounds", "style", "protect", "parent"}
        specific = {
            "shape": {"shape", "points"},
            "text": {"text", "font_size"},
            "image": {"source", "fit", "asset_bounds"},
            "formula": {"latex", "text"},
            "edge": {"points", "curve", "source", "target", "source_port", "target_port", "arrow_end"},
        }[item["type"]]
        if set(item) - common - specific:
            raise SceneError(f"{item_id} has unsupported keys: {sorted(set(item) - common - specific)}")
        _style(item)
        if item["type"] != "edge":
            _item_bounds(item)
        if item["type"] == "shape" and item.get("shape", "rect") not in SHAPES:
            raise SceneError(f"{item_id}.shape must be one of {sorted(SHAPES)}")
        if item["type"] == "shape" and item.get("shape") == "polygon":
            points = item.get("points")
            if not isinstance(points, list) or len(points) < 3:
                raise SceneError(f"{item_id}.points needs at least three polygon points")
            bx, by, bw, bh = _item_bounds(item)
            if any(not (bx <= px <= bx + bw and by <= py <= by + bh)
                   for px, py in (_point(point, f"{item_id}.points") for point in points)):
                raise SceneError(f"{item_id}.points must lie inside declared bounds")
        if item["type"] in {"text", "formula"} and not isinstance(item.get("text", ""), str):
            raise SceneError(f"{item_id}.text must be a string")
        if item["type"] == "formula" and not isinstance(item.get("latex"), str):
            raise SceneError(f"{item_id}.latex must be a MathText formula string")
        if item["type"] == "image":
            source = item.get("source")
            if not isinstance(source, str) or not source:
                raise SceneError(f"{item_id}.source must be a local path or data URI")
            if "://" in source and not source.startswith("data:image/"):
                raise SceneError(f"{item_id}.source may not be a remote URL")
            if source.startswith("data:image/"):
                _image_href(source, None)
            elif Path(source).suffix.lower() == ".svg":
                try:
                    inspect_svg(_asset_path(source, base_dir),
                                color=item.get("style", {}).get("color", "#000000"))
                except SVGAssetError as exc:
                    raise SceneError(f"{item_id}: {exc}") from exc
            if item.get("fit", "contain") not in FITS:
                raise SceneError(f"{item_id}.fit must be one of {sorted(FITS)}")
            if "asset_bounds" in item:
                ax, ay, aw, ah = _box(item["asset_bounds"], f"{item_id}.asset_bounds")
                _, _, bw, bh = _item_bounds(item)
                if ax < 0 or ay < 0 or ax + aw > bw or ay + ah > bh:
                    raise SceneError(f"{item_id}.asset_bounds must lie inside item bounds")
        if item["type"] == "edge":
            if "bounds" in item:
                raise SceneError(f"{item_id}.bounds is not allowed; edge bounds come from its path")
            _edge_points(item)
            for port_name in ("source_port", "target_port"):
                if port_name in item:
                    _point(item[port_name], f"{item_id}.{port_name}")
        normalized.append(item)

    by_id = {item["id"]: item for item in normalized}
    for item in normalized:
        parent_id = item.get("parent")
        if parent_id is None:
            continue
        parent = by_id.get(parent_id)
        if parent is None or parent["type"] != "shape" or parent_id == item["id"]:
            raise SceneError(f"{item['id']}.parent must reference a different shape item")
        seen = {item["id"]}
        cursor = parent
        while cursor.get("parent") is not None:
            next_id = cursor["parent"]
            if next_id in seen:
                raise SceneError(f"parent cycle contains {next_id}")
            seen.add(next_id)
            cursor = by_id.get(next_id)
            if cursor is None or cursor["type"] != "shape":
                raise SceneError(f"{parent_id} parent chain must contain only existing shapes")

    issues: list[dict[str, Any]] = []
    bounds = {item["id"]: (_image_visible_bounds(item, base_dir) if item["type"] == "image" and base_dir else _item_bounds(item))
              for item in normalized}
    for item in normalized:
        if item.get("parent") and not _box_contains(bounds[item["parent"]], bounds[item["id"]], parent_padding):
            issues.append({"severity": "error", "code": "child_outside_parent", "item": item["id"],
                           "parent": item["parent"], "padding": parent_padding})
    for item in normalized:
        x, y, w, h = bounds[item["id"]]
        if x < margin or y < margin or x + w > width - margin or y + h > height - margin:
            issues.append({"severity": "error", "code": "outside_canvas", "item": item["id"]})
        if item["type"] == "text":
            size = _number(item.get("font_size"), f"{item['id']}.font_size")
            final_pt = size * include_width_pt / width
            if final_pt < min_font_pt:
                issues.append({"severity": "error", "code": "font_below_minimum", "item": item["id"],
                               "final_pt": round(final_pt, 3), "minimum_pt": min_font_pt})
            line_height = float(item.get("style", {}).get("line_height", 1.2))
            measured_w, measured_h = measure_text(item.get("text", ""), size,
                                                   item.get("style", {}).get("font_family", "Arial"),
                                                   item.get("style", {}).get("font_weight", 400), line_height)
            if measured_w > w or measured_h > h:
                issues.append({"severity": "error", "code": "text_overflow", "item": item["id"],
                               "measured": [round(measured_w, 2), round(measured_h, 2)], "bounds": [w, h]})
            font_path, actual_family, substituted = _font_info(
                item.get("style", {}).get("font_family", "Arial"), item.get("style", {}).get("font_weight", 400))
            if substituted:
                issues.append({"severity": "warning", "code": "font_substituted", "item": item["id"],
                               "actual_family": actual_family})
            if _missing_glyphs(font_path, item.get("text", "")):
                issues.append({"severity": "error", "code": "missing_glyphs", "item": item["id"],
                               "characters": _missing_glyphs(font_path, item.get("text", ""))})
        if item["type"] == "formula":
            try:
                viewbox, _ = compile_math_svg(item["latex"], prefix=item["id"])
                _, _, vw, vh = map(float, viewbox.split())
                formula_pt = 10.0 * min(w / vw, h / vh) * include_width_pt / width
                if formula_pt < min_font_pt:
                    issues.append({"severity": "error", "code": "formula_below_minimum", "item": item["id"],
                                   "final_pt": round(formula_pt, 3), "minimum_pt": min_font_pt})
            except MathSVGError as exc:
                issues.append({"severity": "error", "code": "formula_unsupported", "item": item["id"],
                               "message": str(exc)})

    content = [item for item in normalized if item["type"] in {"text", "image", "formula"}]
    for index, first in enumerate(content):
        for second in content[index + 1:]:
            if _boxes_overlap(bounds[first["id"]], bounds[second["id"]]):
                issues.append({"severity": "error", "code": "content_overlap",
                               "items": [first["id"], second["id"]]})

    protected = [item for item in normalized if item["type"] in {"text", "image", "formula"} or item.get("protect")]
    edges = [item for item in normalized if item["type"] == "edge"]
    for edge in edges:
        samples = _sample_edge(edge)
        for endpoint_name, point in (("source", samples[0]), ("target", samples[-1])):
            endpoint = edge.get(endpoint_name)
            if endpoint is not None:
                owner = next((item for item in normalized if item["id"] == endpoint), None)
                if owner is None or owner["type"] != "shape":
                    issues.append({"severity": "error", "code": "invalid_edge_endpoint", "item": edge["id"],
                                   "endpoint": endpoint_name})
                elif not _on_box_boundary(point, bounds[endpoint]):
                    issues.append({"severity": "error", "code": "endpoint_not_on_shape", "item": edge["id"],
                                   "endpoint": endpoint_name})
        for obstacle in protected:
            stroke_pad = float(edge.get("style", {}).get("stroke_width", 2)) / 2
            if any(_segment_hits_box(a, b, bounds[obstacle["id"]], stroke_pad) for a, b in zip(samples, samples[1:])):
                issues.append({"severity": "error", "code": "edge_crosses_content", "item": edge["id"],
                               "obstacle": obstacle["id"]})
            if edge.get("arrow_end", True) and _boxes_overlap(_arrowhead_bounds(edge), bounds[obstacle["id"]]):
                issues.append({"severity": "error", "code": "arrowhead_overlaps_content", "item": edge["id"],
                               "obstacle": obstacle["id"]})
        if edge.get("source_port") and _distance(samples[0], _point(edge["source_port"], "source_port")) > 0.5:
            issues.append({"severity": "warning", "code": "source_port_mismatch", "item": edge["id"]})
        if edge.get("target_port") and _distance(samples[-1], _point(edge["target_port"], "target_port")) > 0.5:
            issues.append({"severity": "warning", "code": "target_port_mismatch", "item": edge["id"]})
    for index, first in enumerate(edges):
        for second in edges[index + 1:]:
            if _polyline_crosses(_sample_edge(first), _sample_edge(second)):
                issues.append({"severity": "warning", "code": "edge_crossing", "items": [first["id"], second["id"]]})
    return {
        "ok": not issues,
        "renderable": not any(issue["severity"] == "error" for issue in issues),
        "canvas": [width, height],
        "item_bounds": {key: list(value) for key, value in bounds.items()},
        "issues": issues,
        "counts": {severity: sum(i["severity"] == severity for i in issues) for severity in SEVERITIES},
    }


def _inside(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    x, y = point
    bx, by, bw, bh = box
    return bx < x < bx + bw and by < y < by + bh


@lru_cache(maxsize=64)
def _font_cmap(font_path: str) -> frozenset[int]:
    from fontTools.ttLib import TTCollection, TTFont

    if font_path.lower().endswith(".ttc"):
        collection = TTCollection(font_path)
        try:
            codes = {code for font in collection.fonts for table in font["cmap"].tables for code in table.cmap}
        finally:
            collection.close()
    else:
        font = TTFont(font_path)
        try:
            codes = {code for table in font["cmap"].tables for code in table.cmap}
        finally:
            font.close()
    return frozenset(codes)


def _missing_glyphs(font_path: str, text: str) -> list[str]:
    cmap = _font_cmap(font_path)
    return sorted({character for character in text if not character.isspace() and ord(character) not in cmap})


def _on_box_boundary(point: tuple[float, float], box: tuple[float, float, float, float], tolerance: float = 1.0) -> bool:
    x, y = point; bx, by, bw, bh = box
    inside_span = bx - tolerance <= x <= bx + bw + tolerance and by - tolerance <= y <= by + bh + tolerance
    return inside_span and min(abs(x-bx), abs(x-bx-bw), abs(y-by), abs(y-by-bh)) <= tolerance


def _segment_hits_box(a: tuple[float, float], b: tuple[float, float], box: tuple[float, float, float, float], pad: float = 0) -> bool:
    """Exact segment/AABB intersection using Liang-Barsky clipping."""
    x, y, w, h = box; left, right, top, bottom = x-pad, x+w+pad, y-pad, y+h+pad
    dx, dy = b[0]-a[0], b[1]-a[1]
    start, end = 0.0, 1.0
    for p, q in ((-dx, a[0]-left), (dx, right-a[0]), (-dy, a[1]-top), (dy, bottom-a[1])):
        if abs(p) < 1e-12:
            if q < 0: return False
        else:
            ratio = q / p
            if p < 0: start = max(start, ratio)
            else: end = min(end, ratio)
            if start > end: return False
    return True


def _boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


def _box_contains(parent: tuple[float, float, float, float], child: tuple[float, float, float, float], padding: float) -> bool:
    px, py, pw, ph = parent; cx, cy, cw, ch = child
    return (cx >= px + padding and cy >= py + padding and
            cx + cw <= px + pw - padding and cy + ch <= py + ph - padding)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _arrowhead_bounds(item: dict[str, Any]) -> tuple[float, float, float, float]:
    points = _sample_edge(item)
    tip, previous = points[-1], points[-2]
    length = max(8.0, float(item.get("style", {}).get("stroke_width", 2)) * 7.0)
    angle = math.atan2(tip[1] - previous[1], tip[0] - previous[0])
    base = (tip[0] - length * math.cos(angle), tip[1] - length * math.sin(angle))
    half = length * 0.5
    corners = [tip, (base[0] + half * math.sin(angle), base[1] - half * math.cos(angle)),
               (base[0] - half * math.sin(angle), base[1] + half * math.cos(angle))]
    xs, ys = zip(*corners)
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _sample_edge(item: dict[str, Any]) -> list[tuple[float, float]]:
    points = _edge_points(item)
    if "points" in item:
        return points
    p0, p1, p2, p3 = points
    result = [p0]
    def flatten(a, b, c, d, depth=0):
        chord = max(_distance(a, d), 1e-9)
        deviation = max(abs((d[0]-a[0])*(p[1]-a[1])-(d[1]-a[1])*(p[0]-a[0]))/chord for p in (b, c))
        if deviation <= 0.35 or depth >= 14:
            result.append(d); return
        ab=((a[0]+b[0])/2,(a[1]+b[1])/2); bc=((b[0]+c[0])/2,(b[1]+c[1])/2); cd=((c[0]+d[0])/2,(c[1]+d[1])/2)
        abc=((ab[0]+bc[0])/2,(ab[1]+bc[1])/2); bcd=((bc[0]+cd[0])/2,(bc[1]+cd[1])/2); mid=((abc[0]+bcd[0])/2,(abc[1]+bcd[1])/2)
        flatten(a,ab,abc,mid,depth+1); flatten(mid,bcd,cd,d,depth+1)
    flatten(p0,p1,p2,p3)
    return result


def _polyline_crosses(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> bool:
    def orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    for a, b in zip(first, first[1:]):
        for c, d in zip(second, second[1:]):
            if orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0:
                return True
    return False


def _attrs(values: dict[str, Any]) -> str:
    return " ".join(f'{key.replace("_", "-")}="{html.escape(str(value), quote=True)}"' for key, value in values.items())


def _style_attrs(item: dict[str, Any]) -> dict[str, Any]:
    style = _style(item)
    result = {
        "fill": _color(style.get("fill"), "fill"),
        "stroke": _color(style.get("stroke"), "stroke"),
        "stroke-width": _number(style.get("stroke_width", 0), "stroke_width"),
        "opacity": _number(style.get("opacity", 1), "opacity"),
    }
    if style.get("dash"):
        result["stroke-dasharray"] = " ".join(str(_number(v, "dash")) for v in style["dash"])
    return result


def render_svg(scene: dict[str, Any], *, base_dir: str | Path | None = None) -> tuple[str, dict[str, Any]]:
    """Return editable SVG and QA; embed validated local vectors/raster assets."""
    qa = validate_scene(scene, base_dir=base_dir)
    canvas = scene["canvas"]
    width, height = canvas["width"], canvas["height"]
    background = _color(canvas.get("background", "#ffffff"), "canvas.background", allow_none=False)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {width} {height}">',
             f'<rect width="{width}" height="{height}" fill="{html.escape(background)}"/>']
    ordered = sorted(enumerate(scene["items"]), key=lambda pair: (pair[1].get("z", 0), pair[0]))
    for _, item in ordered:
        item_id, kind = html.escape(item["id"], quote=True), item["type"]
        style = _style_attrs(item)
        if kind == "shape":
            x, y, w, h = _item_bounds(item); shape = item.get("shape", "rect")
            if shape == "rect":
                style["rx"] = _number(item.get("style", {}).get("radius", 0), "radius")
                parts.append(f'<rect id="{item_id}" x="{x}" y="{y}" width="{w}" height="{h}" {_attrs(style)}/>')
            elif shape == "ellipse":
                parts.append(f'<ellipse id="{item_id}" cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" {_attrs(style)}/>')
            elif shape == "line":
                parts.append(f'<line id="{item_id}" x1="{x}" y1="{y}" x2="{x+w}" y2="{y+h}" {_attrs(style)}/>')
            else:
                points = item.get("points")
                if not isinstance(points, list) or len(points) < 3:
                    raise SceneError(f"{item['id']}.points needs at least three polygon points")
                value = " ".join(f"{x},{y}" for x, y in (_point(p, "polygon point") for p in points))
                parts.append(f'<polygon id="{item_id}" points="{value}" {_attrs(style)}/>')
        elif kind == "text":
            x, y, w, h = _item_bounds(item); size = _number(item["font_size"], "font_size")
            raw_style = _style(item); anchor = raw_style.get("text_anchor", "start")
            _, actual_family, _ = _font_info(raw_style.get("font_family", "Arial"), raw_style.get("font_weight", 400))
            tx = x if anchor == "start" else x + w / 2 if anchor == "middle" else x + w
            attrs = {"fill": _color(raw_style.get("fill", "#111827"), "text fill", allow_none=False),
                     "font-family": actual_family, "font-size": size,
                     "font-weight": raw_style.get("font_weight", 400), "font-style": raw_style.get("font_style", "normal"),
                     "text-anchor": anchor}
            line_height = float(raw_style.get("line_height", 1.2)) * size
            tspans = "".join(f'<tspan x="{tx}" y="{y + size + i*line_height}">{html.escape(line)}</tspan>'
                             for i, line in enumerate(item.get("text", "").splitlines() or [""]))
            parts.append(f'<text id="{item_id}" {_attrs(attrs)}>{tspans}</text>')
        elif kind == "image":
            x, y, w, h = _item_bounds(item)
            fit = {"contain": "xMidYMid meet", "cover": "xMidYMid slice", "stretch": "none"}[item.get("fit", "contain")]
            ax, ay, aw, ah = item.get("asset_bounds", [0, 0, w, h])
            if not item["source"].startswith("data:") and Path(item["source"]).suffix.lower() == ".svg":
                try:
                    source = _asset_path(item["source"], base_dir)
                    color = item.get("style", {}).get("color", "#000000")
                    info = inspect_svg(source, color=color)
                    # Reserve a prefix that no scene-owned item/arrow can use.
                    # Assets may all contain the same upstream definition ids.
                    prefix = f"ffasset{_}"
                    while any(other["id"] == prefix or other["id"].startswith(prefix + "-")
                              for other in scene["items"]):
                        prefix += "x"
                    content = safe_svg_bytes(source, prefix=prefix, color=color).decode("utf-8")
                except SVGAssetError as exc:
                    raise SceneError(f"{item_id}: {exc}") from exc
                parts.append(f'<svg id="{item_id}" x="{x+ax}" y="{y+ay}" width="{aw}" height="{ah}" '
                             f'viewBox="0 0 {info["width"]} {info["height"]}" preserveAspectRatio="{fit}" '
                             f'overflow="hidden">{content}</svg>')
            else:
                href = _image_href(item["source"], base_dir)
                parts.append(f'<image id="{item_id}" x="{x+ax}" y="{y+ay}" width="{aw}" height="{ah}" preserveAspectRatio="{fit}" href="{html.escape(href, quote=True)}"/>')
        elif kind == "formula":
            x, y, w, h = _item_bounds(item)
            try:
                view, paths = compile_math_svg(item["latex"], prefix=item["id"])
            except MathSVGError:
                view, paths = f"0 0 {w} {h}", f'<rect width="{w}" height="{h}" fill="#fee2e2"/>'
            fill = _color(item.get("style", {}).get("fill", "#111827"), "formula fill", allow_none=False)
            parts.append(f'<svg id="{item_id}" x="{x}" y="{y}" width="{w}" height="{h}" viewBox="{view}" fill="{fill}">{paths}</svg>')
        else:
            points = _edge_points(item)
            d = ("M " + " L ".join(f"{x} {y}" for x, y in points)) if "points" in item else (
                f"M {points[0][0]} {points[0][1]} C {points[1][0]} {points[1][1]} {points[2][0]} {points[2][1]} {points[3][0]} {points[3][1]}")
            style["fill"] = "none"
            if item.get("arrow_end", True):
                marker_id = f"scene-arrow-{item_id}"
                marker_color = style.get("stroke", "#111827")
                parts.append(f'<defs><marker id="{marker_id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10Z" fill="{marker_color}"/></marker></defs>')
                style["marker-end"] = f"url(#{marker_id})"
            parts.append(f'<path id="{item_id}" d="{d}" {_attrs(style)}/>')
    parts.append("</svg>")
    return "".join(parts), qa


def _asset_path(source: str, base_dir: str | Path | None) -> Path:
    """Resolve local assets inside their registered directory, including symlinks."""
    if base_dir is None:
        raise SceneError("base_dir is required for local image assets")
    root = Path(base_dir).resolve()
    path = Path(source)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if path != root and root not in path.parents:
        raise SceneError("image source is outside the registered asset directory")
    if not path.is_file():
        raise SceneError("image source is not a readable local file")
    return path


def _image_href(source: str, base_dir: str | Path | None) -> str:
    if source.startswith("data:image/"):
        match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]*={0,2})", source)
        if not match:
            raise SceneError("image data URI must be base64 PNG, JPEG, or WebP")
        if len(match.group(2)) > (25 * 1024 * 1024 + 2) * 4 // 3:
            raise SceneError("image asset exceeds 25 MB")
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except Exception as exc:
            raise SceneError("image data URI contains invalid base64") from exc
        _validate_raster(data, match.group(1))
        return source
    path = _asset_path(source, base_dir)
    if path.stat().st_size > 25 * 1024 * 1024:
        raise SceneError("image asset exceeds 25 MB")
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    expected = {"image/png": "png", "image/jpeg": "jpeg", "image/webp": "webp"}.get(mime)
    if expected is None:
        raise SceneError("image source must be PNG, JPEG, or WebP")
    _validate_raster(data, expected)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _validate_raster(data: bytes, expected: str) -> None:
    import io
    from PIL import Image

    if len(data) > 25 * 1024 * 1024:
        raise SceneError("image asset exceeds 25 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            actual = (image.format or "").lower()
    except Exception as exc:
        raise SceneError("image asset is not a valid raster") from exc
    if actual == "jpg":
        actual = "jpeg"
    if actual != expected:
        raise SceneError(f"image data does not match declared {expected.upper()} format")


def _image_visible_bounds(item: dict[str, Any], base_dir: str | Path) -> tuple[float, float, float, float]:
    """Map raster or safe SVG preview alpha bounds into authored coordinates."""
    import io
    from PIL import Image

    source = item["source"]
    if source.startswith("data:image/"):
        try:
            payload = base64.b64decode(source.split(",", 1)[1], validate=True)
        except Exception as exc:
            raise SceneError("invalid image data URI") from exc
    elif Path(source).suffix.lower() == ".svg":
        try:
            payload = raster_preview(_asset_path(source, base_dir),
                                     color=item.get("style", {}).get("color", "#000000"))
        except SVGAssetError as exc:
            raise SceneError(f"{item['id']}: {exc}") from exc
    else:
        payload = base64.b64decode(_image_href(source, base_dir).split(",", 1)[1])
    with Image.open(io.BytesIO(payload)) as image:
        rgba = image.convert("RGBA")
        alpha_bbox = rgba.getchannel("A").getbbox()
        iw, ih = rgba.size
    x, y, w, h = _item_bounds(item)
    ax, ay, aw, ah = item.get("asset_bounds", [0, 0, w, h])
    x, y, w, h = x + ax, y + ay, aw, ah
    if alpha_bbox is None:
        return x, y, 0.0, 0.0
    left, top, right, bottom = alpha_bbox
    fit = item.get("fit", "contain")
    if fit == "stretch":
        sx, sy, ox, oy = w / iw, h / ih, x, y
    else:
        scale = min(w / iw, h / ih) if fit == "contain" else max(w / iw, h / ih)
        sx = sy = scale
        ox, oy = x + (w - iw * scale) / 2, y + (h - ih * scale) / 2
    vx, vy = max(x, ox + left * sx), max(y, oy + top * sy)
    vr, vb = min(x + w, ox + right * sx), min(y + h, oy + bottom * sy)
    return vx, vy, max(0.0, vr - vx), max(0.0, vb - vy)


def render_scene(scene: dict[str, Any], output: str | Path, *, formats: Iterable[str] = ("svg",),
                 base_dir: str | Path | None = None) -> dict[str, Any]:
    """Render SVG and optional PDF/PNG; return paths plus non-blocking geometry QA."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    svg, qa = render_svg(scene, base_dir=base_dir)
    requested = set(formats)
    if not requested or requested - {"svg", "pdf", "png"}:
        raise SceneError("formats may contain only svg, pdf, and png")
    paths: dict[str, str] = {}
    if "svg" in requested:
        path = output.with_suffix(".svg"); path.write_text(svg, encoding="utf-8"); paths["svg"] = str(path)
    if requested & {"pdf", "png"}:
        from cairosvg.surface import PDFSurface, PNGSurface
        if "pdf" in requested:
            path = output.with_suffix(".pdf")
            include_pt = float(scene["canvas"].get("include_width_pt", scene["canvas"]["width"]))
            PDFSurface.convert(bytestring=svg.encode(), write_to=str(path), output_width=include_pt * 96 / 72,
                               unsafe=False, url_fetcher=_scene_asset_fetcher)
            paths["pdf"] = str(path)
        if "png" in requested:
            path = output.with_suffix(".png")
            PNGSurface.convert(bytestring=svg.encode(), write_to=str(path),
                               output_width=int(scene["canvas"]["width"]), output_height=int(scene["canvas"]["height"]),
                               unsafe=False, url_fetcher=_scene_asset_fetcher)
            paths["png"] = str(path)
    return {"paths": paths, "qa": qa, "svg": svg if "svg" not in requested else None}


def _scene_asset_fetcher(url: str, resource_type: str) -> bytes:
    """Final PNG/PDF export has the same no-network/no-file barrier as QA."""
    if not isinstance(url, str) or not url.startswith("data:image/"):
        raise SceneError("scene export may not fetch network or filesystem resources")
    _image_href(url, None)
    return base64.b64decode(url.split(",", 1)[1], validate=True)
