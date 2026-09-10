"""Bounded, non-executable SVG assets for layered scene rendering.

Supported: paths/basic shapes, groups, linear/radial gradients, clip paths,
simple class/inline presentation styles, and verified embedded PNG/JPEG/WebP.
Text, scripts, animation, use, filters, masks, external references and nested
SVG are intentionally unsupported. Keep the official asset; use an approved
PNG export when its SVG requires unsupported features. Never redraw a logo as
an approximation. Validation is not a claim about provenance or trademark use.

Every output is serialized from the validated tree; input XML is never pasted
into a scene. IDs are scoped, styles are flattened, and currentColor is fixed.
"""

from __future__ import annotations

import base64
import io
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_BYTES = 2 * 1024 * 1024
MAX_NODES = 2000
MAX_DEPTH = 32
MAX_PATH_CHARS = 128 * 1024
MAX_NUMBERS = 100000
MAX_COORD = 1_000_000
MAX_DIMENSION = 16384
MAX_PREVIEW_SIDE = 2048
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
IDENT = r"[A-Za-z_][A-Za-z0-9_.-]{0,99}"
SOURCE_IDENT = r"[^\W\d][\w.-]{0,99}"
CSS_IDENT = r"[A-Za-z_][A-Za-z0-9_-]{0,99}"
PAINT_PROPS = {"fill", "stroke", "color", "stop-color"}
PRESENTATION = PAINT_PROPS | {
    "opacity", "fill-opacity", "stroke-opacity", "stop-opacity", "stroke-width",
    "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray",
    "stroke-dashoffset", "fill-rule", "clip-rule", "clip-path",
}
GEOMETRY = {
    "svg": {"viewBox", "width", "height", "preserveAspectRatio", "version", "overflow"},
    "g": set(), "defs": set(), "path": {"d", "pathLength"},
    "rect": {"x", "y", "width", "height", "rx", "ry"},
    "circle": {"cx", "cy", "r"}, "ellipse": {"cx", "cy", "rx", "ry"},
    "line": {"x1", "y1", "x2", "y2"}, "polyline": {"points"}, "polygon": {"points"},
    "linearGradient": {"x1", "y1", "x2", "y2", "gradientUnits", "gradientTransform", "spreadMethod", "href"},
    "radialGradient": {"cx", "cy", "r", "fx", "fy", "fr", "gradientUnits", "gradientTransform", "spreadMethod", "href"},
    "stop": {"offset"}, "clipPath": {"clipPathUnits"},
    "image": {"x", "y", "width", "height", "preserveAspectRatio", "href"},
    "style": {"type"}, "title": set(), "desc": set(),
}
GRADIENTS = {"linearGradient", "radialGradient"}
SHAPES = {"g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}


class SVGAssetError(ValueError):
    """The asset is outside the bounded static SVG subset."""


def _fail(message: str) -> None:
    raise SVGAssetError(message + "; use a verified PNG export of the original asset if needed")


def _read(source: bytes | str | Path) -> bytes:
    if isinstance(source, bytes):
        data = source
    elif isinstance(source, (str, Path)):
        try:
            path = Path(source)
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                _fail("SVG must be a local file of at most 2 MiB")
            data = path.read_bytes()
        except (OSError, ValueError) as exc:
            if isinstance(exc, SVGAssetError):
                raise
            raise SVGAssetError("SVG source is not a readable local file") from exc
    else:
        _fail("SVG source must be bytes or a local path")
    if not data or len(data) > MAX_BYTES:
        _fail("SVG exceeds the 2 MiB resource budget")
    return data


def _tag(name: str) -> str:
    if name.startswith("{" + SVG_NS + "}"):
        return name.split("}", 1)[1]
    if "{" in name or ":" in name:
        _fail("foreign XML namespaces are not supported")
    return name


def _numbers(value: str, *, percent: bool = False, count: int | None = None) -> list[float]:
    pattern = NUMBER + ("%?" if percent else "")
    tokens = re.findall(pattern, value)
    if not tokens or re.sub(pattern, "", value).strip(" ,\t\r\n"):
        _fail("invalid SVG numeric value")
    if count is not None and len(tokens) != count:
        _fail("wrong number of SVG numeric components")
    result = [float(token.rstrip("%")) for token in tokens]
    if any(not math.isfinite(number) or abs(number) > MAX_COORD for number in result):
        _fail("SVG coordinate exceeds finite numeric limits")
    return result


def _length(value: str) -> float:
    match = re.fullmatch(r"(" + NUMBER + r")(px|pt|pc|in|cm|mm)?", value)
    if not match:
        _fail("SVG length must use finite absolute units")
    factor = {None: 1, "px": 1, "pt": 96 / 72, "pc": 16, "in": 96, "cm": 96 / 2.54, "mm": 96 / 25.4}[match[2]]
    result = _numbers(match[1], count=1)[0] * factor
    if not math.isfinite(result) or abs(result) > MAX_COORD:
        _fail("SVG absolute length exceeds numeric limits")
    return result


def _color(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 80:
        _fail("SVG color must be a short explicit string")
    if value in {"none", "currentColor"}:
        return value
    if re.fullmatch(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?", value):
        return value
    # Pillow supplies a finite named-color table; arbitrary CSS identifiers are
    # not accepted, nor are CSS variables, context-fill, or dynamic functions.
    from PIL import ImageColor
    if value.lower() in ImageColor.colormap or value == "transparent":
        return value
    match = re.fullmatch(r"(rgb|rgba)\(([^()]*)\)", value)
    if match:
        parts = [part.strip() for part in match[2].split(",")]
        if len(parts) == (4 if match[1] == "rgba" else 3):
            for index, part in enumerate(parts):
                number = _numbers(part, percent=True, count=1)[0]
                if not 0 <= number <= (100 if part.endswith("%") else 1 if index == 3 else 255):
                    _fail("color component is out of range")
            return value
    _fail("unsupported static SVG color")


def _declarations(text: str) -> dict[str, str]:
    if len(text) > 32768 or any(token in text for token in ("\\", "/*", "*/", "@", "!", "{", "}")):
        _fail("unsupported CSS syntax")
    result = {}
    for entry in text.split(";"):
        if not entry.strip():
            continue
        if entry.count(":") != 1:
            _fail("invalid CSS declaration")
        key, value = (part.strip() for part in entry.split(":", 1))
        if key not in PRESENTATION or not value:
            _fail("unsupported SVG style property")
        result[key] = value
    return result


def _styles(root: ET.Element) -> list[tuple[set[str], dict[str, str]]]:
    rules = []
    for node in root.iter():
        if _tag(node.tag) != "style":
            continue
        if len(node) or (node.get("type") not in {None, "text/css"}):
            _fail("unsupported stylesheet")
        text = node.text or ""
        if len(text) > 32768 or any(token in text for token in ("\\", "/*", "*/", "@")):
            _fail("unsupported stylesheet syntax")
        cursor = 0
        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
            if text[cursor:match.start()].strip():
                _fail("stylesheet must contain only simple class rules")
            selectors = [part.strip() for part in match[1].split(",")]
            if not all(re.fullmatch(r"\." + CSS_IDENT, selector) for selector in selectors):
                _fail("only simple class CSS selectors are supported")
            rules.append(({selector[1:] for selector in selectors}, _declarations(match[2])))
            cursor = match.end()
        if text[cursor:].strip() or len(rules) > 128:
            _fail("stylesheet is unsupported or too large")
    return rules


@lru_cache(maxsize=16)
def _raster(uri: str) -> bytes:
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]*={0,2})", uri)
    if not match or len(uri) > MAX_BYTES:
        _fail("embedded image must be a bounded base64 PNG, JPEG, or WebP")
    try:
        data = base64.b64decode(match[2], validate=True)
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            if (image.format or "").lower() != match[1]:
                _fail("embedded image MIME does not match decoded format")
            if max(image.size) > 4096 or image.width * image.height > 8_000_000:
                _fail("embedded raster exceeds dimension/pixel limits")
            if getattr(image, "n_frames", 1) != 1:
                _fail("animated embedded raster is not supported")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except SVGAssetError:
        raise
    except Exception as exc:
        raise SVGAssetError("embedded raster is invalid") from exc
    return data


def _transform(value: str) -> None:
    cursor, components = 0, 0
    for match in re.finditer(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^()]*)\)", value):
        if value[cursor:match.start()].strip(" ,\t\n\r"):
            _fail("unsupported SVG transform")
        nums = _numbers(match[2])
        counts = {"matrix": {6}, "translate": {1, 2}, "scale": {1, 2}, "rotate": {1, 3}, "skewX": {1}, "skewY": {1}}
        if len(nums) not in counts[match[1]]:
            _fail("invalid SVG transform arity")
        cursor, components = match.end(), components + 1
    if not components or components > 32 or value[cursor:].strip(" ,\t\n\r"):
        _fail("SVG transform exceeds supported syntax or budget")


def _path(value: str) -> None:
    """Validate finite path commands and arities, including elliptical arc flags."""
    if not value.strip():
        return
    if len(value) > MAX_PATH_CHARS or re.sub(NUMBER + r"|[MmZzLlHhVvCcSsQqTtAa\s,]", "", value):
        _fail("unsupported SVG path syntax")
    tokens = re.findall(NUMBER + r"|[MmZzLlHhVvCcSsQqTtAa]", value)
    if not tokens or tokens[0] not in {"M", "m"}:
        _fail("SVG path must start with a move command")
    arity = {"M": 2, "Z": 0, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}
    index = 0
    while index < len(tokens):
        command = tokens[index].upper()
        if command not in arity:
            _fail("SVG path requires a command before coordinates")
        index += 1
        values = []
        while index < len(tokens) and tokens[index].upper() not in arity:
            values.extend(_numbers(tokens[index], count=1))
            index += 1
        size = arity[command]
        if (size == 0 and values) or (size and (not values or len(values) % size)):
            _fail("SVG path command has invalid parameter count")
        if command == "A":
            for start in range(0, len(values), 7):
                if min(values[start:start+2]) < 0 or any(values[start+j] not in {0, 1} for j in (3, 4)):
                    _fail("SVG arc radii or flags are invalid")


def _validated(data: bytes, prefix: str, color: str) -> tuple[ET.Element, dict[str, Any]]:
    if not isinstance(prefix, str) or not re.fullmatch(IDENT, prefix):
        _fail("SVG prefix must be a safe identifier")
    fixed_color = _color(color)
    if fixed_color in {"none", "currentColor"}:
        _fail("currentColor fallback must be an explicit color")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SVGAssetError("SVG must be UTF-8") from exc
    if "\x00" in text or re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
        _fail("XML document types and entities are forbidden")
    # Processing instructions other than the initial XML declaration are never
    # handed to ElementTree/Cairo, including xml-stylesheet instructions.
    text = re.sub(r"^\s*<\?xml\s+[^?]*\?>", "", text, count=1)
    if "<?" in text:
        _fail("XML processing instructions are forbidden")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SVGAssetError("invalid SVG XML") from exc
    if _tag(root.tag) != "svg":
        _fail("asset root must be SVG")
    stack = [(root, 1)]
    nodes = []
    while stack:
        node, depth = stack.pop()
        nodes.append(node)
        if depth > MAX_DEPTH or len(nodes) > MAX_NODES or len(node.attrib) > 32:
            _fail("SVG tree exceeds resource limits")
        if _tag(node.tag) not in GEOMETRY or (node is not root and _tag(node.tag) == "svg"):
            _fail("unsupported SVG element: " + _tag(node.tag))
        stack.extend((child, depth + 1) for child in node)
    rules = _styles(root)
    ids, refs, counts = {}, [], Counter()
    numeric_budget, path_commands, embedded_count, embedded_pixels = 0, 0, 0, 0
    for node in nodes:
        name = _tag(node.tag)
        counts[name] += 1
        node.tag = "{" + SVG_NS + "}" + name
        attrs = {}
        for key, value in node.attrib.items():
            key = "href" if key == "{" + XLINK_NS + "}href" else key
            # Illustrator/editor labels and accessibility metadata have no
            # effect in the supported drawing subset; discard instead of
            # forcing loss of an otherwise valid official vector asset.
            if key == "role" or re.fullmatch(r"(?:data|aria)-[A-Za-z0-9_.-]+", key):
                continue
            if key in attrs or key not in GEOMETRY[name] | PRESENTATION | {"id", "class", "style", "transform"}:
                _fail("unsupported SVG attribute: " + key)
            if len(value) > (MAX_BYTES if key == "href" else MAX_PATH_CHARS):
                _fail("SVG attribute exceeds size budget")
            attrs[key] = value.strip()
        if "class" in attrs:
            classes = set(attrs["class"].split())
            if not all(re.fullmatch(IDENT, item) for item in classes):
                _fail("invalid SVG class")
            for selectors, declarations in rules:
                if classes & selectors:
                    attrs.update(declarations)
        attrs.pop("class", None)
        attrs.update(_declarations(attrs.pop("style", "")))
        node.attrib.clear()
        node.attrib.update(attrs)
        if name not in {"style", "title", "desc"} and (node.text or "").strip():
            _fail("text glyphs are unsupported in SVG assets")
        if (node.tail or "").strip():
            _fail("unexpected SVG text content")
        if name != "style":
            node.text = node.text if name in {"title", "desc"} else None
        node.tail = None
        if "id" in attrs:
            original_id = attrs["id"]
            if not re.fullmatch(SOURCE_IDENT, original_id) or original_id in ids:
                _fail("duplicate or invalid SVG id")
            ids[original_id] = node
        for key, value in list(attrs.items()):
            if key in {"id", "type"}:
                continue
            if key in PAINT_PROPS:
                if value.startswith("url("):
                    if key not in {"fill", "stroke"}:
                        _fail("only fill/stroke may reference gradients")
                    refs.append((node, key, value, GRADIENTS))
                else:
                    node.set(key, _color(value))
            elif key == "clip-path":
                if value != "none":
                    refs.append((node, key, value, {"clipPath"}))
            elif key == "href":
                if name == "image":
                    decoded = _raster(value)
                    from PIL import Image
                    with Image.open(io.BytesIO(decoded)) as image:
                        embedded_pixels += image.width * image.height
                    embedded_count += 1
                    if embedded_count > 4 or embedded_pixels > 16_000_000:
                        _fail("embedded image total exceeds resource limits")
                    # Cairo supports xlink consistently; input href/xlink are
                    # normalized to this one namespace, never double-applied.
                    node.attrib.pop("href")
                    node.set("{" + XLINK_NS + "}href", value)
                elif name in GRADIENTS:
                    refs.append((node, key, value, GRADIENTS))
                else:
                    _fail("SVG links are forbidden")
            elif key in {"transform", "gradientTransform"}:
                _transform(value)
            elif key == "d":
                _path(value)
                path_commands += len(re.findall(r"[MmZzLlHhVvCcSsQqTtAa]", value))
                if path_commands > 20000:
                    _fail("SVG paths exceed command budget")
            elif key in {"viewBox", "points", "stroke-dasharray"}:
                if key == "stroke-dasharray" and value == "none":
                    continue
                values = _numbers(value, count=4 if key == "viewBox" else None)
                if key == "points" and len(values) % 2:
                    _fail("SVG points must contain coordinate pairs")
            elif key in {"opacity", "fill-opacity", "stroke-opacity", "stop-opacity", "offset"}:
                val = _numbers(value, percent=True, count=1)[0]
                if not 0 <= val <= (100 if value.endswith("%") else 1):
                    _fail("SVG opacity/offset is out of range")
            elif key in {"fill-rule", "clip-rule"}:
                if value not in {"nonzero", "evenodd"}: _fail("unsupported fill rule")
            elif key == "stroke-linecap":
                if value not in {"butt", "round", "square"}: _fail("unsupported stroke linecap")
            elif key == "stroke-linejoin":
                if value not in {"miter", "round", "bevel"}: _fail("unsupported stroke linejoin")
            elif key in {"gradientUnits", "clipPathUnits"}:
                if value not in {"userSpaceOnUse", "objectBoundingBox"}: _fail("unsupported units")
            elif key == "spreadMethod":
                if value not in {"pad", "reflect", "repeat"}: _fail("unsupported gradient spread")
            elif key == "preserveAspectRatio":
                if not re.fullmatch(r"none|x(?:Min|Mid|Max)Y(?:Min|Mid|Max)(?: (?:meet|slice))?", value):
                    _fail("unsupported aspect-ratio mode")
            elif key == "version":
                if value not in {"1.0", "1.1", "2.0"}: _fail("unsupported SVG version")
            elif key == "overflow":
                if value != "hidden": _fail("SVG viewport overflow must be hidden")
            else:
                values = (_numbers(value, percent=True, count=1) if name in GRADIENTS else [_length(value)])
                if key in {"width", "height", "r", "rx", "ry", "fr", "stroke-width", "pathLength", "stroke-miterlimit"} and values[0] < 0:
                    _fail("negative SVG size")
            if key != "href":
                numeric_budget += len(re.findall(NUMBER, value))
                if numeric_budget > MAX_NUMBERS:
                    _fail("SVG exceeds numeric complexity budget")
    # Defs are finite trees rather than executable/reusable instance graphs.
    for node in nodes:
        name = _tag(node.tag)
        if name in GRADIENTS and any(_tag(child.tag) not in {"stop", "title", "desc"} for child in node):
            _fail("gradient may contain only stops")
        if name == "clipPath":
            for child in list(node.iter())[1:]:
                if _tag(child.tag) not in SHAPES or child.get("clip-path") not in {None, "none"}:
                    _fail("clipPath must contain only non-recursive static geometry")
    adjacency = {name: set() for name in ids}
    for node, key, value, expected in refs:
        if key == "href":
            match = re.fullmatch(r"#(" + SOURCE_IDENT + ")", value)
        else:
            match = re.fullmatch(r"url\(\s*#(" + SOURCE_IDENT + r")\s*\)", value)
        if not match or match[1] not in ids or _tag(ids[match[1]].tag) not in expected:
            _fail("SVG reference must name a local definition of the expected type")
        target = match[1]
        if node.get("id") in adjacency:
            adjacency[node.get("id")].add(target)
        node.set(key if key != "href" else "{" + XLINK_NS + "}href",
                 "#" + prefix + "-" + target if key == "href" else "url(#" + prefix + "-" + target + ")")
        if key == "href": node.attrib.pop("href", None)
    # Memoized, deduplicated DFS is linear in graph size. Repeated paint/href
    # references must not multiply traversal work exponentially.
    depths, visiting = {}, set()
    def reference_depth(identifier: str) -> int:
        if identifier in visiting:
            _fail("cyclic SVG references")
        if identifier in depths:
            return depths[identifier]
        if len(visiting) >= 16:
            _fail("excessively deep SVG references")
        visiting.add(identifier)
        depth = 1 + max((reference_depth(target) for target in adjacency[identifier]), default=0)
        visiting.remove(identifier)
        if depth > 16:
            _fail("excessively deep SVG references")
        depths[identifier] = depth
        return depth
    for identifier in adjacency: reference_depth(identifier)
    for identifier, node in ids.items(): node.set("id", prefix + "-" + identifier)
    def colors(node: ET.Element, inherited: str) -> None:
        own = node.get("color", inherited)
        own = inherited if own == "currentColor" else own
        if own == "none": _fail("color may not be none")
        for key in PAINT_PROPS:
            if node.get(key) == "currentColor": node.set(key, own)
        if "color" in node.attrib: node.set("color", own)
        for child in list(node):
            if _tag(child.tag) == "style": node.remove(child)
            else: colors(child, own)
    colors(root, fixed_color)
    root.set("color", root.get("color", fixed_color))
    view = _numbers(root.get("viewBox", ""), count=4) if root.get("viewBox") else None
    if view and (min(view[2:]) < 1e-6 or max(view[2:]) > MAX_DIMENSION):
        _fail("SVG viewBox must have bounded positive dimensions")
    width = _length(root.get("width")) if root.get("width") else None
    height = _length(root.get("height")) if root.get("height") else None
    if width is None: width = view[2] if view else None
    if height is None: height = view[3] if view else None
    if width is None or height is None or min(width, height) < 1e-6 or max(width, height) > MAX_DIMENSION:
        _fail("SVG needs bounded positive intrinsic width/height or viewBox")
    if max(width / height, height / width) > 4096:
        _fail("SVG aspect ratio exceeds resource limits")
    if view is None: view = [0.0, 0.0, width, height]
    root.set("width", str(width)); root.set("height", str(height))
    root.set("viewBox", " ".join(str(value) for value in view))
    root.set("preserveAspectRatio", root.get("preserveAspectRatio", "xMidYMid meet"))
    root.set("overflow", "hidden")
    info = {"width": width, "height": height, "view_box": view, "aspect_ratio": width / height,
            "element_count": len(nodes), "elements": dict(counts), "definition_ids": sorted(ids),
            "embedded_raster_count": embedded_count, "static_subset": True}
    return root, info


@lru_cache(maxsize=32)
def _safe(data: bytes, prefix: str, color: str) -> tuple[bytes, dict[str, Any]]:
    root, info = _validated(data, prefix, color)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(root, encoding="utf-8"), info


def safe_svg_bytes(source: bytes | str | Path, *, prefix: str = "asset", color: str = "#000000") -> bytes:
    """Validate and normalize a local static SVG; namespace every definition ID."""
    if not isinstance(prefix, str):
        _fail("SVG prefix must be a safe identifier")
    _color(color)
    return _safe(_read(source), prefix, color)[0]


def inspect_svg(source: bytes | str | Path, *, color: str = "#000000") -> dict[str, Any]:
    """Return checked intrinsic dimensions and subset metadata, without rendering."""
    import copy
    _color(color)
    return copy.deepcopy(_safe(_read(source), "inspect", color)[1])


def _local_raster_fetcher(url: str, resource_type: str) -> bytes:
    # Even if a renderer discovers a missed reference, it cannot perform I/O.
    if not isinstance(url, str) or not url.startswith("data:image/"):
        raise SVGAssetError("SVG renderer may not fetch network or filesystem resources")
    return _raster(url)


@lru_cache(maxsize=32)
def _preview(data: bytes, color: str, max_side: int) -> bytes:
    safe, info = _safe(data, "preview", color)
    from cairosvg.surface import PNGSurface
    factor = max_side / max(info["width"], info["height"])
    width = max(1, round(info["width"] * factor))
    height = max(1, round(info["height"] * factor))
    try:
        return PNGSurface.convert(bytestring=safe, output_width=width, output_height=height,
                                  unsafe=False, url_fetcher=_local_raster_fetcher)
    except SVGAssetError:
        raise
    except Exception as exc:
        raise SVGAssetError("validated SVG could not be rasterized; use a verified PNG export") from exc


def raster_preview(source: bytes | str | Path, *, color: str = "#000000", max_side: int = 512) -> bytes:
    """Return a bounded transparent PNG used for alpha/bounds QA, never delivery."""
    if isinstance(max_side, bool) or not isinstance(max_side, int) or not 1 <= max_side <= MAX_PREVIEW_SIDE:
        raise SVGAssetError("preview max_side must be an integer from 1 to 2048")
    _color(color)
    return _preview(_read(source), color, max_side)
