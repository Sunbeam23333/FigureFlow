"""Resolve individually named PDF vectors into editable SVG paths at render time.

The recipe pins the PDF's hash upstream and stores draw-operation IDs, not
third-party artwork. The resulting SVG is ordinary local, editable geometry.
"""

from __future__ import annotations


def _coord(point):
    return f"{point.x:.4f},{point.y:.4f}"


def path_data(drawing):
    """Preserve subpath direction (nonzero winding), incl. reversed rectangles."""
    result, end = [], None
    for item in drawing["items"]:
        kind = item[0]
        if kind in ("l", "c"):
            if item[1] != end:
                result += ["M", _coord(item[1])]
            result += ["L" if kind == "l" else "C", *map(_coord, item[2:])]
            end = item[-1]
        elif kind in ("re", "qu"):
            obj = item[1]
            if kind == "qu":
                pts = (obj.ul, obj.ur, obj.lr, obj.ll)
            elif item[2] == 1:
                pts = (obj.bl, obj.br, obj.tr, obj.tl)
            else:
                pts = (obj.tl, obj.tr, obj.br, obj.bl)
            result += ["M", _coord(pts[0]), "L", *map(_coord, pts[1:]), "Z"]
            end = None
        else:
            raise ValueError(f"Unexpected path primitive: {kind}")
    if drawing["closePath"]:
        result.append("Z")
    return " ".join(result)


def resolve_source_paths(page, layers):
    """Materialize only declared vector objects, never a whole page or figure."""
    if not any("source_seqno" in layer for layer in layers):
        return layers
    drawings = {d["seqno"]: d for d in page.get_drawings()}
    resolved = []
    for layer in layers:
        if "source_seqno" not in layer:
            resolved.append(layer)
            continue
        seq = layer["source_seqno"]
        if layer["kind"] != "path" or "d" in layer or seq not in drawings:
            raise ValueError(f"Invalid source path selector: {seq}")
        resolved.append(dict(layer, d=path_data(drawings[seq])))
    return resolved
