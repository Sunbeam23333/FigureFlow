#!/usr/bin/env python3
"""Build the complete data/main/link/table research-visual demo and paper PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from PIL import Image, ImageDraw, ImageFont

from render_data_figure import render as render_data
from render_link_graph import render as render_link
from render_overview import render as render_overview
from render_table import render as render_table
from public_safety import portable_path, sanitize_log_file, sanitize_log_text
from visual_common import PALETTE, render_pdf, write_json


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SOURCE_DIR = SKILL_DIR / "demo" / "source"


def generate_source_data(data_dir: Path) -> list[Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260825)

    tokens = np.linspace(0.5, 30.0, 60)
    train = 2.94 + 6.3 * np.exp(-tokens / 5.1) + 0.035 * np.sin(tokens * 1.3)
    validation = 2.86 + 2.65 * np.exp(-tokens / 6.7) + 0.025 * np.cos(tokens)
    training = pd.DataFrame(
        {
            "tokens_b": tokens,
            "train_loss": train,
            "train_low": train - 0.08,
            "train_high": train + 0.08,
            "validation_loss": validation,
            "validation_low": validation - 0.06,
            "validation_high": validation + 0.06,
            "status": "synthetic demo - not measured",
        }
    )
    training_path = data_dir / "training.csv"
    training.to_csv(training_path, index=False, float_format="%.6g")

    log_rank = np.linspace(2.4, 5.2, 18)
    observed = 0.095 * (log_rank - log_rank.mean()) + rng.normal(0, 0.018, len(log_rank))
    fitted = np.polyval(np.polyfit(log_rank, observed, 1), log_rank)
    residuals_path = data_dir / "residuals.csv"
    pd.DataFrame(
        {
            "log_rank": log_rank,
            "observed": observed,
            "fitted": fitted,
            "status": "synthetic demo - not measured",
        }
    ).to_csv(residuals_path, index=False, float_format="%.6g")

    gates_path = data_dir / "gates.csv"
    pd.DataFrame(
        {
            "family": ["latent-2", "latent-4", "parity"],
            "old": [69, 73, 35],
            "faithful": [94, 96, 93],
            "status": "synthetic demo - not measured",
        }
    ).to_csv(gates_path, index=False)

    flops = np.linspace(0.2, 1.0, 9)
    frontier_path = data_dir / "frontier.csv"
    pd.DataFrame(
        {
            "flops": flops,
            "rank1": 3.08 + 1.55 * np.exp(-2.2 * flops),
            "rank4": 2.89 + 1.48 * np.exp(-2.55 * flops),
            "adaptive": 2.76 + 1.42 * np.exp(-2.9 * flops),
            "status": "synthetic demo - not measured",
        }
    ).to_csv(frontier_path, index=False, float_format="%.6g")
    return [training_path, residuals_path, gates_path, frontier_path]


def materialize_data_spec(
    template_path: Path,
    data_files: list[Path],
    output_dir: Path,
) -> Path:
    """Write an output-local data spec whose CSV paths follow --output-dir."""
    spec = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or not isinstance(spec.get("panels"), list):
        raise ValueError("data-figure template must contain a panels list")

    resolved_output = output_dir.resolve()
    files_by_name: dict[str, Path] = {}
    for path in data_files:
        resolved = path.resolve()
        if resolved.name in files_by_name:
            raise ValueError(f"duplicate generated data filename: {resolved.name}")
        try:
            resolved.relative_to(resolved_output)
        except ValueError as exc:
            raise ValueError("generated demo data must stay inside --output-dir") from exc
        files_by_name[resolved.name] = resolved

    for panel in spec["panels"]:
        if not isinstance(panel, dict) or not panel.get("csv"):
            raise ValueError("every data-figure panel must reference a generated CSV")
        filename = Path(str(panel["csv"])).name
        data_path = files_by_name.get(filename)
        if data_path is None:
            raise ValueError(f"data-figure template references unknown CSV: {filename}")
        panel["csv"] = data_path.relative_to(resolved_output).as_posix()

    output_name = str(spec.get("output_name", "data_figure"))
    materialized = resolved_output / f"{output_name}_source.yaml"
    materialized.write_text(
        yaml.safe_dump(spec, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return materialized


def compile_demo_paper(output_dir: Path) -> tuple[Path, Path]:
    source = r"""\documentclass[10pt,twocolumn]{article}
\usepackage[a4paper,margin=0.68in,columnsep=0.23in]{geometry}
\usepackage{fontspec}
\usepackage{amsmath,amssymb,booktabs,array,colortbl,xcolor,graphicx,microtype}
\usepackage[hidelinks]{hyperref}
\IfFontExistsTF{TeX Gyre Heros}{\setmainfont{TeX Gyre Heros}}{\setmainfont{Arial}}
\definecolor{navy}{HTML}{__NAVY__}
\definecolor{blue}{HTML}{__BLUE__}
\definecolor{teal}{HTML}{__TEAL__}
\definecolor{orange}{HTML}{__ORANGE__}
\definecolor{lightblue}{HTML}{__LIGHT_BLUE__}
\definecolor{lightorange}{HTML}{__LIGHT_ORANGE__}
\definecolor{predgray}{HTML}{__PREDGRAY__}
\definecolor{sectiongray}{HTML}{F7F9FC}
\definecolor{measuredgreen}{HTML}{E9F6F4}
\setlength{\textfloatsep}{8pt plus 2pt minus 2pt}
\setlength{\floatsep}{7pt plus 2pt minus 2pt}
\setlength{\abovecaptionskip}{4pt}
\setlength{\belowcaptionskip}{2pt}
\setlength{\tabcolsep}{3.2pt}
\renewcommand{\arraystretch}{1.30}
\makeatletter
\setlength{\@fptop}{0pt}
\setlength{\@dblfptop}{0pt}
\makeatother
\title{\vspace{-1.1cm}\textbf{Publication Visual System: A Reproducible Demo}}
\author{Deterministic module showcase}
\date{}
\begin{document}
\maketitle
\vspace{-5mm}
\begin{abstract}
This compact document demonstrates four reusable research-paper modules: a semantic overview, a quantitative evidence grid, an explicit transfer graph, and a status-aware result table. All values are synthetic and visibly marked as such. The design separates claims, evidence status, visual encoding, and captions so the same modules can be filled with verified paper content.
\end{abstract}
\noindent\colorbox{lightorange}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{\textbf{Demo status.} Every numeric value in this document is synthetic and must not be read as an experimental result.}}

\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{demo_main_overview.pdf}
\caption{\textbf{Main overview module.} Five semantic stages, a routed two-branch decision, compiled formulas, and a hard-gate belt form one falsifiable narrative. Text and geometry remain editable vector objects.}
\end{figure*}

\section{Narrative contract}
The visual order is evidence first, mechanism second, decisions third, and stress tests last. The lower belt carries stopping criteria rather than decorative badges. This keeps the figure useful even when the eventual result is null.

For any statistic $r_t$, the paper must first define its evidence source, then explain the formula and variables, and only then attach it to a prediction or allocation rule. Generated illustrations cannot replace measured evidence.

\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{demo_quantitative.pdf}
\caption{\textbf{Quantitative module.} The four panels progress from optimization health to held-out prediction, preregistered gate, and equal-compute decision value. The source CSVs and deterministic seed are delivered with the figure.}
\end{figure*}

\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{demo_link_graph.pdf}
\caption{\textbf{Link-graph module.} Solid curves show planned transfer tests. The dashed red edge is an explicit non-transfer statement; it prevents an attractive graph from silently broadening the paper's claim.}
\end{figure*}

\input{demo_results_table_fragment.tex}

\section{Interpretation}
The demo encodes evidence status redundantly: banners in figures, gray forecast cells, superscript markers, and caption language. A final paper should replace synthetic values with measured results while preserving the audit trail and negative-result rows.

\section{Module routing}
Use the overview module for one paper-level claim with three to six semantic stages. Use the quantitative module when axes, uncertainty, units, and source rows carry the argument. Use the link module when direction, transfer, or an explicitly unsupported edge matters. Use the table module when exact values and evidence status must remain inspectable.

The renderer is selected only after the claim is written in one sentence. This avoids dressing exploratory output as a finished paper figure and keeps each visual tied to an auditable source artifact.

\section{Caption and evidence}
A complete caption names the claim, the visual encoding, the evidence status, and the reading boundary. Mathematical notation is typeset by a real math engine and embedded as vector paths; variables are defined in prose before the equation is used to support a decision.

\section{Quality gates}
Final delivery requires editable source, PDF and high-resolution PNG, source data, a provenance manifest, and a rendered paper-page preview. Every PDF is checked for page count, embedded fonts, clipping, stale renders, and compilation warnings. Forecasts, simulations, illustrations, and synthetic demos remain visibly distinct from measured results.
\end{document}
"""
    for token, theme_key in {
        "__NAVY__": "navy",
        "__BLUE__": "blue",
        "__TEAL__": "teal",
        "__ORANGE__": "orange",
        "__LIGHT_BLUE__": "light_blue",
        "__LIGHT_ORANGE__": "light_orange",
        "__PREDGRAY__": "predgray",
    }.items():
        source = source.replace(token, PALETTE[theme_key].removeprefix("#"))
    tex = output_dir / "demo_paper.tex"
    tex.write_text(source, encoding="utf-8")
    engine = shutil.which("xelatex")
    if not engine:
        raise RuntimeError("xelatex is required to compile the demo paper")
    logs: list[str] = []
    for _ in range(2):
        result = subprocess.run(
            [engine, "-interaction=nonstopmode", "-halt-on-error", tex.name],
            cwd=output_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        safe_output = sanitize_log_text(result.stdout, local_roots=(output_dir, SKILL_DIR))
        logs.append(safe_output)
        sanitize_log_file(
            output_dir / "demo_paper.log",
            local_roots=(output_dir, SKILL_DIR),
        )
        if result.returncode:
            raise RuntimeError(f"xelatex failed:\n{safe_output[-5000:]}")
    log_path = output_dir / "demo_paper_compile.log.txt"
    log_path.write_text("\n\n".join(logs), encoding="utf-8")
    pdf = output_dir / "demo_paper.pdf"
    if not pdf.exists():
        raise RuntimeError("demo paper PDF was not created")
    return tex, pdf


def make_gallery(paths: list[Path], output: Path) -> Path:
    images = [Image.open(path).convert("RGB") for path in paths]
    cell_width, padding, label_height = 1050, 34, 48
    resized: list[Image.Image] = []
    heights: list[int] = []
    for image in images:
        ratio = cell_width / image.width
        item = image.resize((cell_width, max(1, round(image.height * ratio))), Image.Resampling.LANCZOS)
        resized.append(item)
        heights.append(item.height + label_height)
    row_heights = [max(heights[index : index + 2]) for index in range(0, len(heights), 2)]
    canvas = Image.new("RGB", (2 * cell_width + 3 * padding, sum(row_heights) + (len(row_heights) + 1) * padding), "#F7F8F6")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    y = padding
    for row, row_height in enumerate(row_heights):
        for column in range(2):
            index = row * 2 + column
            if index >= len(resized):
                break
            x = padding + column * (cell_width + padding)
            draw.text((x, y + 8), paths[index].stem, fill="#142B4A", font=font)
            canvas.paste(resized[index], (x, y + label_height))
        y += row_height + padding
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=SKILL_DIR / "demo" / "output")
    args = parser.parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    data_files = generate_source_data(output_dir / "source_data")
    data_spec = materialize_data_spec(
        SOURCE_DIR / "data_figure.yaml",
        data_files,
        output_dir,
    )
    overview_svg, overview_pdf, overview_png = render_overview(SOURCE_DIR / "overview.yaml", output_dir)
    data_pdf, data_png = render_data(data_spec, output_dir)
    link_pdf, link_png = render_link(SOURCE_DIR / "link_graph.yaml", output_dir)
    table_tex, table_fragment, table_pdf, table_png = render_table(SOURCE_DIR / "table.yaml", output_dir)
    paper_tex, paper_pdf = compile_demo_paper(output_dir)

    paper_prefix = output_dir / "demo_paper_page"
    renderer = shutil.which("pdftoppm")
    if not renderer:
        raise RuntimeError("pdftoppm is required for demo QA")
    for stale_page in output_dir.glob("demo_paper_page-*.png"):
        stale_page.unlink()
    rendered = subprocess.run(
        [renderer, "-png", "-r", "170", str(paper_pdf), str(paper_prefix)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if rendered.returncode:
        raise RuntimeError(sanitize_log_text(rendered.stdout, local_roots=(output_dir, SKILL_DIR)))
    paper_pages = sorted(output_dir.glob("demo_paper_page-*.png"))
    gallery = make_gallery([overview_png, data_png, link_png, table_png], output_dir / "demo_gallery.png")

    outputs = [overview_pdf, data_pdf, link_pdf, table_pdf, paper_pdf]
    qa_single = output_dir / "qa_single_page.json"
    qa_paper = output_dir / "qa_paper.json"
    qa_commands = [
        [
            sys.executable,
            str(SCRIPT_DIR / "qa_pdf.py"),
            str(overview_pdf),
            str(data_pdf),
            str(link_pdf),
            str(table_pdf),
            "--single-page",
            "--log",
            str(output_dir / f"{table_pdf.stem}.log"),
            "--json-output",
            str(qa_single),
        ],
        [
            sys.executable,
            str(SCRIPT_DIR / "qa_pdf.py"),
            str(paper_pdf),
            "--expect-pages",
            "3",
            "--log",
            str(output_dir / "demo_paper.log"),
            "--json-output",
            str(qa_paper),
        ],
    ]
    for command in qa_commands:
        checked = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if checked.returncode:
            safe_output = sanitize_log_text(checked.stdout, local_roots=(output_dir, SKILL_DIR))
            raise RuntimeError(f"visual PDF QA failed:\n{safe_output}")
    output_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in outputs
    }
    manifest = {
        "evidence_status": "synthetic-demo",
        "seed": 20260825,
        "source_specs": [
            portable_path(path, output_dir)
            for path in (
                SOURCE_DIR / "overview.yaml",
                data_spec,
                SOURCE_DIR / "link_graph.yaml",
                SOURCE_DIR / "table.yaml",
            )
        ],
        "source_data": [portable_path(path, output_dir) for path in data_files],
        "editable_sources": [
            portable_path(path, output_dir)
            for path in (overview_svg, table_tex, table_fragment, paper_tex)
        ],
        "pdf_outputs": [portable_path(path, output_dir) for path in outputs],
        "pdf_sha256": output_hashes,
        "qa_reports": [portable_path(path, output_dir) for path in (qa_single, qa_paper)],
        "module_manifests": [
            portable_path(output_dir / f"{stem}_manifest.json", output_dir)
            for stem in (
                "demo_main_overview",
                "demo_quantitative",
                "demo_link_graph",
                "demo_results_table",
            )
        ],
        "review_pngs": [
            portable_path(path, output_dir)
            for path in (overview_png, data_png, link_png, table_png, *paper_pages)
        ],
        "gallery": portable_path(gallery, output_dir),
        "statement": "All demo numbers are synthetic and are not experimental results.",
    }
    manifest_path = output_dir / "demo_manifest.json"
    write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2))
    print(portable_path(manifest_path, output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
