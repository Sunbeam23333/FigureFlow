"""Emit an editable, native TikZ scene in original paper-point coordinates.

Input: resolved scene primitives + independently extracted evidence assets.
Output: candidate_tikz.tex (compile with xelatex candidate_tikz.tex).
Unknown operators fail rather than silently rasterizing or dropping artwork.
"""

from __future__ import annotations

import re
from pathlib import Path

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
TOKEN = re.compile(rf"[MLCZ]|{NUMBER}")
TEX_ESCAPE = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "%": r"\%",
    "^": r"\textasciicircum{}",
    "~": r"\textasciitilde{}",
    "\u00a0": "~",
}
FONT_MAP = {
    "Times New Roman": "Times",
    "Arial": "Arial",
    "Georgia": "Georgia",
    "STIX Two Math": "STIX",
    "DejaVu Sans": "Deja",
    "Menlo": "Menlo",
    "Verdana": "Verdana",
}
FALLBACK = {
    "Times": "texgyretermes",
    "Arial": "texgyreheros",
    "Georgia": "texgyretermes",
    "STIX": "latinmodern-math",
    "Deja": "texgyreheros",
    "Menlo": "texgyrecursor",
    "Verdana": "texgyreheros",
}


def num(x):
    return format(float(x), ".4f").rstrip("0").rstrip(".") or "0"


def xy(x, y):
    return f"({num(x)},{num(y)})"


def rect(box):
    return xy(*box[:2]) + " rectangle " + xy(*box[2:])


def decode_path(string):
    """Convert the supported absolute SVG path subset into editable TikZ."""
    if re.search(r"[^,\s]", TOKEN.sub("", string)):
        raise ValueError("unsupported SVG path grammar")
    tokens = TOKEN.findall(string)
    command, result, i = None, [], 0
    while i < len(tokens):
        if tokens[i] in ("M", "L", "C", "Z"):
            command = tokens[i]
            i += 1
        if command == "Z":
            result.append("--cycle")
            command = None
            continue
        count = {"M": 2, "L": 2, "C": 6}.get(command)
        if count is None or i + count > len(tokens):
            raise ValueError("incomplete SVG path")
        values = tokens[i : i + count]
        i += count
        if command == "C":
            result.append(
                ".. controls " + xy(*values[:2]) + " and " + xy(*values[2:4]) + " .. " + xy(*values[4:])
            )
        else:
            result.append(("--" if command == "L" else "") + xy(*values))
            command = "L"
    return " ".join(result)


def write_tikz(spec, resolved_layers, out):
    palette = {}

    def color(c):
        if c in ("white", "black", "none"):
            return c
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", c):
            raise ValueError(f"unsupported PDF color: {c}")
        key = c[1:].upper()
        return palette.setdefault(key, "ff" + key)

    def style(a):
        o = []
        fill, stroke = a.get("fill", "none"), a.get("stroke", "none")
        if fill.startswith("url("):
            grad = re.fullmatch(r"url\(#([A-Za-z0-9-]+)\)", fill)
            if grad is None or grad[1] not in spec.get("gradients", {}):
                raise ValueError(f"undefined gradient: {fill}")
            o.extend(["shade", "shading=ffgrad" + grad[1]])
        elif fill != "none":
            o.append("fill=" + color(fill))
        if stroke != "none" and a.get("sw", 1) > 0:
            o.extend(["draw=" + color(stroke), "line width=" + num(a.get("sw", 1)) + "bp"])
        for field, option in (
            ("opacity", "opacity"),
            ("fillOpacity", "fill opacity"),
            ("fill_opacity", "fill opacity"),
            ("strokeOpacity", "draw opacity"),
            ("stroke_opacity", "draw opacity"),
        ):
            if field in a:
                o.append(option + "=" + num(a[field]))
        if a.get("rule", a.get("fill_rule")) == "evenodd":
            o.append("even odd rule")
        if "dash" in a:
            d = a["dash"].split() if isinstance(a["dash"], str) else a["dash"]
            if len(d) % 2:
                d = d + d
            o.append(
                "dash pattern="
                + " ".join(("off" if i % 2 else "on") + " " + num(n) + "bp" for i, n in enumerate(d))
            )
        return o

    scene = []
    for idx, a in enumerate(resolved_layers):
        kind, key = a["kind"], a.get("id", f"{a['kind']}-{idx}")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", key):
            raise ValueError(f"unsafe layer name: {key}")
        scene.append("% " + key + " | " + kind)
        wrap = "clip" in a or "transform" in a
        if wrap:
            options = []
            if "transform" in a:
                m = re.fullmatch(rf"translate\(\s*({NUMBER})[ ,]+({NUMBER})\s*\)", a["transform"])
                if not m:
                    raise ValueError("unsupported TikZ scene transform")
                options.append("shift={" + xy(m[1], m[2]) + "}")
            scene.append(r"\begin{scope}[" + ",".join(options) + "]")
            if "clip" in a:
                scene.append(r"\clip " + rect(a["clip"]) + ";")
        options = style(a)
        if kind in ("rect", "path", "ellipse"):
            if kind == "rect":
                x, y, w, h = (a[k] for k in ("x", "y", "w", "h"))
                geo = rect([x, y, x + w, y + h])
                if a.get("rx", 0):
                    options.append("rounded corners=" + num(a["rx"]) + "bp")
            elif kind == "ellipse":
                geo = (
                    xy(a["cx"], a["cy"])
                    + " ellipse [x radius="
                    + num(a["rx"])
                    + "bp,y radius="
                    + num(a["ry"])
                    + "bp]"
                )
            else:
                geo = decode_path(a["d"])
            if geo:
                scene.append(r"\path[" + ",".join(options) + "] " + geo + ";")
        elif kind == "asset":
            box = a.get("dest", a["box"])
            w = box[2] - box[0]
            h = box[3] - box[1]
            scene.append(
                r"\node[anchor=north west,inner sep=0pt,outer sep=0pt,"
                + ",".join(options)
                + "] at "
                + xy(*box[:2])
                + r" {\includegraphics[width="
                + num(w)
                + "bp,height="
                + num(h)
                + "bp]{assets/"
                + key
                + ".png}};"
            )
        elif kind == "text":
            # Geometric compression affects the label's width only. Its TeX
            # baseline and physical point size remain independent of its width.
            options = [t for t in options if not t.startswith("fill=")]
            options += [
                "inner sep=0pt",
                "outer sep=0pt",
                "text=" + color(a.get("fill", "black")),
                "anchor="
                + {"start": "base west", "middle": "base", "end": "base east"}[a.get("anchor", "start")],
            ]
            if "rotate" in a:
                options += ["rotate=" + num(-a["rotate"])]
            family = a.get("font", "Arial").split(",")[0]
            f = FONT_MAP.get(family)
            if f is None:
                raise ValueError("unsupported figure font: " + family)
            label = "".join(TEX_ESCAPE.get(c, c) for c in a["text"])
            commands = [
                r"\fffont" + f,
                r"\fontsize{" + num(a["size"]) + "bp}{" + num(a["size"] * 1.15) + r"bp}\selectfont",
            ]
            if str(a.get("weight", "normal")) in ("bold", "600", "700", "800", "900"):
                commands.append(r"\bfseries")
            if a.get("style") == "italic":
                commands.append(r"\itshape")
            content = r"\hbox{" + " ".join(commands) + " " + label + "}"
            if a.get("length") and a["text"].strip():
                content = r"\resizebox{" + num(a["length"]) + r"bp}{\height}{" + content + "}"
            scene.append(r"\node[" + ",".join(options) + "] at " + xy(a["x"], a["y"]) + " {" + content + "};")
        else:
            raise ValueError(f"unsupported TikZ layer: {kind}")
        if wrap:
            scene.append(r"\end{scope}")

    gradients = []
    for name, stops in spec.get("gradients", {}).items():
        if not re.fullmatch(r"[A-Za-z0-9-]+", name):
            raise ValueError("invalid gradient name")
        # PGF fits the *middle* 50 bp of a shading to the shape's bounding box.
        points = (
            [(0, stops[0][1])]
            + [(25 + 0.5 * float(n.rstrip("%")), c) for n, c in stops]
            + [(100, stops[-1][1])]
        )
        gradients.append(
            r"\pgfdeclarehorizontalshading{ffgrad"
            + name
            + "}{100bp}{"
            + "; ".join("color(" + num(offset) + "bp)=(" + color(c) + ")" for offset, c in points)
            + "}"
        )
    fonts = []
    used = {a.get("font", "Arial").split(",")[0] for a in resolved_layers if a["kind"] == "text"}
    for name, macro in FONT_MAP.items():
        if name not in used:
            continue
        alt = FALLBACK[macro]
        fallback = (
            "{latinmodern-math.otf}"
            if macro == "STIX"
            else "[BoldFont="
            + alt
            + "-bold.otf,ItalicFont="
            + alt
            + "-italic.otf,BoldItalicFont="
            + alt
            + "-bolditalic.otf]{"
            + alt
            + "-regular.otf}"
        )
        fonts.append(
            r"\IfFontExistsTF{"
            + name
            + r"}{\newfontfamily\fffont"
            + macro
            + "{"
            + name
            + r"}}{\newfontfamily\fffont"
            + macro
            + fallback
            + "}"
        )
    bbox = rect(spec["box"])
    tex = [
        "% !TeX program = xelatex",
        "% Editable source-assisted reconstruction; supplied figure images are separate local assets.",
        "% Compile in this directory with xelatex candidate_tikz.tex",
        r"\documentclass[tikz,border=0pt]{standalone}",
        r"\usepackage{fontspec,graphicx}",
        *fonts,
        *[r"\definecolor{" + value + "}{HTML}{" + hexval + "}" for hexval, value in palette.items()],
        *gradients,
        r"\begin{document}",
        r"\begin{tikzpicture}[x=1bp,y=-1bp]",
        r"\path[use as bounding box] " + bbox + ";",
        r"\begin{scope}[overlay]",
        r"\clip " + bbox + ";",
        *scene,
        r"\end{scope}",
        r"\end{tikzpicture}",
        r"\end{document}",
    ]
    target = Path(out) / "candidate_tikz.tex"
    target.write_text("\n".join(tex) + "\n", encoding="utf-8")
    return target
