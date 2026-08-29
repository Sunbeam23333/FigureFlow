#!/usr/bin/env python3
"""Render a radar plus GPU strong-scaling audit figure from YAML and optional CSV."""

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


def _read_optional_frame(spec_path: Path, panel: dict[str, Any]) -> pd.DataFrame | None:
    source = panel.get("csv")
    return pd.read_csv(resolve_from(spec_path, source)) if source else None


def _vector(
    item: dict[str, Any],
    frame: pd.DataFrame | None,
    *,
    values_key: str = "values",
    column_key: str = "column",
) -> np.ndarray:
    if values_key in item:
        values = item[values_key]
    elif column_key in item:
        if frame is None:
            raise ValueError(f"{column_key} requires a panel-level csv")
        values = frame[item[column_key]].to_numpy()
    else:
        raise ValueError(f"series needs either {values_key} or {column_key}")
    result = np.asarray(values, dtype=float)
    if result.ndim != 1 or not len(result):
        raise ValueError("series values must be a non-empty one-dimensional sequence")
    if not np.isfinite(result).all():
        raise ValueError("series contains a non-finite value")
    return result


def _optional_vector(
    item: dict[str, Any],
    frame: pd.DataFrame | None,
    *,
    values_key: str,
    column_key: str,
) -> np.ndarray | None:
    if values_key not in item and column_key not in item:
        return None
    return _vector(item, frame, values_key=values_key, column_key=column_key)


def _require_same_length(reference: np.ndarray, values: np.ndarray, label: str) -> None:
    if len(values) != len(reference):
        raise ValueError(f"{label} has {len(values)} values; expected {len(reference)}")


def _draw_radar(ax, spec_path: Path, panel: dict[str, Any]) -> None:
    frame = _read_optional_frame(spec_path, panel)
    if "metrics" in panel:
        metrics = [str(item) for item in panel["metrics"]]
    elif frame is not None and panel.get("metric_column"):
        metrics = frame[panel["metric_column"]].astype(str).tolist()
    else:
        raise ValueError("radar panel needs metrics or csv + metric_column")
    if len(metrics) < 3:
        raise ValueError("radar panel needs at least three metrics")
    series_items = panel.get("series", [])
    if len(series_items) != 2:
        raise ValueError("radar panel needs exactly two series: baseline and candidate")

    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False)
    closed_angles = np.r_[angles, angles[0]]
    for index, series in enumerate(series_items):
        values = _vector(series, frame)
        _require_same_length(angles, values, series.get("label", f"series {index + 1}"))
        closed_values = np.r_[values, values[0]]
        series_color = color(series.get("color"), "teal" if index else "gray")
        ax.plot(
            closed_angles,
            closed_values,
            color=series_color,
            linewidth=series.get("width", 2.25),
            linestyle=series.get("linestyle", "-" if index else "--"),
            marker=series.get("marker", "o"),
            markersize=series.get("markersize", 3.7),
            label=series.get("label"),
            zorder=3 + index,
        )
        ax.fill(
            closed_angles,
            closed_values,
            color=series_color,
            alpha=series.get("fill_alpha", 0.10 if index else 0.055),
            linewidth=0,
            zorder=1 + index,
        )

    value_lim = panel.get("value_lim", [0.0, 1.0])
    ax.set_ylim(*value_lim)
    ax.set_theta_offset(np.pi / 2 + np.deg2rad(panel.get("rotation_degrees", 0)))
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels(metrics, fontsize=panel.get("metric_fontsize", 7.5), color=PALETTE["navy"])
    rings = panel.get("rings", [0.25, 0.50, 0.75, 1.0])
    ring_labels = panel.get("ring_labels", [f"{100 * value:.0f}" for value in rings])
    ax.set_yticks(rings)
    ax.set_yticklabels(ring_labels, fontsize=6.3, color=PALETTE["gray"])
    ax.set_rlabel_position(panel.get("ring_label_angle", 112))
    ax.grid(color=PALETTE["line"], alpha=0.68, linewidth=0.65)
    ax.spines["polar"].set_color(PALETTE["line"])
    ax.spines["polar"].set_linewidth(0.8)
    # Polar set_title() uses a projection-specific anchor that can jump into the
    # figure header.  An axes-relative label keeps both panel titles aligned.
    ax.text(
        panel.get("title_x", 0.50),
        panel.get("title_y", 1.08),
        f"(a) {panel.get('title', 'Capability audit')}",
        transform=ax.transAxes,
        fontsize=10.3,
        fontweight="bold",
        color=PALETTE["navy"],
        ha=panel.get("title_ha", "center"),
        va="bottom",
    )
    if any(item.get("label") for item in series_items):
        ax.legend(
            frameon=False,
            loc=panel.get("legend_location", "lower center"),
            bbox_to_anchor=panel.get("legend_anchor", [0.5, -0.22]),
            ncol=panel.get("legend_columns", 2),
            handlelength=2.6,
        )


def _draw_scaling_series(
    ax,
    x: np.ndarray,
    item: dict[str, Any],
    frame: pd.DataFrame | None,
    *,
    default_color: str,
    default_linestyle: str = "-",
):
    values = _vector(item, frame)
    _require_same_length(x, values, item.get("label", "scaling series"))
    series_color = color(item.get("color"), default_color)
    line = ax.plot(
        x,
        values,
        label=item.get("label"),
        color=series_color,
        linewidth=item.get("width", 2.25),
        linestyle=item.get("linestyle", default_linestyle),
        marker=item.get("marker", "o"),
        markersize=item.get("markersize", 4.1),
        markerfacecolor=item.get("markerfacecolor", series_color),
        markeredgecolor="white",
        markeredgewidth=0.55,
        zorder=4,
    )[0]
    low = _optional_vector(item, frame, values_key="low_values", column_key="low_column")
    high = _optional_vector(item, frame, values_key="high_values", column_key="high_column")
    if (low is None) != (high is None):
        raise ValueError(f"{item.get('label', 'series')} needs both low and high interval bounds")
    if low is not None and high is not None:
        _require_same_length(x, low, f"{item.get('label', 'series')} low interval")
        _require_same_length(x, high, f"{item.get('label', 'series')} high interval")
        if np.any(low > high):
            raise ValueError(f"{item.get('label', 'series')} has low interval values above high values")
        ax.fill_between(
            x,
            low,
            high,
            color=series_color,
            alpha=item.get("band_alpha", 0.13),
            linewidth=0,
            zorder=2,
        )
    return line, values


def _draw_scaling(ax, spec_path: Path, panel: dict[str, Any]) -> None:
    frame = _read_optional_frame(spec_path, panel)
    if "gpu_values" in panel:
        x = np.asarray(panel["gpu_values"], dtype=float)
    elif frame is not None and panel.get("gpu_column"):
        x = np.asarray(frame[panel["gpu_column"]], dtype=float)
    else:
        raise ValueError("scaling panel needs gpu_values or csv + gpu_column")
    if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or np.any(x <= 0):
        raise ValueError("GPU counts must be a finite, positive one-dimensional sequence")
    if len(x) > 1 and np.any(np.diff(x) <= 0):
        raise ValueError("GPU counts must be strictly increasing")

    throughput = panel.get("throughput")
    if not isinstance(throughput, dict):
        raise ValueError("scaling panel needs one throughput series")
    left_line, throughput_values = _draw_scaling_series(
        ax, x, throughput, frame, default_color="blue"
    )
    left_lines = [left_line]
    if panel.get("show_ideal", True):
        ideal = throughput_values[0] * x / x[0]
        ideal_line = ax.plot(
            x,
            ideal,
            color=color(panel.get("ideal_color"), "gray"),
            linewidth=1.15,
            linestyle=panel.get("ideal_linestyle", ":"),
            label=panel.get("ideal_label", "ideal linear"),
            zorder=1,
        )[0]
        left_lines.append(ideal_line)

    x_scale = panel.get("x_scale", "log")
    if x_scale == "log":
        ax.set_xscale(x_scale, base=panel.get("x_base", 2))
    else:
        ax.set_xscale(x_scale)
    ax.set_xticks(x)
    ax.set_xticklabels([str(int(value)) if value.is_integer() else f"{value:g}" for value in x])
    ax.set_xlabel(panel.get("x_label", "GPU count"))
    ax.set_ylabel(panel.get("throughput_label", "throughput"), color=color("blue"))
    ax.tick_params(axis="y", colors=color("blue"))
    if panel.get("throughput_lim"):
        ax.set_ylim(*panel["throughput_lim"])
    ax.grid(axis="both", alpha=0.18, linewidth=0.6, color=PALETTE["line"], zorder=0)

    right_ax = ax.twinx()
    right_ax.spines["top"].set_visible(False)
    right_ax.spines["right"].set_color(color(panel.get("right_axis_color"), "teal"))
    right_lines = []
    defaults = [("teal", "-"), ("orange", "--"), ("violet", "-.")]
    for index, item in enumerate(panel.get("right_series", [])):
        default_color, default_style = defaults[index % len(defaults)]
        line, _ = _draw_scaling_series(
            right_ax,
            x,
            item,
            frame,
            default_color=default_color,
            default_linestyle=default_style,
        )
        right_lines.append(line)
    if not right_lines:
        raise ValueError("scaling panel needs at least one right_series item")
    right_ax.set_ylabel(
        panel.get("right_label", "efficiency / communication (%)"),
        color=color(panel.get("right_axis_color"), "teal"),
    )
    right_ax.tick_params(axis="y", colors=color(panel.get("right_axis_color"), "teal"))
    if panel.get("right_lim"):
        right_ax.set_ylim(*panel["right_lim"])

    ax.set_title(
        f"(b) {panel.get('title', 'GPU strong scaling')}",
        loc="left",
        fontsize=10.3,
        fontweight="bold",
        color=PALETTE["navy"],
        pad=12,
    )
    handles = left_lines + right_lines
    ax.legend(
        handles,
        [line.get_label() for line in handles],
        frameon=False,
        loc=panel.get("legend_location", "upper left"),
        ncol=panel.get("legend_columns", 2),
        columnspacing=1.0,
        handlelength=2.3,
    )
    if panel.get("annotation"):
        ax.text(
            panel.get("annotation_x", 0.98),
            panel.get("annotation_y", 0.04),
            panel["annotation"],
            transform=ax.transAxes,
            ha=panel.get("annotation_ha", "right"),
            va=panel.get("annotation_va", "bottom"),
            fontsize=6.7,
            color=PALETTE["gray"],
        )


def render(spec_path: Path, output_dir: Path) -> tuple[Path, Path]:
    configure_matplotlib(display=False)
    spec = load_yaml(spec_path)
    radar = spec.get("radar")
    scaling = spec.get("scaling")
    if not isinstance(radar, dict) or not isinstance(scaling, dict):
        raise ValueError("audit-figure spec needs radar and scaling mappings")

    figsize = spec.get("figsize", [8.4, 4.0])
    fig = plt.figure(figsize=figsize, facecolor="white")
    grid = fig.add_gridspec(
        1,
        2,
        width_ratios=spec.get("width_ratios", [0.92, 1.38]),
        left=spec.get("left", 0.07),
        right=spec.get("right", 0.93),
        bottom=spec.get("bottom", 0.19),
        top=spec.get("top", 0.72),
        wspace=spec.get("wspace", 0.36),
    )
    radar_ax = fig.add_subplot(grid[0, 0], projection="polar")
    scaling_ax = fig.add_subplot(grid[0, 1])
    _draw_radar(radar_ax, spec_path, radar)
    _draw_scaling(scaling_ax, spec_path, scaling)

    fig.text(
        spec.get("left", 0.07),
        0.965,
        spec["title"],
        fontsize=spec.get("title_size", 14.4),
        fontweight="bold",
        color=PALETTE["navy"],
        va="top",
    )
    if spec.get("subtitle"):
        fig.text(
            spec.get("left", 0.07),
            0.895,
            spec["subtitle"],
            fontsize=8.1,
            color=PALETTE["gray"],
            va="top",
        )
    if spec.get("status"):
        foreground, background, border = status_colors(spec.get("status_kind", spec["evidence_status"]))
        fig.text(
            spec.get("left", 0.07),
            0.815,
            spec["status"],
            fontsize=8.2,
            fontweight="bold",
            color=foreground,
            bbox={"boxstyle": "round,pad=0.28", "facecolor": background, "edgecolor": border},
            va="center",
        )
    if spec.get("footer"):
        fig.text(
            spec.get("right", 0.93),
            0.035,
            spec["footer"],
            ha="right",
            fontsize=6.8,
            color=PALETTE["gray"],
        )

    stem = output_dir / spec.get("output_name", "audit_figure")
    result = save_figure(fig, stem, dpi=spec.get("dpi", 240))
    plt.close(fig)
    input_paths = [
        resolve_from(spec_path, panel["csv"])
        for panel in (radar, scaling)
        if panel.get("csv")
    ]
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
