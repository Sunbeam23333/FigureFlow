#!/usr/bin/env python3
"""Render a publication-style LaTeX table from YAML and compile a review PDF."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Any

from public_safety import sanitize_log_file, sanitize_log_text
from visual_common import PALETTE, load_yaml, render_pdf, write_artifact_manifest


ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
}


def latex_escape(value: Any) -> str:
    text = str(value)
    for old, new in ESCAPES.items():
        text = text.replace(old, new)
    return text


def _raw_or_text(value: Any) -> str:
    if isinstance(value, dict):
        if "latex" in value:
            return str(value["latex"])
        return latex_escape(value.get("text", ""))
    return latex_escape(value)


def _cell(value: Any) -> str:
    if not isinstance(value, dict):
        return latex_escape(value)
    content = _raw_or_text(value)
    if value.get("best"):
        content = rf"\textbf{{{content}}}"
    kind = value.get("kind")
    if kind in {"predicted", "forecast", "synthetic-demo"}:
        content = rf"\cellcolor{{predgray}}{content}"
    elif kind == "measured":
        content = rf"\cellcolor{{measuredgreen}}{content}"
    elif kind == "implemented":
        content = rf"\cellcolor{{lightblue}}{content}"
    elif kind == "simulation":
        content = rf"\cellcolor{{lightviolet}}{content}"
    elif kind == "failed-gate":
        content = rf"\cellcolor{{lightred}}{content}"
    elif kind == "warning":
        content = rf"\cellcolor{{lightorange}}{content}"
    return content


def _column_spec(columns: list[dict[str, Any]]) -> str:
    pieces: list[str] = []
    for index, column in enumerate(columns):
        align = column.get("align", "c")
        width = float(column.get("width_cm", 3.7 if index == 0 else 2.35))
        declaration = {
            "l": r">{\raggedright\arraybackslash}",
            "c": r">{\centering\arraybackslash}",
            "r": r">{\raggedleft\arraybackslash}",
        }[align]
        pieces.append(rf"{declaration}p{{{width:.2f}cm}}")
    return "".join(pieces)


def _tabular(spec: dict[str, Any]) -> str:
    columns = spec["columns"]
    headers = [
        str(column["latex_header"])
        if "latex_header" in column
        else latex_escape(column.get("header", ""))
        for column in columns
    ]
    lines = [
        rf"\begin{{tabular}}{{{_column_spec(columns)}}}",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
    ]
    for row in spec.get("rows", []):
        if row.get("separator_before"):
            lines.append(r"\midrule")
        style = row.get("style")
        if style == "ours":
            lines.append(r"\rowcolor{lightblue}")
        elif style == "hybrid" or style == "warning":
            lines.append(r"\rowcolor{lightorange}")
        elif style == "section":
            lines.append(r"\rowcolor{sectiongray}")
        elif style == "failed-gate":
            lines.append(r"\rowcolor{lightred}")
        elif style == "simulation":
            lines.append(r"\rowcolor{lightviolet}")
        cells = row.get("cells", [])
        if len(cells) != len(columns):
            raise ValueError(f"row has {len(cells)} cells but table has {len(columns)} columns")
        lines.append(" & ".join(_cell(cell) for cell in cells) + r" \\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines)


def _preamble() -> str:
    colors = {name: value.removeprefix("#") for name, value in PALETTE.items()}
    source = r"""
\usepackage{fontspec}
\usepackage{booktabs,tabularx,array,colortbl,xcolor,graphicx}
\IfFontExistsTF{TeX Gyre Heros}{\setmainfont{TeX Gyre Heros}}{\setmainfont{Arial}}
\definecolor{navy}{HTML}{__NAVY__}
\definecolor{blue}{HTML}{__BLUE__}
\definecolor{teal}{HTML}{__TEAL__}
\definecolor{orange}{HTML}{__ORANGE__}
\definecolor{violet}{HTML}{__VIOLET__}
\definecolor{red}{HTML}{__RED__}
\definecolor{lightblue}{HTML}{__LIGHT_BLUE__}
\definecolor{lightorange}{HTML}{__LIGHT_ORANGE__}
\definecolor{lightviolet}{HTML}{__LIGHT_VIOLET__}
\definecolor{lightred}{HTML}{__LIGHT_RED__}
\definecolor{predgray}{HTML}{__PREDGRAY__}
\definecolor{sectiongray}{HTML}{F7F9FC}
\definecolor{measuredgreen}{HTML}{__LIGHT_TEAL__}
\definecolor{linegray}{HTML}{__LINE__}
\setlength{\tabcolsep}{3.2pt}
\renewcommand{\arraystretch}{1.34}
""".strip()
    replacements = {
        "__NAVY__": colors["navy"],
        "__BLUE__": colors["blue"],
        "__TEAL__": colors["teal"],
        "__ORANGE__": colors["orange"],
        "__VIOLET__": colors["violet"],
        "__RED__": colors["red"],
        "__LIGHT_BLUE__": colors["light_blue"],
        "__LIGHT_ORANGE__": colors["light_orange"],
        "__LIGHT_VIOLET__": colors["light_violet"],
        "__LIGHT_RED__": colors["light_red"],
        "__PREDGRAY__": colors["predgray"],
        "__LIGHT_TEAL__": colors["light_teal"],
        "__LINE__": colors["line"],
    }
    for token, value in replacements.items():
        source = source.replace(token, value)
    return source


def _standalone_source(spec: dict[str, Any], tabular: str) -> str:
    title = _raw_or_text(spec.get("title", "Results"))
    caption = _raw_or_text(spec.get("caption", ""))
    status = _raw_or_text(spec.get("status", ""))
    status_color = {
        "measured": "teal",
        "implemented": "blue",
        "simulation": "violet",
        "failed-gate": "red",
    }.get(spec.get("status_kind", spec.get("evidence_status")), "orange")
    note = _raw_or_text(spec.get("note", ""))
    width_mm = int(spec.get("standalone_width_mm", 196))
    return rf"""\documentclass[border=7pt]{{standalone}}
{_preamble()}
\begin{{document}}
\begin{{minipage}}{{{width_mm}mm}}
\sffamily
{{\Large\bfseries\color{{navy}} {title}}}\\[2pt]
{{\small\color{{navy}} {caption}}}\\[6pt]
""" + (rf"{{\footnotesize\bfseries\color{{{status_color}}} {status}}}\\[6pt]" if status else "") + rf"""
\centering
\small
{tabular}
""" + (rf"\\[5pt]{{\footnotesize\color{{navy}} {note}}}" if note else "") + r"""
\end{minipage}
\end{document}
"""


def _fragment_source(spec: dict[str, Any], tabular: str) -> str:
    caption = spec.get("paper_caption", spec.get("caption", ""))
    label = spec.get("label", "tab:results")
    environment = spec.get("environment", "table*")
    return rf"""% Requires booktabs, array, colortbl, xcolor, and the semantic colors from this skill.
\begin{{{environment}}}[t]
\centering
\caption{{{caption}}}
\label{{{label}}}
\small
{tabular}
\end{{{environment}}}
"""


def _compile(tex: Path, output_dir: Path) -> Path:
    engine = shutil.which("xelatex")
    if not engine:
        raise RuntimeError("xelatex is required for the table demo")
    command = [engine, "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={output_dir}", tex.name]
    result = subprocess.run(
        command,
        cwd=tex.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    safe_output = sanitize_log_text(result.stdout, local_roots=(tex.parent, output_dir))
    (output_dir / f"{tex.stem}.log.txt").write_text(safe_output, encoding="utf-8")
    sanitize_log_file(
        output_dir / f"{tex.stem}.log",
        local_roots=(tex.parent, output_dir),
    )
    if result.returncode:
        raise RuntimeError(f"xelatex failed for {tex.name}:\n{safe_output[-4000:]}")
    pdf = output_dir / f"{tex.stem}.pdf"
    if not pdf.exists():
        raise RuntimeError(f"xelatex did not create {pdf.name}")
    return pdf


def render(spec_path: Path, output_dir: Path) -> tuple[Path, Path, Path, Path]:
    spec = load_yaml(spec_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = spec.get("output_name", "results_table")
    tabular = _tabular(spec)
    standalone = output_dir / f"{name}.tex"
    fragment = output_dir / f"{name}_fragment.tex"
    standalone.write_text(_standalone_source(spec, tabular), encoding="utf-8")
    fragment.write_text(_fragment_source(spec, tabular), encoding="utf-8")
    pdf = _compile(standalone, output_dir)
    png = output_dir / f"{name}.png"
    render_pdf(pdf, png, dpi=int(spec.get("dpi", 220)))
    write_artifact_manifest(output_dir / name, spec_path, spec, [standalone, fragment, pdf, png])
    return standalone, fragment, pdf, png


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in render(args.spec.resolve(), args.output_dir.resolve()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
