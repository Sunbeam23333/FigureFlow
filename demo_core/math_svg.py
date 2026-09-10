"""Restricted Matplotlib MathText-to-SVG conversion (no TeX subprocess)."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET


class MathSVGError(ValueError):
    pass


_TAGS = {"svg", "g", "defs", "path", "use", "clipPath", "rect"}
_ATTRS = {
    "id", "d", "x", "y", "width", "height", "viewBox", "transform", "style",
    "fill", "stroke", "stroke-width", "clip-path", "href",
}


def compile_math_svg(latex: str, *, prefix: str = "math") -> tuple[str, str]:
    """Return ``(viewBox, safe_inner_svg)`` for a common paper formula.

    Matplotlib's built-in MathText parser supports common symbols, fractions,
    scripts, matrices, and Greek letters.  It does not invoke a shell or a TeX
    installation.  The generated XML is reduced to a small SVG whitelist.
    """
    if not isinstance(latex, str) or not latex.strip() or len(latex) > 2000:
        raise MathSVGError("latex must be a non-empty string of at most 2000 characters")
    if re.search(r"\\(?:input|include|write|open|usepackage|documentclass|special|html|href|url)\b", latex):
        raise MathSVGError("formula contains a command outside safe MathText")
    try:
        from matplotlib.mathtext import math_to_image
        buffer = io.BytesIO()
        expression = latex.strip()
        if not (expression.startswith("$") and expression.endswith("$")):
            expression = f"${expression}$"
        math_to_image(expression, buffer, format="svg", dpi=72)
        root = ET.fromstring(buffer.getvalue())
    except Exception as exc:
        raise MathSVGError(f"unsupported MathText formula: {exc}") from exc
    # Matplotlib adds RDF metadata and a global style reset. Neither is needed
    # for glyph geometry; remove them instead of widening the accepted schema.
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] not in _TAGS:
                parent.remove(child)
    id_map: dict[str, str] = {}
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in _TAGS:
            raise MathSVGError(f"MathText emitted unsupported SVG element: {tag}")
        for name in list(node.attrib):
            local = name.rsplit("}", 1)[-1]
            if local not in _ATTRS or local.startswith("on"):
                del node.attrib[name]
        if "id" in node.attrib:
            old = node.attrib["id"]
            id_map[old] = f"{prefix}-{old}"
            node.attrib["id"] = id_map[old]
    for node in root.iter():
        for key, value in list(node.attrib.items()):
            if value.startswith("#"):
                node.attrib[key] = "#" + id_map.get(value[1:], value[1:])
            elif "url(#" in value:
                for old, new in id_map.items():
                    value = value.replace(f"url(#{old})", f"url(#{new})")
                node.attrib[key] = value
            if "javascript:" in node.attrib[key].lower() or "://" in node.attrib[key]:
                raise MathSVGError("MathText SVG contains an external reference")
    viewbox = root.attrib.get("viewBox")
    if not viewbox:
        raise MathSVGError("MathText SVG has no viewBox")
    inner = "".join(ET.tostring(child, encoding="unicode") for child in root)
    return viewbox, inner
