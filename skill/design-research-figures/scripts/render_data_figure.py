#!/usr/bin/env python3
"""Render a multi-panel paper data figure from a YAML specification."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from visual_common import (
    PALETTE,
    color,
    configure_matplotlib,
    load_yaml,
    resolve_from,
    save_figure,
    status_colors,
    write_artifact_manifest,
)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _read_frame(spec_path: Path, panel: dict[str, Any]) -> pd.DataFrame:
    source = panel.get("csv")
    if not source:
        raise ValueError(f"panel {panel.get('title', '<untitled>')} needs csv")
    return pd.read_csv(resolve_from(spec_path, source))


def _draw_standard(ax, frame: pd.DataFrame, panel: dict[str, Any]) -> None:
    for series in panel.get("series", []):
        subset = frame
        if "where" in series:
            column, expected = next(iter(series["where"].items()))
            subset = subset[subset[column] == expected]
        x = subset[series["x"]]
        y = subset[series["y"]]
        series_color = color(series.get("color"), "blue")
        kind = series.get("kind", "line")
        label = series.get("label")
        if kind == "scatter":
            ax.scatter(
                x,
                y,
                s=series.get("size", 28),
                color=series_color,
                edgecolor="white",
                linewidth=0.55,
                alpha=series.get("alpha", 0.95),
                label=label,
                zorder=3,
            )
        else:
            ax.plot(
                x,
                y,
                color=series_color,
                linewidth=series.get("width", 2.1),
                linestyle=series.get("linestyle", "-"),
                marker=series.get("marker"),
                markersize=series.get("markersize", 4.2),
                label=label,
                alpha=series.get("alpha", 1.0),
                zorder=3,
            )
        if series.get("low") and series.get("high"):
            ax.fill_between(
                x,
                subset[series["low"]],
                subset[series["high"]],
                color=series_color,
                alpha=series.get("band_alpha", 0.12),
                linewidth=0,
                zorder=1,
            )


def _draw_grouped_bar(ax, frame: pd.DataFrame, panel: dict[str, Any]) -> None:
    category = panel["category"]
    labels = frame[category].astype(str).tolist()
    series = panel.get("series", [])
    positions = np.arange(len(labels), dtype=float)
    width = min(0.72 / max(1, len(series)), 0.34)
    for index, item in enumerate(series):
        offset = (index - (len(series) - 1) / 2) * width
        bars = ax.bar(
            positions + offset,
            frame[item["y"]],
            width=width * 0.88,
            color=color(item.get("color"), "blue"),
            label=item.get("label"),
            edgecolor="white",
            linewidth=0.6,
            zorder=3,
        )
        if item.get("labels", False):
            ax.bar_label(bars, fmt=item.get("label_format", "%.0f"), padding=2, fontsize=6.4)
    ax.set_xticks(positions, labels, rotation=panel.get("rotation", 0))


def _decorate_axis(ax, panel: dict[str, Any], letter: str) -> None:
    ax.set_title(f"({letter}) {panel['title']}", loc="left", fontweight="bold")
    ax.set_xlabel(panel.get("x_label", ""))
    ax.set_ylabel(panel.get("y_label", ""))
    if panel.get("x_scale"):
        ax.set_xscale(panel["x_scale"])
    if panel.get("y_scale"):
        ax.set_yscale(panel["y_scale"])
    if panel.get("x_lim"):
        ax.set_xlim(*panel["x_lim"])
    if panel.get("y_lim"):
        ax.set_ylim(*panel["y_lim"])
    if panel.get("invert_y"):
        ax.invert_yaxis()
    for gate in panel.get("gates", []):
        gate_color = color(gate.get("color"), "orange")
        if gate.get("orientation", "horizontal") == "vertical":
            ax.axvline(gate["value"], color=gate_color, lw=1.2, ls=gate.get("linestyle", "--"))
        else:
            ax.axhline(gate["value"], color=gate_color, lw=1.2, ls=gate.get("linestyle", "--"))
        if gate.get("label"):
            ax.text(
                gate.get("label_x", 0.02),
                gate.get("label_y", 0.96),
                gate["label"],
                transform=ax.transAxes,
                color=gate_color,
                fontsize=6.7,
                va="top",
                ha="left",
            )
    ax.grid(alpha=0.18, linewidth=0.6, color=PALETTE["line"], zorder=0)
    if any(item.get("label") for item in panel.get("series", [])):
        ax.legend(
            frameon=False,
            loc=panel.get("legend_location", "best"),
            ncol=panel.get("legend_columns", 1),
        )


def render(spec_path: Path, output_dir: Path) -> tuple[Path, Path]:
    configure_matplotlib(display=False)
    spec = load_yaml(spec_path)
    panels = spec.get("panels", [])
    if not panels:
        raise ValueError("data-figure spec has no panels")
    figsize = spec.get("figsize", [11.4, 3.6])
    fig, axes = plt.subplots(1, len(panels), figsize=figsize, squeeze=False)
    fig.patch.set_facecolor("white")
    axes = axes[0]
    fig.subplots_adjust(
        left=spec.get("left", 0.055),
        right=spec.get("right", 0.99),
        bottom=spec.get("bottom", 0.19),
        top=spec.get("top", 0.70),
        wspace=spec.get("wspace", 0.36),
    )

    for index, (ax, panel) in enumerate(zip(axes, panels)):
        frame = _read_frame(spec_path, panel)
        if panel.get("type", "standard") == "grouped_bar":
            _draw_grouped_bar(ax, frame, panel)
        else:
            _draw_standard(ax, frame, panel)
        _decorate_axis(ax, panel, chr(ord("a") + index))

    fig.text(
        0.055,
        0.96,
        spec["title"],
        fontsize=spec.get("title_size", 14.6),
        fontweight="bold",
        color=PALETTE["navy"],
        va="top",
    )
    if spec.get("subtitle"):
        fig.text(0.055, 0.875, spec["subtitle"], fontsize=8.2, color=PALETTE["gray"])
    if spec.get("status"):
        foreground, background, border = status_colors(spec.get("status_kind", spec["evidence_status"]))
        fig.text(
            0.055,
            0.795,
            spec["status"],
            fontsize=8.6,
            fontweight="bold",
            color=foreground,
            bbox={"boxstyle": "round,pad=0.28", "facecolor": background, "edgecolor": border},
        )
    if spec.get("footer"):
        fig.text(0.99, 0.035, spec["footer"], ha="right", fontsize=6.9, color=PALETTE["gray"])

    stem = output_dir / spec.get("output_name", "data_figure")
    result = save_figure(fig, stem, dpi=spec.get("dpi", 240))
    plt.close(fig)
    input_paths = [resolve_from(spec_path, panel["csv"]) for panel in panels]
    write_artifact_manifest(stem, spec_path, spec, result, inputs=input_paths)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    pdf, png = render(args.spec.resolve(), args.output_dir.resolve())
    print(pdf)
    print(png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
