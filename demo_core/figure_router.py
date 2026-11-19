"""Role-first routing for publication figures.

The router is intentionally declarative: it chooses the deterministic module
and QA gates from a validated FigureSpec. It never lets a prompt select an
arbitrary executable path.
"""

from __future__ import annotations

from typing import Any

from .schemas import FigureSpec


ROLE_ROUTES: dict[str, dict[str, Any]] = {
    "main-figure": {
        "renderer": "render_overview.py",
        "case_renderer": "render_case_study_flow.py",
        "qa": ["role_claim", "case_share", "paper_width", "independent_review"],
    },
    "pipeline": {
        "renderer": "render_overview.py",
        "case_renderer": "render_case_study_flow.py",
        "qa": ["input_output", "stage_order", "native_labels", "paper_width"],
    },
    "case-study": {
        "renderer": "extract_frames.py + deterministic composer",
        "case_renderer": "render_case_study_flow.py",
        "qa": ["source_manifest", "frame_crops", "case_share", "paper_width"],
    },
    "data-analysis": {
        "renderer": "render_data_figure.py",
        "case_renderer": None,
        "qa": ["data_identity", "uncertainty", "native_axes", "paper_width"],
    },
}

LAYOUT_ROUTES: dict[str, dict[str, Any]] = {
    "tiered-pipeline": {
        "renderer": "cases/looped_comic_case_studies/build_tiered_looped_demo.py",
        "layout_spec": "skill/design-research-figures/assets/layouts/tiered_pipeline_reference.json",
        "qa": ["orthogonal_connectors", "shared_artifact", "native_text", "source_manifest", "paper_width"],
    }
}


def route_figure(spec: FigureSpec) -> dict[str, Any]:
    """Return a stable, non-executable routing record for a validated spec."""

    route = dict(ROLE_ROUTES[spec.role])
    route.update(
        {
            "figure_id": spec.figure_id,
            "role": spec.role,
            "layout_family": spec.layout_family,
            "case_layers": len(spec.case_layers),
            "case_share": spec.case_share,
            "requires_source_manifest": bool(spec.case_layers),
            "evidence_status": spec.evidence_status,
            "layout_route": LAYOUT_ROUTES.get(spec.layout_family),
        }
    )
    return route
