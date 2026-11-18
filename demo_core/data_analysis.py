"""Local, evidence-labelled tabular analysis and deterministic research charts.

This is the *data-driven* renderer, not the source-layout replay implemented in
``alphaedit_reproduction``. Bar lengths here always follow the supplied values.
No files are fetched, missing observations imputed, or experiments rerun.

Run ``python -m demo_core.data_analysis data.csv --output-dir output``.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping
import zipfile


PALETTE = ("#645AC6", "#C3DEC3", "#FFDCC7", "#A3B5D6", "#DEA991")
ALPHAEDIT_METHOD_COLORS = dict(zip(("AlphaEdit", "RECT", "PRUNE", "MEMIT", "ROME"), PALETTE))
WELM_IMAGE_RADIAL_PALETTE = (
    "#60AB88",  # WeLM-Image
    "#7ABE96",  # HunyuanImage-3.0-Instruct-Distil
    "#93CDA7",  # Qwen-Image
    "#ACDCBB",  # Qwen-Image-2512
    "#C3E7CD",  # SenseNova-U1-8B-MoT
    "#DBF3E2",  # Ernie-Image-Turbo
)
PALETTE_NAMES = ("alphaedit", "welm-image")
EVIDENCE_CODES = {
    "published-figure": "P", "published-table": "T", "user-supplied": "U",
    "remeasured": "R", "measured": "M", "synthetic-demo": "S",
    "simulation": "I", "forecast": "F", "failed-gate": "G",
}
_RC = {"font.family": "DejaVu Sans", "font.size": 9, "pdf.fonttype": 42,
       "ps.fonttype": 42, "svg.fonttype": "path", "text.usetex": False,
       "text.parse_math": False,
       "axes.spines.top": False, "axes.spines.right": False,
       "savefig.facecolor": "white", "svg.hashsalt": "figureflow-data-v1"}


@dataclass(frozen=True)
class Observation:
    metric: str
    method: str
    value: float
    label: str
    source: str
    evidence_status: str


@dataclass(frozen=True)
class DataTable:
    """A complete metric × method matrix, retaining input order and provenance."""

    observations: tuple[Observation, ...]
    metrics: tuple[str, ...]
    methods: tuple[str, ...]
    filename: str
    sha256: str
    source_path: Path

    def lookup(self) -> dict[tuple[str, str], Observation]:
        return {(row.metric, row.method): row for row in self.observations}


def load_data(csv_path: str | Path, *, default_evidence_status: str = "user-supplied") -> DataTable:
    """Validate a local long CSV; reject duplicates, nonfinite values and gaps.

    ``metric,method,value`` are required. ``label`` is an optional numeric display
    string (e.g. ``0.90``), not a second value. ``source`` and ``evidence_status``
    preserve provenance. An absent source defaults to the local CSV's basename.
    Negative values are valid for analysis/small multiples, but not annular bars.
    """
    if "://" in str(csv_path):
        raise ValueError("Only local CSV files are accepted; URLs are provenance, not fetch instructions")
    if default_evidence_status not in EVIDENCE_CODES:
        raise ValueError(f"Unknown evidence status: {default_evidence_status}")
    path = Path(csv_path).expanduser()
    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path}")
    rows: list[Observation] = []
    keys: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if not {"metric", "method", "value"}.issubset(fields):
            raise ValueError("CSV requires metric, method and value columns")
        if len(fields) != len(set(fields)):
            raise ValueError("CSV contains duplicate column names")
        for line, item in enumerate(reader, 2):
            if None in item:
                raise ValueError(f"Line {line}: too many fields")
            metric = (item.get("metric") or "").strip()
            method = (item.get("method") or "").strip()
            if not metric or not method:
                raise ValueError(f"Line {line}: metric and method must be nonempty")
            if (metric, method) in keys:
                raise ValueError(f"Line {line}: duplicate metric/method pair {metric!r}, {method!r}")
            try:
                value = float(item.get("value") or "")
            except ValueError as exc:
                raise ValueError(f"Line {line}: missing or nonnumeric value") from exc
            if not math.isfinite(value):
                raise ValueError(f"Line {line}: value must be finite")
            label = (item.get("label") or "").strip() or f"{value:g}"
            try:
                label_value = float(label)
            except ValueError as exc:
                raise ValueError(f"Line {line}: label must be a numeric display string") from exc
            if not math.isfinite(label_value) or not math.isclose(label_value, value, rel_tol=1e-12):
                raise ValueError(f"Line {line}: label must represent the same value")
            status = (item.get("evidence_status") or default_evidence_status).strip()
            if status not in EVIDENCE_CODES:
                raise ValueError(f"Line {line}: unknown evidence status {status!r}")
            source = (item.get("source") or "").strip() or path.name
            rows.append(Observation(metric, method, value, label, source, status))
            keys.add((metric, method))
    if not rows:
        raise ValueError("CSV contains no observations")
    metrics = tuple(dict.fromkeys(row.metric for row in rows))
    methods = tuple(dict.fromkeys(row.method for row in rows))
    missing = [(metric, method) for metric in metrics for method in methods if (metric, method) not in keys]
    if missing:
        raise ValueError(f"Incomplete matrix; missing {missing[:5]} (no imputation performed)")
    return DataTable(tuple(rows), metrics, methods, path.name,
                     hashlib.sha256(path.read_bytes()).hexdigest(), path.resolve())


def analyze_data(
    data: DataTable | str | Path, *, focus_method: str | None = None,
    higher_is_better: Mapping[str, bool] | None = None,
) -> dict:
    """Rank within each metric and compare focus against its best alternative.

    A positive ``advantage`` means the focus is better in the selected direction;
    ``difference`` is always raw focus minus comparator. Relative advantage uses
    the comparator's absolute value; it is undefined (JSON null) at zero. Ties
    receive the same competition rank. There is no across-metric aggregate.
    """
    table = load_data(data) if not isinstance(data, DataTable) else data
    focus = focus_method or ("AlphaEdit" if "AlphaEdit" in table.methods else table.methods[0])
    if focus not in table.methods:
        raise ValueError(f"Unknown focus method: {focus}")
    directions = dict(higher_is_better or {})
    if set(directions) - set(table.metrics):
        raise ValueError(f"Unknown direction metrics: {sorted(set(directions) - set(table.metrics))}")
    if any(not isinstance(value, bool) for value in directions.values()):
        raise ValueError("Metric directions must be booleans")
    lookup = table.lookup()
    result = []
    for metric in table.metrics:
        direction = 1 if directions.get(metric, True) else -1
        ordered = sorted(table.methods, key=lambda method: -direction * lookup[metric, method].value)
        ranking = [{"method": method, "value": lookup[metric, method].value,
                    "rank": 1 + sum(direction * lookup[metric, other].value >
                                    direction * lookup[metric, method].value for other in table.methods)}
                   for method in ordered]
        alternatives = [method for method in ordered if method != focus]
        focus_value = lookup[metric, focus].value
        comparison = None
        if alternatives:
            best_value = lookup[metric, alternatives[0]].value
            difference = focus_value - best_value
            relative = direction * difference / abs(best_value) * 100 if best_value else None
            if not math.isfinite(difference) or (relative is not None and not math.isfinite(relative)):
                raise ValueError(f"Comparison overflow for {metric!r}; rescale this metric's units")
            comparison = {"methods": [method for method in alternatives if lookup[metric, method].value == best_value],
                          "value": best_value, "difference": difference, "advantage": direction * difference,
                          "relative_advantage_pct": relative}
        result.append({"metric": metric, "direction": "higher" if direction == 1 else "lower",
                       "ranking": ranking, "focus_value": focus_value, "best_alternative": comparison})
    statuses = sorted({row.evidence_status for row in table.observations})
    return {"schema_version": 1, "focus_method": focus, "metrics": result,
            "evidence_statuses": statuses, "sources": sorted({row.source for row in table.observations}),
            "input": {"filename": table.filename, "sha256": table.sha256, "rows": len(table.observations)},
            "experiment_rerun_by_figureflow": False, "cross_metric_aggregate": None,
            "limitations": ["Values are supplied observations, not experiments rerun by FigureFlow.",
                            "Metrics are compared separately; no mean across unlike units is computed.",
                            "No uncertainty, seed count or statistical significance is inferred.",
                            "Relative advantage is undefined when the best alternative is zero."]}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def analysis_markdown(analysis: dict) -> str:
    """A portable, concise audit with explicit interpretation boundaries."""
    lines = ["# Data audit", "", f"Focus method: **{_escape(analysis['focus_method'])}**.", "",
             "Evidence: " + ", ".join(analysis["evidence_statuses"]) + ".",
             "Sources: " + "; ".join(_escape(source) for source in analysis["sources"]) + ".", "",
             "| Metric | Better | Focus | Best alternative | Advantage | Relative advantage |",
             "|---|---|---:|---|---:|---:|"]
    for item in analysis["metrics"]:
        other = item["best_alternative"]
        if other:
            relative = other["relative_advantage_pct"]
            cells = [", ".join(other["methods"]) + f" ({other['value']:g})", f"{other['advantage']:+.4g}",
                     f"{relative:+.2f}%" if relative is not None else "undefined (baseline = 0)"]
        else:
            cells = ["none", "n/a", "n/a"]
        lines.append("| " + " | ".join([_escape(item["metric"]), item["direction"],
                                         f"{item['focus_value']:g}", *map(_escape, cells)]) + " |")
    lines += ["", "A positive advantage favors the focus method. Rankings (ties share a rank):", ""]
    for item in analysis["metrics"]:
        lines.append(f"- {_escape(item['metric'])}: " + "; ".join(
            f"{row['rank']}. {_escape(row['method'])} ({row['value']:g})" for row in item["ranking"]))
    lines += ["", "Interpretation boundaries:", "", *[f"- {item}" for item in analysis["limitations"]], ""]
    return "\n".join(lines)


def _plot_imports():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return matplotlib, plt


def _method_colors(methods: tuple[str, ...], focus: str, palette_name: str = "alphaedit") -> dict[str, str]:
    from matplotlib import colormaps
    from matplotlib.colors import to_hex
    if palette_name not in PALETTE_NAMES:
        raise ValueError(f"Unknown chart palette: {palette_name!r}; choose one of {PALETTE_NAMES}")
    ordered = [focus, *[method for method in methods if method != focus]]
    if palette_name == "alphaedit" and set(methods).issubset(ALPHAEDIT_METHOD_COLORS):
        return {method: ALPHAEDIT_METHOD_COLORS[method] for method in methods}
    colors = list(WELM_IMAGE_RADIAL_PALETTE if palette_name == "welm-image" else PALETTE)
    colors += [to_hex(colormaps["tab20"](index)) for index in range(20)]
    return dict(zip(ordered, colors))


def _evidence_note(table: DataTable) -> str:
    statuses = sorted({row.evidence_status for row in table.observations})
    text = "; ".join(f"{EVIDENCE_CODES[status]} = {status}" for status in statuses)
    return "Evidence: " + text + ". No experiments rerun."


def _source_note(table: DataTable) -> str:
    sources = sorted({row.source for row in table.observations})
    source = sources[0] if len(sources) == 1 else f"{len(sources)} sources; see audit report"
    return "Source: " + (source if len(source) <= 110 else source[:107] + "...")


def _text_width(text: str, fontsize: float, *, weight: str = "normal") -> float:
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextToPath
    prop = FontProperties(family="DejaVu Sans", size=fontsize, weight=weight)
    return TextToPath().get_text_width_height_descent(text, prop, False)[0]


def _wrap_measured(text: str, width: float, fontsize: float, *, name: str,
                   max_lines: int = 2, weight: str = "normal") -> str:
    """Wrap against actual font metrics; fail instead of silently shrinking text."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        if _text_width(word, fontsize, weight=weight) > width:
            raise ValueError(f"{name} contains a word too wide for this layout; shorten it or move it to the caption")
        candidate = (current + " " + word).strip()
        if current and _text_width(candidate, fontsize, weight=weight) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        raise ValueError(f"{name} needs more than {max_lines} lines; shorten it or move the detail to the caption")
    return "\n".join(lines)


def _check_label_lengths(table: DataTable, *, annular: bool) -> None:
    metric_limit, method_limit = (32, 24) if annular else (40, 24)
    if any(len(name) > metric_limit or "\n" in name or "\r" in name for name in table.metrics):
        raise ValueError(f"Metric labels must be single-line and at most {metric_limit} characters; "
                         "use concise labels and keep full names in the caption/audit")
    if any(len(name) > method_limit or "\n" in name or "\r" in name for name in table.methods):
        raise ValueError(f"Method labels must be single-line and at most {method_limit} characters; "
                         "use concise names before rendering")
    if any(len(row.label) > 10 for row in table.observations):
        raise ValueError("Numeric display labels exceed 10 characters; use equivalent scientific notation")


def _curve_label(ax, text: str, angle: float, radius: float, *, fontsize: float, arc: float) -> None:
    """Place measured glyph advances along an arc, upright on both hemispheres."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextToPath
    prop = FontProperties(family="DejaVu Sans", size=fontsize)
    widths = [TextToPath().get_text_width_height_descent(char, prop, False)[0] for char in text]
    # Convert point widths to data distances using the actual fixed axes extent.
    units_per_point = (ax.get_xlim()[1] - ax.get_xlim()[0]) / (ax.bbox.width / ax.figure.dpi * 72)
    radians = [width * units_per_point / radius for width in widths]
    total = sum(radians)
    if total > arc:
        scale = arc / total
        if fontsize * scale < 7.5:
            raise ValueError(f"Metric label {text!r} would be smaller than 7.5 pt at this density; "
                             "shorten it, split the metrics, or use small-multiples")
        radians = [width * scale for width in radians]
        fontsize *= scale
        total = arc
    upper = math.sin(angle) >= 0
    direction = -1 if upper else 1
    cursor = angle - direction * total / 2
    for char, width in zip(text, radians):
        theta = cursor + direction * width / 2
        rotation = math.degrees(theta) - 90 if upper else math.degrees(theta) + 90
        ax.text(radius * math.cos(theta), radius * math.sin(theta), char,
                ha="center", va="center", rotation=rotation, rotation_mode="anchor",
                fontsize=fontsize, color="#22232B", parse_math=False)
        cursor += direction * width


def _save_outputs(fig, table: DataTable, analysis: dict, output_dir: str | Path, stem: str,
                  geometry: dict) -> dict[str, str]:
    requested_target = Path(output_dir).expanduser()
    if requested_target.is_symlink():
        raise ValueError("Output directory is a symlink; choose an explicit directory")
    target = requested_target.resolve()
    paths = {kind: target / f"{stem}.{kind}" for kind in ("png", "pdf", "svg")}
    paths["analysis"] = target / f"{stem}_analysis.json"
    paths["report"] = target / f"{stem}_audit.md"
    paths["manifest"] = target / f"{stem}_manifest.json"
    paths["data"] = target / f"{stem}_data.csv"
    archive = target / f"{stem}_bundle.zip"
    # Validate every planned artifact before writing the first one. This is a
    # scoped overwrite check, not a recursive scan of user-owned directories.
    for path in [*paths.values(), archive]:
        if path.is_symlink():
            raise ValueError(f"Refusing to overwrite symlink output: {path.name}")
        if path.resolve() == table.source_path or (path.exists() and path.samefile(table.source_path)):
            raise ValueError(f"Output {path.name} is the input CSV; choose a different output directory")
        if path.exists() and not path.is_file():
            raise ValueError(f"Output target is not a regular file: {path.name}")
    target.mkdir(parents=True, exist_ok=True)
    # Suppress creation timestamps for reproducible vector exports. SVG glyphs
    # are paths, so opening them on another machine cannot substitute a font.
    fig.savefig(paths["png"], dpi=240, metadata={"Software": "FigureFlow"})
    fig.savefig(paths["pdf"], metadata={"Creator": "FigureFlow", "CreationDate": None, "ModDate": None})
    fig.savefig(paths["svg"], metadata={"Creator": "FigureFlow", "Date": None})
    with paths["data"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["metric", "method", "value", "label", "source", "evidence_status"])
        writer.writerows((row.metric, row.method, row.value, row.label, row.source, row.evidence_status)
                         for row in table.observations)
    paths["analysis"].write_text(json.dumps(analysis, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                                 encoding="utf-8")
    paths["report"].write_text(analysis_markdown(analysis), encoding="utf-8")
    manifest = {"schema_version": 1, "renderer": "figureflow-data-driven", "input": analysis["input"],
                "evidence_statuses": analysis["evidence_statuses"], "sources": analysis["sources"],
                "experiment_rerun_by_figureflow": False,
                "published_values_present": any(status.startswith("published-") for status in analysis["evidence_statuses"]),
                "user_declared_remeasured_values_present": "remeasured" in analysis["evidence_statuses"],
                "chart": geometry,
                "outputs": {kind: {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                            for kind, path in paths.items() if kind != "manifest"}}
    paths["manifest"].write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                                 encoding="utf-8")
    # Archive this run's allowlisted outputs, never unrelated output-dir content.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in paths.values():
            bundle.write(path, arcname=path.name)
    paths["zip"] = archive
    return {kind: str(path) for kind, path in paths.items()}


def render_annular_chart(
    csv_path: str | Path, output_dir: str | Path, *, title: str = "Model comparison",
    subtitle: str = "Performance across metrics", focus_method: str | None = None,
    higher_is_better: Mapping[str, bool] | None = None, palette_name: str = "alphaedit",
) -> dict[str, str]:
    """Render grouped annular bars with explicit independent per-metric scales.

    Supports 2–24 metrics and 1–12 methods (at most 120 bars), nonnegative data. Zero is a short
    baseline tick, never a nonzero bar. Conventional small multiples are better
    when labels are long, values are signed, or precise comparisons are primary.
    """
    table = load_data(csv_path)
    if not 2 <= len(table.metrics) <= 24 or not 1 <= len(table.methods) <= 12:
        raise ValueError("Annular layout supports 2–24 metrics and 1–12 methods; use small multiples otherwise")
    if len(table.metrics) * len(table.methods) > 120:
        raise ValueError("More than 120 bars would be too dense; split the input or use small-multiples")
    if any(row.value < 0 for row in table.observations):
        raise ValueError("Annular bars require nonnegative values; use small-multiples for signed values")
    _check_label_lengths(table, annular=True)
    analysis = analyze_data(table, focus_method=focus_method, higher_is_better=higher_is_better)
    mpl, plt = _plot_imports()
    from matplotlib.patches import Arc, Patch, Wedge
    focus = analysis["focus_method"]
    colors = _method_colors(table.methods, focus, palette_name)
    # Constant order at every group is a redundant encoding independent of color.
    methods = (focus, *[method for method in table.methods if method != focus])
    lookup = table.lookup()
    mixed = len(analysis["evidence_statuses"]) > 1
    count, method_count = len(table.metrics), len(methods)
    size = max(8.6, min(14.5, 7 + count * method_count * 0.045))
    points_per_unit = min(size * 0.93, (size + 0.7) * 0.82) * 72 / 4
    center_title = _wrap_measured(title, 1.42 * points_per_unit, 19, name="Annular title", weight="semibold")
    center_subtitle = _wrap_measured(subtitle, 1.42 * points_per_unit, 10.5, name="Annular subtitle")
    # Fit a maximum of two legend rows using measured names, not character counts.
    legend_columns = min(6, method_count)
    widest_legend = max(_text_width(method, 10) for method in methods) + 42
    while legend_columns > 1 and legend_columns * widest_legend > size * 72 * 0.9:
        legend_columns -= 1
    if math.ceil(method_count / legend_columns) > 2:
        raise ValueError("Method names need more than two legend rows; shorten names or use small-multiples")
    for metric in table.metrics:
        label_width = sum(_text_width(char, 10) for char in metric + " ↑")
        available_width = (2 * math.pi / count) * 0.9 * 0.9 * points_per_unit
        if label_width and 10 * available_width / label_width < 7.5:
            raise ValueError(f"Metric label {metric!r} would be smaller than 7.5 pt at this density; "
                             "shorten it, split the metrics, or use small-multiples")
    with mpl.rc_context(_RC):
        paper = "#F7F7F7" if palette_name == "welm-image" else "white"
        ink = "#191919" if palette_name == "welm-image" else "#242331"
        grid = "#D9D9D9" if palette_name == "welm-image" else "#E8E8EE"
        fig = plt.figure(figsize=(size, size + 0.7), facecolor=paper)
        ax = fig.add_axes([0.035, 0.13, 0.93, 0.82], aspect="equal")
        ax.set(xlim=(-2.08, 2.08), ylim=(-2.08, 2.08))
        ax.axis("off")
        fig.canvas.draw()
        inner, extent = 1.00, 0.76
        group_angle = 2 * math.pi / count
        usable = group_angle * 0.85
        bar_width = usable / method_count
        scales = {metric: max(lookup[metric, method].value for method in methods) for metric in table.metrics}
        font_size = max(6.5, min(9, 11 - method_count * count / 35))
        for index, metric in enumerate(table.metrics):
            center = math.pi / 2 - index * group_angle
            start = center + usable / 2
            scale = scales[metric] or 1.0
            # Subtle 100% arc within each sector, not a universal quantitative axis.
            ax.add_patch(Arc((0, 0), 2 * (inner + extent), 2 * (inner + extent),
                             theta1=math.degrees(center - usable / 2),
                             theta2=math.degrees(center + usable / 2), color=grid, linewidth=0.6))
            if palette_name == "welm-image":
                # The published WeLM-Image radial charts use a segmented outer
                # arc to make benchmark groups visible before reading the bars.
                ax.add_patch(Arc((0, 0), 3.86, 3.86,
                                 theta1=math.degrees(center - usable / 2),
                                 theta2=math.degrees(center + usable / 2),
                                 color="#3BBB74", linewidth=10, capstyle="butt"))
            for method_index, method in enumerate(methods):
                row = lookup[metric, method]
                theta = start - (method_index + 0.5) * bar_width
                half_width = bar_width * 0.43
                height = row.value / scale * extent
                if row.value:
                    ax.add_patch(Wedge((0, 0), inner + height, math.degrees(theta - half_width),
                                       math.degrees(theta + half_width), width=height,
                                       facecolor=colors[method], edgecolor="white", linewidth=0.5))
                else:
                    ax.add_patch(Arc((0, 0), 2 * inner, 2 * inner,
                                     theta1=math.degrees(theta - half_width),
                                     theta2=math.degrees(theta + half_width), color=colors[method], linewidth=1.5))
                radius = inner + height + 0.045
                angle = math.degrees(theta)
                # Numeric labels run along the bar, not across adjacent lanes.
                # Tangential value text collides on long labels such as 437.4.
                right_half = math.cos(theta) >= 0
                rotation = angle if right_half else angle + 180
                label = row.label + (f" [{EVIDENCE_CODES[row.evidence_status]}]" if mixed else "")
                ax.text(radius * math.cos(theta), radius * math.sin(theta), label,
                        ha="left" if right_half else "right", va="center",
                        rotation=rotation, rotation_mode="anchor",
                        fontsize=font_size, color=ink, parse_math=False)
            direction = "↑" if (higher_is_better or {}).get(metric, True) else "↓"
            _curve_label(ax, metric + " " + direction, center, 0.90, fontsize=10,
                         arc=group_angle * 0.90)
        ax.text(0, 0.12, center_title, ha="center", va="center",
                fontsize=19, weight="semibold", color=ink, linespacing=1.35, parse_math=False)
        ax.text(0, -0.23, center_subtitle, ha="center", va="center",
                fontsize=10.5, color="#676571", linespacing=1.45, parse_math=False)
        handles = [Patch(facecolor=colors[method], label=method) for method in methods]
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.080),
                   frameon=False, ncol=legend_columns, fontsize=10, handlelength=1.5,
                   columnspacing=1.8)
        footnotes = ["Each metric is independently scaled to its maximum; zero = baseline tick.",
                     _evidence_note(table), _source_note(table)]
        for index, text in enumerate(footnotes):
            fig.text(0.5, 0.064 - index * 0.019, text, ha="center", fontsize=7.5,
                     color="#676571", parse_math=False)
        try:
            return _save_outputs(fig, table, analysis, output_dir, "annular_chart",
                                 {"kind": "grouped-annular", "palette": palette_name,
                                  "method_order": list(methods), "colors": colors,
                                  "normalization": "per-metric maximum", "metric_maxima": scales,
                                  "zero_encoding": "baseline tick; zero radial length", "value_labels": True})
        finally:
            plt.close(fig)


def render_small_multiples(
    csv_path: str | Path, output_dir: str | Path, *, title: str = "Model comparison",
    focus_method: str | None = None, higher_is_better: Mapping[str, bool] | None = None,
    palette_name: str = "alphaedit",
) -> dict[str, str]:
    """Render conventional per-metric panels in original units, including negatives."""
    table = load_data(csv_path)
    if len(table.metrics) > 36 or len(table.methods) > 20:
        raise ValueError("Small multiples support at most 36 metrics and 20 methods; split the input")
    _check_label_lengths(table, annular=False)
    analysis = analyze_data(table, focus_method=focus_method, higher_is_better=higher_is_better)
    mpl, plt = _plot_imports()
    focus = analysis["focus_method"]
    colors = _method_colors(table.methods, focus, palette_name)
    lookup = table.lookup()
    columns = min(3, len(table.metrics))
    rows = math.ceil(len(table.metrics) / columns)
    title_text = _wrap_measured(title, 3.0 * columns * 72 * 0.9, 16, name="Chart title")
    subtitle_text = _wrap_measured("Original values; independent panel axes", 3.0 * columns * 72 * 0.9,
                                  16, name="Panel axis note")
    metric_titles = {metric: _wrap_measured(metric, 2.8 * 72, 10.5, name="Metric label")
                     for metric in table.metrics}
    if max(_text_width(method, 9) for method in table.methods) > 1.0 * 72:
        raise ValueError("Method names would consume the panel width; shorten names to about 12 characters")
    mixed = len(analysis["evidence_statuses"]) > 1
    with mpl.rc_context(_RC):
        panel_height = max(2.4, len(table.methods) * 0.25 + 0.8)
        fig, axes = plt.subplots(rows, columns, figsize=(3.0 * columns, panel_height * rows + 1.0),
                                 squeeze=False, layout="constrained")
        for index, ax in enumerate(axes.flat):
            if index >= len(table.metrics):
                ax.axis("off")
                continue
            metric = table.metrics[index]
            values = [lookup[metric, method].value for method in table.methods]
            bars = ax.barh(range(len(table.methods)), values,
                           color=[colors[method] for method in table.methods], height=0.64)
            labels = [lookup[metric, method].label +
                      (f" [{EVIDENCE_CODES[lookup[metric, method].evidence_status]}]" if mixed else "")
                      for method in table.methods]
            ax.bar_label(bars, labels=labels, padding=4, fontsize=9)
            ax.set_yticks(range(len(table.methods)), table.methods, fontsize=9)
            ax.invert_yaxis()
            direction = "higher is better" if (higher_is_better or {}).get(metric, True) else "lower is better"
            ax.set_title(f"{metric_titles[metric]}\n{direction}", loc="left", fontsize=10.5, parse_math=False)
            ax.axvline(0, color="#B2B1BA", linewidth=0.6)
            ax.grid(axis="x", color="#E9E9EE", linewidth=0.6)
            ax.set_axisbelow(True)
            ax.margins(x=0.25)
            ax.tick_params(axis="both", length=0, labelsize=9)
            ax.spines["left"].set_visible(False)
            ax.spines["bottom"].set_color("#D2D1D8")
        fig.suptitle(title_text + "\n" + subtitle_text, fontsize=16, parse_math=False)
        fig.supxlabel(_evidence_note(table) + "\n" + _source_note(table), fontsize=8, color="#676571")
        try:
            return _save_outputs(fig, table, analysis, output_dir, "small_multiples",
                                 {"kind": "small-multiples", "palette": palette_name,
                                  "method_order": list(table.methods),
                                  "colors": colors, "normalization": "none; original values",
                                  "independent_panel_axes": True, "value_labels": True})
        finally:
            plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chart", "--kind", choices=("annular", "small-multiples"), default="annular")
    parser.add_argument("--title", default="Model comparison")
    parser.add_argument("--focus-method")
    parser.add_argument("--palette", choices=PALETTE_NAMES, default="alphaedit",
                        help="Color system for the chart. 'welm-image' reuses the green radial-chart grammar.")
    parser.add_argument("--lower-is-better", action="append", default=[], metavar="METRIC")
    args = parser.parse_args(argv)
    renderer = render_annular_chart if args.chart == "annular" else render_small_multiples
    try:
        result = renderer(args.csv, args.output_dir, title=args.title, focus_method=args.focus_method,
                          higher_is_better={metric: False for metric in args.lower_is_better},
                          palette_name=args.palette)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
