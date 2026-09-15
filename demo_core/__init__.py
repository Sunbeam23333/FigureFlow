"""FigureFlow modules; offline charts do not import model SDKs or web UI."""


def __getattr__(name: str):
    # Preserve the public imports without forcing all workflow dependencies on
    # ``python -m demo_core.data_analysis`` or the portable reproduction bundle.
    if name == "run_pipeline":
        from .pipeline import run_pipeline
        return run_pipeline
    if name in {"FigurePlan", "ReferenceAsset"}:
        from .schemas import FigurePlan, ReferenceAsset
        return {"FigurePlan": FigurePlan, "ReferenceAsset": ReferenceAsset}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["FigurePlan", "ReferenceAsset", "run_pipeline"]
