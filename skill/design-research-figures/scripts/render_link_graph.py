#!/usr/bin/env python3
"""Render an evidence-aware transfer/link graph from YAML."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path
from typing import Any

from visual_common import PALETTE, color, configure_matplotlib, load_yaml, save_figure, status_colors, write_artifact_manifest

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path as MplPath
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, PathPatch


def _bezier(ax, p0, p1, edge_color, width, alpha=0.58, radial_pull=0.22) -> None:
    p0, p1 = np.asarray(p0), np.asarray(p1)
    midpoint = (p0 + p1) / 2
    control = midpoint * radial_pull
    path = MplPath(
        [p0, control, control, p1],
        [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4],
    )
    ax.add_patch(
        PathPatch(
            path,
            fill=False,
            linewidth=width,
            color=edge_color,
            alpha=alpha,
            capstyle="round",
            zorder=1,
        )
    )


def _node_position(node: dict[str, Any]) -> np.ndarray:
    if "x" in node and "y" in node:
        return np.array([float(node["x"]), float(node["y"])])
    angle = np.deg2rad(float(node.get("angle", 90)))
    radius = float(node.get("radius", 1.0))
    return np.array([np.cos(angle) * radius, np.sin(angle) * radius])


def _draw_graph(ax, spec: dict[str, Any]) -> None:
    nodes = spec.get("nodes", [])
    positions = {node["id"]: _node_position(node) for node in nodes}
    node_map = {node["id"]: node for node in nodes}

    for edge in spec.get("edges", []):
        source = positions[edge["source"]]
        target = positions[edge["target"]]
        edge_color = color(edge.get("color"), node_map[edge["target"]].get("color", "blue"))
        if edge.get("style", "solid") in {"nontransfer", "dashed", "negative"}:
            arrow = FancyArrowPatch(
                source,
                target,
                connectionstyle=f"arc3,rad={edge.get('curvature', -0.35)}",
                arrowstyle="-|>",
                mutation_scale=11,
                linewidth=edge.get("width", 1.8),
                linestyle="--",
                color=edge_color,
                alpha=edge.get("alpha", 0.9),
                zorder=2,
            )
            ax.add_patch(arrow)
        else:
            _bezier(
                ax,
                source,
                target,
                edge_color,
                edge.get("width", 3.2),
                edge.get("alpha", 0.58),
                edge.get("radial_pull", 0.22),
            )

    for node in nodes:
        position = positions[node["id"]]
        node_color = color(node.get("color"), "blue")
        radius = float(node.get("node_radius", 0.13))
        ax.add_patch(Circle(position, radius, facecolor="white", edgecolor=node_color, lw=2.8, zorder=4))
        ax.add_patch(Circle(position, radius * 0.43, facecolor=node_color, edgecolor="none", zorder=5))
        label_offset = position * float(node.get("label_offset", 0.23))
        if abs(position[0]) < 0.16:
            horizontal = "center"
        else:
            horizontal = "left" if position[0] > 0 else "right"
        if abs(position[1]) < 0.16:
            vertical = "center"
        else:
            vertical = "bottom" if position[1] > 0 else "top"
        ax.text(
            *(position + label_offset),
            node.get("label", node["id"]),
            ha=node.get("ha", horizontal),
            va=node.get("va", vertical),
            fontsize=9.2,
            color=PALETTE["navy"],
            fontweight=700,
            zorder=6,
        )

    center = spec.get("center", {})
    ax.text(
        0,
        0,
        center.get("label", "shared\ncoordinate"),
        ha="center",
        va="center",
        fontsize=8.5,
        color=PALETTE["gray"],
    )
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(*spec.get("x_lim", [-1.4, 1.4]))
    ax.set_ylim(*spec.get("y_lim", [-1.35, 1.3]))


def _draw_notes(ax, spec: dict[str, Any]) -> None:
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.02, 0.94, spec.get("notes_title", "How to read the graph"), fontsize=11.5, fontweight="bold", color=PALETTE["navy"])
    y = 0.84
    for note in spec.get("notes", []):
        note_color = color(note.get("color"), "blue")
        height = float(note.get("height", 0.16))
        box = FancyBboxPatch(
            (0.02, y - height + 0.025),
            0.95,
            height,
            boxstyle="round,pad=0.018,rounding_size=0.025",
            facecolor=color(note.get("background"), "offwhite"),
            edgecolor=note_color,
            linewidth=1.2,
        )
        ax.add_patch(box)
        ax.text(0.055, y - 0.02, note["title"], fontsize=8.8, fontweight="bold", color=note_color, va="top")
        wrapped = textwrap.fill(note.get("text", ""), width=int(note.get("wrap_width", 50)))
        ax.text(0.055, y - 0.075, wrapped, fontsize=7.4, color=PALETTE["gray"], va="top", linespacing=1.12)
        y -= height + 0.045
    if spec.get("gate"):
        gate = spec["gate"]
        ax.text(
            0.02,
            0.035,
            gate,
            fontsize=8.1,
            fontweight="bold",
            color=PALETTE["red"],
            bbox={"boxstyle": "round,pad=0.35", "facecolor": PALETTE["light_red"], "edgecolor": "#E7B7AA"},
        )


def render(spec_path: Path, output_dir: Path) -> tuple[Path, Path]:
    configure_matplotlib(display=False)
    spec = load_yaml(spec_path)
    figsize = spec.get("figsize", [10.8, 4.8])
    fig = plt.figure(figsize=figsize, facecolor="white")
    grid = fig.add_gridspec(
        1,
        2,
        width_ratios=spec.get("width_ratios", [1.55, 0.82]),
        left=0.055,
        right=0.985,
        bottom=0.12,
        top=0.72,
        wspace=0.12,
    )
    graph_ax = fig.add_subplot(grid[0, 0])
    notes_ax = fig.add_subplot(grid[0, 1])
    _draw_graph(graph_ax, spec)
    _draw_notes(notes_ax, spec)

    fig.text(0.055, 0.965, spec["title"], fontsize=14.6, fontweight="bold", color=PALETTE["navy"], va="top")
    if spec.get("subtitle"):
        fig.text(0.055, 0.875, spec["subtitle"], fontsize=8.3, color=PALETTE["gray"])
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
        fig.text(0.985, 0.035, spec["footer"], ha="right", fontsize=6.9, color=PALETTE["gray"])

    stem = output_dir / spec.get("output_name", "link_graph")
    result = save_figure(fig, stem, dpi=spec.get("dpi", 240))
    plt.close(fig)
    write_artifact_manifest(stem, spec_path, spec, result)
    return result


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
