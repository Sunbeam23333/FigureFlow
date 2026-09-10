"""Stateful, tool-using research-figure workflow on the standard OpenAI API.

The agent can redesign the scene rather than fill a fixed slide template. Local
sources are explicit, tool arguments are data, and publishing is not a tool.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile

from .context_bundle import ContextBundle, digest, image_input
from .model_policy import SolGateway
from .research_assets import ResearchAssets, ResearchAssetError
from .scene_patch import apply_scene_patch, hash_scene, validate_symbol_consistency

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = ROOT / "skill" / "design-research-figures" / "references"


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _official_brand(record):
    provenance = record.get("provenance", {})
    return record.get("kind") == "official-brand" or (
        isinstance(provenance, dict) and provenance.get("provider") == "official-brand")


def _without_response_ids(value):
    """Copy public metadata without provider IDs; never mutate local records.

    This is deliberately narrow redaction, not a general public-safety claim.
    Scene/patch contents are not rewritten because their hashes must replay.
    """
    if isinstance(value, dict):
        return {key: _without_response_ids(item) for key, item in value.items() if key != "response_id"}
    if isinstance(value, list):
        return [_without_response_ids(item) for item in value]
    if isinstance(value, tuple):
        return [_without_response_ids(item) for item in value]
    return value


def response_text(response):
    direct = value(response, "output_text")
    if direct:
        return direct
    return "".join(value(content, "text", "") for item in value(response, "output", [])
                   for content in value(item, "content", []) if value(content, "type") == "output_text")


def parse_response(response):
    text = response_text(response).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


def safe_id(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", raw):
        raise ValueError("Use a short alphanumeric ID, not a path")
    return raw


def validate_action(action):
    if not isinstance(action, dict):
        raise ValueError("Each action must be an object")
    tool = action.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError("Each action must have a non-empty tool string")
    arguments = action.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("Each action must have an arguments object")
    return tool, arguments


def validate_action_batch(answer):
    if not isinstance(answer, dict):
        raise ValueError("Response must be an object with summary and actions")
    actions = answer.get("actions")
    if not isinstance(actions, list):
        raise ValueError("actions must be a list")
    if not 1 <= len(actions) <= 12:
        raise ValueError(f"actions must contain 1-12 items; received {len(actions)}")
    for index, action in enumerate(actions):
        try:
            validate_action(action)
        except ValueError as exc:
            raise ValueError(f"actions[{index}]: {exc}") from exc
    return actions


TOOLS = r'''
Tools (each action is {"tool": name, "arguments": {...}}):
- record_design: {"design": {"takeaway":str,"reading_order":str,"claims":[{"id":str,"text":str,"source_id":"S1","page":int,"quote":str}],"essential_relations":[object],"caption":str,"uncertainties":[str]}}. Quote each important factual mechanism. Exact source quotes are checked, not invented. The object can include your visual choices and rationale; no fixed node/edge count.
- search_source: {"query":str}. Literal search over complete supplied files; returns source/page/excerpt.
- read_page: {"source_id":"S1","page":int}. Returns page pixels from a registered PDF. Useful for equations/figures.
- inspect_image: {"image_id":str,"crop":[left,top,right,bottom] optional}. Read registered asset or rendered candidate, optionally inspect a pixel crop.
- measure_text: {"text":str,"font_size":number,"font_family":"DejaVu Sans","font_weight":400,"line_height":1.2}. Measure before placing exact text.
- search_assets: {"query":str,"limit":1..3,"provider":"wikimedia-commons"|"official-brand" optional}. Only if reference_search capability is enabled. Default Commons searches licensed reference metadata; official-brand searches a bounded, verified brand catalog, not arbitrary URLs. Register exact result IDs and reuse them for import; official provenance does not imply an unrestricted trademark license.
- import_asset: {"reference_id":str}. Only a previously returned search ID; safely download/normalize locally and return registered pixels, provenance and asset ID. Attribution is added automatically when used on canvas.
- process_asset: {"asset_id":str,"new_id":str}. Conservatively normalize/remove a near-uniform background from a registered asset; complex photos keep their background. Original is preserved.
- generate_icon: {"id":str,"meaning":str}. Only if image_generation is enabled: same Sol gateway and full task context, with a separately identified gpt-image-2 text-free image tool; at most two attempts. Returns raw/processed pixels and provenance. Never use for plots, exact text, formulas or actual experiment results.
- render: {"id":str,"phase":"rough"|"refined","family":str,"density":"compact"|"spacious","rationale":str,"scene":SCENE}. Save editable JSON, render current pixels, and return geometry QA. Same ID may be refined; history versions remain. Failure is returned for repair, not silently replaced by a template.
- patch_scene: {"id":str,"base_sha256":str optional,"updates":[{"id":item_id, ... fields to update}],"remove_ids":[str],"append":[SCENE_ITEM],"metadata":object optional,"scope":{"editable_ids":[str]} optional,"rationale":str}. Prefer the current scene hash returned by render. Missing, duplicate, conflicting or locked IDs fail atomically. style fields merge deeply; other unchanged fields stay intact. metadata replaces scene metadata so evidence bindings can be updated. Re-renders, invalidates review, and saves a replayable patch with before/after hashes and unchanged-item checks. A caller's revision scope cannot be widened.
- review: {"id":str}. Independent gpt-5.6-sol review using the original full evidence, current design brief, current scene, its QA, and rendered pixels. Fix supported issues before requesting another review.
- finish: {"id":str,"summary":str}. Allowed only for current-hash objective+independent-review pass, evidence pass, and required candidate exploration. Produces editable SVG, vector PDF, PNG, provenance, and ZIP. Otherwise returns actionable errors.

SCENE v1: {"version":1,"canvas":{"width":1800,"height":1100,"background":"#FFFFFF"},"metadata":{...},"items":[...]}.
Root controls final include width and minimum readable size; you cannot lower QA thresholds.
For refined scenes, metadata.claim_bindings maps each verified claim ID to the item IDs (text/formula/edge) that express it. metadata.nonfactual_ids lists only structural labels (such as panel letters), not scientific claims. Every text/formula/edge must be mapped or explicitly nonfactual; a reviewer checks the mapping against sources.
For repeated symbols, optionally declare metadata.symbol_registry={concept_id:{"kind":canonical_semantic_kind,"asset_ref":"asset:REGISTERED_ID" optional,"shape":"ellipse" optional}} and metadata.concept_bindings={item_id:concept_id}. Repeat the same asset or geometry for the same declared concept. Branch colours may differ. This checks declared consistency, not scientific truth; do not use a shared concept ID for unrelated concepts.
Every item: {"id":str,"type":"shape"|"text"|"image"|"formula"|"edge","z":number optional,...}.
Items inside a card should declare parent:shape_id. The renderer checks a real 8-unit inner margin; move/enlarge the card instead of letting a label cross its border. Parent shapes may be nested but cannot form cycles.
- shape: {"bounds":[x,y,w,h],"shape":"rect"|"ellipse"|"polygon"|"line","style":{"fill":"#F4F8FB","stroke":"#CCD8E0","stroke_width":1,"radius":18}}. Polygon additionally needs points:[[absolute_x,absolute_y],...] with >=3 vertices; this also supports hexagons/diamonds. No shape named hexagon or diamond exists. A panel does not create text automatically; author text as separate items.
- text: {"bounds":[x,y,w,h],"text":str,"font_size":number,"style":{"fill":"#193249","font_family":"DejaVu Sans","font_weight":400,"line_height":1.2,"text_anchor":"start"}}. Newlines are explicit, never automatic truncation. Source top-left bounds include full line-height. Body font >=26 units on an 1800-wide canvas; prefer 28-34, headings 38-48. Keep all text/graphics within 24 units of the page boundary.
- image: {"bounds":[x,y,w,h],"source":"asset:REGISTERED_ID","fit":"contain"}. Only asset IDs, no file paths or URLs. Assets may be reused selectively; no icon/photo quota.
- formula: {"bounds":[x,y,w,h],"latex":str,"text":str,"style":{"fill":"#193249"}}. Use math without dollar delimiters. Only mathtext-supported commands; unsupported syntax is returned for correction. Caption may refer to a sourced formula instead of pretending unsupported typesetting worked.
- edge: {"points":[[x,y],...],"source":shape_id optional,"target":shape_id optional,"arrow_end":true,"style":{"stroke":"#4078A0","stroke_width":3,"dash":[8,5] optional}}. Or use "curve":[start,control1,control2,end] for a cubic curve instead of points. Avoid crossing text or images. Do not hide arrowheads behind content. Do not use numbered badges unless the actual visual argument needs them.

Return a JSON object with summary and an actions list containing 1-12 actions per response. Each action must be an object with a non-empty tool string and an arguments object. Split larger batches across turns. Invalid batches execute no actions and are returned for correction within the same call/time budget. You may include multiple independent read/render actions in one response. Do not include finish in the same response as render/review; inspect the new result first. Keep tool payloads finite.
'''


class ResearchHarness:
    def __init__(self, *, client, sources: list[Path], brief: str, run_dir: Path,
                 assets: list[dict] | None = None, style_images: list[Path] | None = None,
                 citations: dict[str, str] | None = None, max_calls: int = 24,
                 reasoning_effort: str = "medium", require_exploration: bool = True,
                 include_width_pt: float = 486, min_font_pt: float = 7,
                 max_seconds: float = 1200, progress_callback=None,
                 allow_reference_search: bool = False, allow_image_generation: bool = False,
                 initial_scene: dict | None = None, initial_design: dict | None = None,
                 editable_ids: list[str] | None = None):
        self.run_dir = Path(run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.started = time.perf_counter()
        self.started_utc = datetime.now(timezone.utc).isoformat()
        self.context = ContextBundle(sources, citations=citations)
        self.context.save_manifest(self.run_dir / "sources.json")
        self.brief, self.require_exploration = brief, require_exploration
        self.include_width_pt, self.min_font_pt = include_width_pt, min_font_pt
        self.gateway = SolGateway(client, self.run_dir, reasoning_effort=reasoning_effort, max_calls=max_calls)
        self.asset_tools = ResearchAssets(self.gateway, self.run_dir,
            allow_reference_search=allow_reference_search, allow_image_generation=allow_image_generation)
        self.max_seconds = max_seconds
        self.progress_callback = progress_callback
        self.assets, self.images, self.candidates, self.reviews = {}, {}, {}, {}
        self.design, self.design_audit = None, None
        self.rough_variants = set()
        self.rough_scenes = {}
        self.source_page_images = {}
        self.events, self.render_count, self.done = [], 0, False
        self.patch_count = 0
        self.revision_base = None
        self.seed_scene_sha256 = None
        self.editable_ids = set(editable_ids) if editable_ids is not None else None
        if self.editable_ids is not None:
            if not initial_scene or not self.editable_ids.issubset({i["id"] for i in initial_scene["items"]}):
                raise ValueError("Editable IDs require an explicit starting scene and existing item IDs")
        (self.run_dir / "assets").mkdir()
        for record in assets or []:
            asset_id = safe_id(record["id"])
            if asset_id in self.assets:
                raise ValueError("Duplicate registered asset ID")
            staged = self._stage_asset_files(record, caller_supplied=True)
            self.assets[asset_id] = staged
            self.images[asset_id] = staged["preview_path"]
        if initial_scene is not None:
            initial_scene = self._normalize_seed_scene(initial_scene)
            # Scoped locking is defined against the normalized portable seed:
            # packaged assets/<id>.<ext> references become registered asset IDs.
            self.revision_base = deepcopy(initial_scene)
            self.seed_scene_sha256 = hash_scene(initial_scene)
        asset_metadata = [_without_response_ids({k: v for k, v in a.items() if k not in {"path", "raw_path", "preview_path"}}) for a in self.assets.values()]
        guidance = "\n\n".join((REFERENCE_ROOT / name).read_text(encoding="utf-8")
                               for name in ["workflow.md", "style-system.md", "layouts-and-shapes.md", "assets-and-prompts.md", "qa.md"])
        self.instructions = (ROOT / "prompts" / "research_harness.md").read_text(encoding="utf-8") + "\n\n" + TOOLS
        initial = [{"type": "input_text", "text": json.dumps({"user_request": brief,
                   "source_manifest": self.context.manifest(), "registered_assets": asset_metadata,
                   "target_include_width_pt": include_width_pt, "minimum_body_font_pt": min_font_pt,
                   "capabilities": {"reference_search": allow_reference_search, "image_generation": allow_image_generation},
                   "require_six_rough_candidates": require_exploration}, ensure_ascii=False)},
                   {"type": "input_text", "text": "PUBLIC TASK-SPECIFIC DESIGN GUIDANCE\n" + guidance},
                   {"type": "input_text", "text": "COMPLETE SOURCE DATA\n" + self.context.full_text()}]
        for p in style_images or []:
            initial.extend([{"type": "input_text", "text": f"Style reference only: {Path(p).name}; not factual evidence for this paper."}, image_input(Path(p))])
        for asset_id, asset in list(self.assets.items())[:8]:
            initial.extend([{"type": "input_text", "text": f"Registered asset {asset_id}: {asset.get('meaning', asset.get('kind', 'illustration'))}. Inspect its silhouette before assigning space."}, image_input(asset["preview_path"])])
        self.initial_content = initial
        from .scene import font_environment
        initial.append({"type": "input_text", "text": "RENDERER FONT ENVIRONMENT: " +
            json.dumps(font_environment()) + ". Use the recommended actual font family explicitly, not an unavailable font name."})
        self.history = [{"role": "user", "content": initial}]
        write_json(self.run_dir / "context_manifest.json", {"source_characters": self.context.characters,
                   "sources": self.context.manifest(), "assets": asset_metadata,
                   "style_references": [{"name": Path(p).name, "sha256": digest(Path(p))} for p in style_images or []],
                   "instructions_sha256": hashlib.sha256(self.instructions.encode()).hexdigest(),
                   "revision": {"seed_scene_sha256": self.seed_scene_sha256,
                                "editable_ids": editable_ids},
                   "implementation_hashes": {name: digest(Path(__file__).parent / name) for name in
                       ["research_harness.py", "context_bundle.py", "scene.py", "math_svg.py", "model_policy.py",
                        "scene_patch.py", "svg_assets.py", "research_assets.py", "official_assets.py"]},
                   "full_source_preserved_every_request": True, "history_mode": "explicit output-item replay",
                   "reasoning_effort": reasoning_effort, "model": "gpt-5.6-sol",
                   "capabilities": {"reference_search": allow_reference_search, "image_generation": allow_image_generation},
                   "scope": "explicit evidence, safe scene operations and separately granted asset capabilities; no publishing or arbitrary shell"})
        if initial_design is not None:
            result, _ = self.execute({"tool": "record_design", "arguments": {"design": initial_design}})
            initial.append({"type": "input_text", "text": "Supplied starting design, rechecked against current sources: " +
                json.dumps({"design": initial_design, "audit": result}, ensure_ascii=False)})
        if initial_scene is not None:
            result, images = self.execute({"tool": "render", "arguments": {
                "id": "starting_scene", "phase": "refined", "family": "existing", "scene": initial_scene}})
            initial.extend([{"type": "input_text", "text": "EXPLICIT STARTING SCENE FOR REVISION\n" + json.dumps({
                "scene": initial_scene, "result": result, "editable_item_ids": editable_ids,
                "constraint": "Preserve every other item, item order, and canvas. Only listed items may change; metadata can be corrected." if editable_ids is not None else "Preserve the supplied visual design except where the user requests revision."}, ensure_ascii=False)}])
            initial.extend(image_input(p) for p in images)

    def _stage_asset_files(self, record, *, caller_supplied=False):
        """Preserve source vectors while registering only raster model previews."""
        asset_id = safe_id(record["id"])
        source = Path(record["path"]).resolve(strict=True)
        if not caller_supplied and self.run_dir not in source.parents:
            raise ValueError("Asset tool result must be inside this run")
        if not source.is_file() or source.stat().st_size > 25_000_000:
            raise ValueError("Registered source asset must be a bounded regular file")
        suffix = source.suffix.lower()
        if suffix == ".svg":
            from .svg_assets import safe_svg_bytes, raster_preview
            safe_svg_bytes(source, prefix="asset-" + asset_id)
            preview_bytes = raster_preview(source, max_side=1024)
            local = self.run_dir / "assets" / (asset_id + ".svg")
            preview = self.run_dir / "asset_previews" / (asset_id + ".png")
            preview.parent.mkdir(exist_ok=True)
            # Generate from the actual SVG even if a provider supplies a preview:
            # source and model-visible pixels must not silently diverge.
            preview.write_bytes(preview_bytes)
            image_input(preview)
        else:
            image_input(source)
            local = self.run_dir / "assets" / (asset_id + suffix)
            preview = local
        if source != local:
            shutil.copyfile(source, local)
        return {**record, "path": local, "preview_path": preview,
                "sha256": digest(local), "preview_sha256": digest(preview),
                "media_kind": "svg-vector" if suffix == ".svg" else "raster"}

    def _normalize_seed_scene(self, raw):
        """Map portable package asset names through the explicit asset manifest only."""
        scene = deepcopy(raw)
        registered = {
            f"assets/{asset_id}{Path(record['path']).suffix.lower()}": asset_id
            for asset_id, record in self.assets.items()
        }
        for item in scene.get("items", []):
            if item.get("type") != "image":
                continue
            source = item.get("source")
            if isinstance(source, str) and source.startswith("asset:"):
                if source[6:] not in self.assets:
                    raise ValueError("Seed scene references an asset absent from the explicit manifest")
                continue
            if source not in registered:
                raise ValueError("Portable seed images must match assets explicitly supplied in the manifest")
            item["source"] = "asset:" + registered[source]
        registry = scene.get("metadata", {}).get("symbol_registry", {})
        if isinstance(registry, dict):
            for symbol in registry.values():
                if isinstance(symbol, dict) and symbol.get("asset_ref") in registered:
                    symbol["asset_ref"] = "asset:" + registered[symbol["asset_ref"]]
        return scene

    def _record(self, tool, start, result):
        self.events.append({"tool": tool, "start_s": start-self.started,
                            "end_s": time.perf_counter()-self.started,
                            "status": "error" if result.get("error") else "completed", "result": result})
        write_json(self.run_dir / "events.json", self.events)
        if self.progress_callback:
            self.progress_callback(self.events[-1])

    def _prepare_scene(self, raw):
        if self.revision_base is not None and self.editable_ids is not None:
            base = self.revision_base
            if raw["canvas"] != base["canvas"] or [i["id"] for i in raw["items"]] != [i["id"] for i in base["items"]]:
                raise ValueError("Revision scope locks the canvas, item IDs and item order")
            for before, after in zip(base["items"], raw["items"]):
                if before["id"] not in self.editable_ids and before != after:
                    raise ValueError(f"Revision attempted to change locked item: {before['id']}")
        scene = deepcopy(raw)
        canvas = scene["canvas"]
        width, height = canvas["width"], canvas["height"]
        if not 600 <= width <= 3000 or not 400 <= height <= 2200 or len(scene.get("items", [])) > 280:
            raise ValueError("Use a bounded, readable figure: width 600-3000, height 400-2200, <=280 items")
        canvas["include_width_pt"] = self.include_width_pt
        scene["qa"] = {"margin": 24, "min_font_pt": self.min_font_pt}
        used_assets = set()
        for item in scene["items"]:
            if item["type"] == "image":
                source = item["source"]
                if not source.startswith("asset:") or source[6:] not in self.assets:
                    raise ValueError("Image must use a registered asset ID")
                if _official_brand(self.assets[source[6:]]) and item.get("fit", "contain") != "contain":
                    raise ValueError("Official brand artwork requires contain fit; stretching or cropping its wordmark is not permitted")
                item["source"] = str(self.assets[source[6:]]["path"])
                used_assets.add(source[6:])
                # Actual pixel occupancy is derived by the renderer, not supplied by a model.
                item.pop("asset_bounds", None)
        self._add_attribution(scene, used_assets)
        return scene

    def _add_attribution(self, scene, used_assets):
        from .scene import font_environment, measure_text
        credits = []
        for asset_id in sorted(used_assets):
            provenance = self.assets[asset_id].get("provenance", {})
            if provenance.get("provider") == "wikimedia-commons":
                credits.append(" · ".join(str(provenance.get(key) or "") for key in
                    ["title", "author", "license_name"]) + " · Wikimedia Commons · scaled/cropped")
        if not credits:
            return
        width, old_height = scene["canvas"]["width"], scene["canvas"]["height"]
        font = font_environment()["recommended_family"]
        size = max(26, self.min_font_pt * width / self.include_width_pt)
        lines = []
        for credit in credits:
            line = ""
            for char in credit:
                if measure_text(line + char, size, font)[0] > width - 64 and line:
                    lines.append(line)
                    line = char
                else:
                    line += char
            if line:
                lines.append(line)
        height = len(lines) * size * 1.25
        existing = [item for item in scene["items"] if item.get("id") == "ff_credit_footer"]
        if existing:
            if len(existing) != 1 or existing[0].get("type") != "text" or existing[0].get("text") != "\n".join(lines):
                raise ValueError("Existing Commons attribution footer does not match registered provenance")
            return
        scene["canvas"]["height"] = old_height + height + 56
        scene["items"].append({"id": "ff_credit_footer", "type": "text",
            "bounds": [32, old_height + 16, width - 64, height], "text": "\n".join(lines),
            "font_size": size, "style": {"font_family": font, "fill": "#526371", "line_height": 1.25}})

    def _register_asset(self, record):
        asset_id = safe_id(record["id"])
        if asset_id in self.assets:
            raise ValueError("Asset ID already exists; use a new ID to preserve the original")
        staged = self._stage_asset_files(record)
        self.assets[asset_id] = staged
        preview = staged["preview_path"]
        self.images[asset_id] = preview
        metadata = _without_response_ids({k: v for k, v in staged.items() if k not in {"path", "raw_path", "preview_path"}})
        self.initial_content.extend([{"type": "input_text", "text": "New registered asset: " + json.dumps(metadata)}, image_input(preview)])
        self.reviews.clear()
        images = [preview]
        if record.get("raw_path"):
            raw = Path(record["raw_path"]).resolve(strict=True)
            if self.run_dir not in raw.parents:
                raise ValueError("Raw asset must remain inside this run")
            if raw.suffix.lower() == ".svg":
                from .svg_assets import raster_preview
                raw_preview = self.run_dir / "asset_previews" / (asset_id + "-raw.png")
                raw_preview.parent.mkdir(exist_ok=True)
                raw_preview.write_bytes(raster_preview(raw, max_side=1024))
            else:
                raw_preview = raw
            image_input(raw_preview)
            self.images[asset_id + "-raw"] = raw_preview
            images.insert(0, raw_preview)
        return metadata, images

    def _render(self, args):
        from .scene import render_scene
        candidate_id = safe_id(args["id"])
        phase = args.get("phase", "refined")
        if phase not in {"rough", "refined"}:
            raise ValueError("phase must be rough or refined")
        if args.get("density", "spacious") not in {"compact", "spacious"}:
            raise ValueError("density must be compact or spacious")
        family = args.get("family", "custom").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", family):
            raise ValueError("Use a stable short layout family name")
        raw_scene = deepcopy(args["scene"])
        scene = self._prepare_scene(raw_scene)
        self.render_count += 1
        stem = self.run_dir / "renders" / f"{self.render_count:03d}-{candidate_id}"
        write_json(stem.with_suffix(".scene.json"), raw_scene)
        output = render_scene(scene, stem, formats=("svg", "png"), base_dir=self.run_dir / "assets")
        scene_hash = hash_scene(raw_scene)
        consistency = validate_symbol_consistency(raw_scene)
        if not consistency["pass"]:
            issues = [{"severity": "error", "code": "symbol_consistency", **issue}
                      for issue in consistency["errors"]]
            output["qa"]["issues"].extend(issues)
            output["qa"]["ok"] = output["qa"]["renderable"] = False
            output["qa"]["counts"]["error"] += len(issues)
        output["qa"]["symbol_consistency"] = consistency
        record = {"id": candidate_id, "phase": phase, "family": family,
                  "density": args.get("density", "spacious"), "rationale": args.get("rationale", ""),
                  "scene": raw_scene, "scene_hash": scene_hash, "output": output, "stem": str(stem),
                  "patch_history": []}
        self.candidates[candidate_id] = record
        self.reviews.pop(candidate_id, None)
        self.images[candidate_id] = stem.with_suffix(".png")
        if phase == "rough":
            geometry = {"canvas": {k: raw_scene["canvas"][k] for k in ["width", "height"]},
                        "items": [{k: v for k, v in item.items() if k in
                            {"type", "bounds", "points", "curve", "shape", "font_size"}} for item in raw_scene["items"]]}
            geometry_hash = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()
            if geometry_hash not in self.rough_scenes:
                self.rough_scenes[geometry_hash] = {k: record[k] for k in ["id", "family", "density", "scene_hash", "rationale", "stem"]}
                self.rough_variants.add((record["family"], record["density"]))
            write_json(self.run_dir / "exploration.json", list(self.rough_scenes.values()))
        write_json(stem.with_suffix(".qa.json"), output["qa"])
        return {"id": candidate_id, "scene_hash": scene_hash, "qa": output["qa"],
                "evidence_bindings": self._binding_audit(raw_scene) if phase == "refined" else None,
                "rough_variants": sorted(self.rough_variants), "image_id": candidate_id}, [self.images[candidate_id]]

    def _independent_review(self, args):
        candidate = self.candidates[args["id"]]
        binding_audit = self._binding_audit(candidate["scene"])
        if not binding_audit["pass"]:
            raise ValueError("Repair evidence bindings before paid review: " + json.dumps(binding_audit))
        payload = {"task": "Independently review this CURRENT rendered figure against the full paper and original user request. Return JSON {pass:bool, issues:[{severity:'error'|'warning', description:str, fix:str}], strengths:[str]}. Judge actual reading order, scientific relations, visual hierarchy, text and formula fidelity, asset relevance and final paper-width legibility. A schematic can omit secondary details if the stated takeaway is faithful. Do not invent formula numbering assumptions: use explicit source citations. Reject real overlaps and unreadable arrows, but do not confuse crossing bounding boxes with pixel collisions. Do not claim author approval.",
                   "design": self.design, "design_audit": self.design_audit, "scene": candidate["scene"],
                   "geometry_qa": candidate["output"]["qa"], "scene_hash": candidate["scene_hash"],
                   "evidence_bindings": self._binding_audit(candidate["scene"]),
                   "exploration": list(self.rough_scenes.values())}
        review_instructions = ("You are an independent research-figure reviewer. Check the current pixels and source evidence, not prior assistant claims. "
            "Return only JSON with pass (boolean), issues (objects containing severity, description, fix), and strengths (strings). "
            "Do not emit workflow actions. Distinguish verified visual or scientific errors from subjective preferences and uncertain interpretation. "
            "Passing requires readable, scientifically faithful, publication-appropriate composition. Do not claim author approval.")
        page_context = []
        for image_id, path in self.source_page_images.items():
            page_context.extend([{"type": "input_text", "text": f"Previously inspected source page {image_id}"}, image_input(path)])
        response = self.gateway.create(stage="independent_review", instructions=review_instructions,
                   input=[{"role": "user", "content": self.initial_content + page_context + [
                       {"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)},
                       image_input(self.images[args["id"]])]}], text={"format": {"type": "json_object"}})
        review = parse_response(response)
        if not isinstance(review, dict) or type(review.get("pass")) is not bool or not isinstance(review.get("issues"), list):
            raise ValueError("Reviewer returned an invalid review schema")
        if any(not isinstance(issue, dict) or issue.get("severity") not in {"error", "warning"}
               or not issue.get("description") or not issue.get("fix") for issue in review["issues"]):
            raise ValueError("Review issues require severity, description and fix")
        if any(issue["severity"] == "error" for issue in review["issues"]):
            review["pass"] = False
        review["scene_hash"] = candidate["scene_hash"]
        self.reviews[args["id"]] = review
        write_json(Path(candidate["stem"]).with_suffix(".review.json"), review)
        return review, []

    def _binding_audit(self, scene):
        claims = {claim["id"] for claim in (self.design or {}).get("claims", [])}
        items = {item["id"]: item for item in scene["items"]}
        metadata = scene.get("metadata", {})
        bindings = metadata.get("claim_bindings", {})
        nonfactual = metadata.get("nonfactual_ids", [])
        if not isinstance(bindings, dict) or not isinstance(nonfactual, list):
            return {"pass": False, "errors": ["Invalid claim_bindings/nonfactual_ids"]}
        errors, covered = [], set()
        for claim, ids in bindings.items():
            if claim not in claims or not isinstance(ids, list) or not ids:
                errors.append(f"Unknown claim or empty item list: {claim}")
                continue
            for item_id in ids:
                if item_id not in items:
                    errors.append(f"Unknown bound item: {item_id}")
                else:
                    covered.add(item_id)
        for item_id in nonfactual:
            if item_id not in items or items[item_id]["type"] != "text":
                errors.append(f"Only existing structural text may be nonfactual: {item_id}")
            else:
                covered.add(item_id)
        missing = [item_id for item_id, item in items.items()
                   if item["type"] in {"text", "formula", "edge"} and item_id not in covered]
        return {"pass": not errors and not missing, "errors": errors, "unmapped_items": missing,
                "note": "Binding completeness only; the automated reviewer checks whether sources support these mappings."}

    def _verify_patch_history(self, candidate):
        """Replay saved patch data before packaging; reject stale/tampered files."""
        previous_hash = None
        patch_root = (self.run_dir / "patches").resolve()
        for entry in candidate.get("patch_history", []):
            data = {}
            for key in ("base_file", "patch_file", "receipt_file"):
                local = (self.run_dir / entry[key]).resolve(strict=True)
                if patch_root not in local.parents:
                    raise ValueError("Replay file escaped the run's patch directory")
                data[key] = json.loads(local.read_text(encoding="utf-8"))
            base = data["base_file"]
            patch_data = data["patch_file"]
            recorded = data["receipt_file"]
            if previous_hash is not None and hash_scene(base) != previous_hash:
                raise ValueError("Replay patches do not form a contiguous scene chain")
            _, computed = apply_scene_patch(base, patch_data)
            for key in ("base_sha256", "patch_sha256", "result_sha256"):
                if computed[key] != entry[key] or computed[key] != recorded[key]:
                    raise ValueError("Replay file hash did not match its receipt")
            for key in ("changed_ids", "added_ids", "removed_ids", "unchanged_item_sha256", "canvas_unchanged"):
                if recorded[key] != computed[key]:
                    raise ValueError("Replay unchanged-item or operation receipt was modified")
            previous_hash = computed["result_sha256"]
        if previous_hash is not None and previous_hash != hash_scene(candidate["scene"]):
            raise ValueError("Replay patch chain does not match the current scene")
        return {"pass": True, "patch_count": len(candidate.get("patch_history", []))}

    def _finish(self, args):
        from .scene import render_scene
        candidate = self.candidates[args["id"]]
        review = self.reviews.get(args["id"], {})
        unmet = []
        if not self.design_audit or not self.design_audit["pass"]:
            unmet.append("Evidence brief missing or exact source claims unverified")
        if not candidate["output"]["qa"]["ok"]:
            unmet.append("Objective geometry QA has unresolved errors")
        if any(s.path.suffix.lower() == ".pdf" for s in self.context.sources) and not self.source_page_images:
            unmet.append("Inspect the relevant source PDF page pixels before delivery, particularly equations and method figures")
        binding_audit = self._binding_audit(candidate["scene"])
        if not binding_audit["pass"]:
            unmet.append({"evidence_binding_incomplete": binding_audit})
        consistency = validate_symbol_consistency(candidate["scene"])
        if not consistency["pass"]:
            unmet.append({"symbol_consistency_failed": consistency})
        patch_history = candidate.get("patch_history", [])
        try:
            replay_audit = self._verify_patch_history(candidate)
        except (OSError, KeyError, TypeError, ValueError):
            replay_audit = {"pass": False, "patch_count": len(patch_history)}
            unmet.append("Saved replay patch files or their integrity receipts failed verification")
        if review.get("pass") is not True or review.get("scene_hash") != candidate["scene_hash"]:
            unmet.append("Independent review of this exact scene has not passed")
        if self.require_exploration and (len(self.rough_scenes) < 6 or len(self.rough_variants) < 6 or len({x[0] for x in self.rough_variants}) < 3
                                       or len({x[1] for x in self.rough_variants}) < 2):
            unmet.append("Need six rough variants spanning three families and two density levels")
        if not self.gateway.records or any(r.get("status") != "completed" or r.get("identity_status") not in
                {"reported_match", "reported_snapshot"} for r in self.gateway.records):
            unmet.append("Every model call must report a consistent Sol identity before delivery")
        if unmet:
            return {"error": "not_ready", "unmet": unmet}, []
        final = render_scene(self._prepare_scene(candidate["scene"]), self.run_dir / "final", formats=("svg", "png", "pdf"), base_dir=self.run_dir / "assets")
        pdf_audit = subprocess.run([sys.executable, str(REFERENCE_ROOT.parent / "scripts" / "qa_pdf.py"),
            str(self.run_dir / "final.pdf"), "--single-page", "--json"], capture_output=True, text=True, timeout=90)
        pdf_qa = json.loads(pdf_audit.stdout)
        write_json(self.run_dir / "pdf_qa.json", pdf_qa)
        if not final["qa"]["ok"] or not pdf_qa.get("ok") or pdf_qa.get("summary", {}).get("warnings"):
            return {"error": "final_export_qa_failed", "geometry": final["qa"], "pdf": pdf_qa}, []
        portable_scene = self._prepare_scene(candidate["scene"])
        for item in portable_scene["items"]:
            if item["type"] == "image":
                item["source"] = "assets/" + Path(item["source"]).name
        registry = portable_scene.get("metadata", {}).get("symbol_registry", {})
        if isinstance(registry, dict):
            for symbol in registry.values():
                reference = symbol.get("asset_ref") if isinstance(symbol, dict) else None
                if isinstance(reference, str) and reference.startswith("asset:") and reference[6:] in self.assets:
                    symbol["asset_ref"] = "assets/" + self.assets[reference[6:]]["path"].name
        write_json(self.run_dir / "final.scene.json", portable_scene)
        model_audit = _without_response_ids(self.gateway.records)
        write_json(self.run_dir / "model_audit.json", model_audit)
        manifest = {"status": "automated_review_passed", "human_approval": "pending", "candidate_id": args["id"],
                    "scene_hash": candidate["scene_hash"], "source_manifest": self.context.manifest(),
                    "design": self.design, "geometry_qa": final["qa"], "independent_review": review,
                    "evidence_bindings": binding_audit, "pdf_qa": pdf_qa,
                    "requested_model": "gpt-5.6-sol", "reported_model": self.gateway.pinned_reported_model,
                    "model_identity_scope": "consistent service-reported identity; not independent verification of served weights",
                    "call_count": len(self.gateway.records), "summary": args.get("summary", ""),
                    "run_mode": "continuation" if self.revision_base is not None else "fresh",
                    "revision": {"seed_scene_sha256": self.seed_scene_sha256,
                                 "editable_ids": sorted(self.editable_ids) if self.editable_ids is not None else None},
                    "time_scope": "this run's supplied-source reading through review/repair and ZIP close",
                    "time_exclusions": ["prior run and seed creation", "environment development",
                                        "later human acceptance"] if self.revision_base is not None else
                                       ["environment development", "later human acceptance"],
                    "exported_scene_sha256": digest(self.run_dir / "final.scene.json"),
                    "symbol_consistency": consistency, "patch_history": patch_history, "replay_audit": replay_audit,
                    "replay_scope": "Patch files reproduce the declared scene data, not a new model run or semantic approval.",
                    "asset_files": {asset_id: {"source": "assets/" + Path(a["path"]).name,
                        **({"preview": "asset_previews/" + Path(a["preview_path"]).name}
                           if a.get("media_kind") == "svg-vector" else {})}
                        for asset_id, a in self.assets.items()},
                    "assets": [{k: v for k, v in a.items() if k not in {"path", "raw_path", "preview_path"}} for a in self.assets.values()]}
        manifest = _without_response_ids(manifest)
        write_json(self.run_dir / "manifest.json", manifest)
        with zipfile.ZipFile(self.run_dir / "delivery.zip", "w", zipfile.ZIP_DEFLATED) as package:
            for name in ["final.svg", "final.png", "final.pdf", "final.scene.json", "manifest.json",
                         "sources.json", "model_audit.json", "pdf_qa.json"]:
                package.write(self.run_dir / name, name)
            package.writestr("design.json", json.dumps(_without_response_ids(self.design), ensure_ascii=False, indent=2))
            for asset in self.assets.values():
                package.write(asset["path"], "assets/" + asset["path"].name)
                if asset.get("media_kind") == "svg-vector":
                    package.write(asset["preview_path"], "asset_previews/" + Path(asset["preview_path"]).name)
                if asset.get("raw_path"):
                    package.write(asset["raw_path"], "asset_sources/" + asset["id"] + Path(asset["raw_path"]).suffix.lower())
            for entry in patch_history:
                for key in ("base_file", "patch_file", "receipt_file"):
                    package.write(self.run_dir / entry[key], entry[key])
        self.done = True
        return {"status": "automated_review_passed", "elapsed_seconds": time.perf_counter()-self.started,
                "human_approval": "pending", "candidate_id": args["id"]}, []

    def execute(self, action):
        tool = "invalid_action"
        start = time.perf_counter()
        images = []
        try:
            tool, args = validate_action(action)
            if tool == "record_design":
                design = args["design"]
                claims = design.get("claims", [])
                if not claims or not design.get("takeaway"):
                    raise ValueError("Design requires one takeaway and supported claims")
                if not all(design.get(key) for key in ["reading_order", "essential_relations", "caption"]):
                    raise ValueError("Design requires reading_order, essential_relations and caption")
                if len({c["id"] for c in claims}) != len(claims):
                    raise ValueError("Claim IDs must be unique")
                matches = [{"id": c["id"], "pass": self.context.verify_quote(c["source_id"], c["page"], c["quote"])} for c in claims]
                self.design, self.design_audit = design, {"pass": all(c["pass"] for c in matches), "claims": matches}
                self.reviews.clear()
                write_json(self.run_dir / "design.json", design)
                result = self.design_audit
            elif tool == "search_assets":
                result = {"candidates": self.asset_tools.search(**args)}
            elif tool == "import_asset":
                if args["reference_id"] in self.assets:
                    raise ValueError("Reference is already registered; reuse its asset ID")
                result, images = self._register_asset(self.asset_tools.import_reference(args["reference_id"]))
            elif tool == "process_asset":
                new_id = safe_id(args["new_id"])
                if new_id in self.assets:
                    raise ValueError("Use a new processed asset ID")
                previous = self.assets[args["asset_id"]]
                if _official_brand(previous):
                    raise ValueError("Official brand artwork cannot use generic background removal; reuse the verified original or import its declared catalog crop/conversion")
                if Path(previous["path"]).suffix.lower() == ".svg":
                    raise ValueError("A registered SVG is already a vector asset; reuse it or import a new verified original, not a raster matte")
                record = self.asset_tools.process_existing(previous["path"], id=new_id, meaning=previous.get("meaning", ""))
                record["kind"] = previous.get("kind", record["kind"])
                record["provenance"] = {**previous.get("provenance", {}), "local_processing": record["provenance"]}
                result, images = self._register_asset(record)
            elif tool == "generate_icon":
                asset_id = safe_id(args["id"])
                if asset_id in self.assets:
                    raise ValueError("Use a new generated asset ID")
                full_context = self.initial_content + [{"type": "input_text", "text": json.dumps({
                    "current_design": self.design,
                    "current_scenes": [c["scene"] for c in self.candidates.values() if c["phase"] == "refined"]}, ensure_ascii=False)}]
                for image_id, page_path in self.source_page_images.items():
                    full_context.extend([{"type": "input_text", "text": f"Inspected source page {image_id}"}, image_input(page_path)])
                refined = [c for c in self.candidates.values() if c["phase"] == "refined"]
                if refined:
                    full_context.extend([{"type": "input_text", "text": "Current layout to match; generate only the requested component."},
                                         image_input(self.images[refined[-1]["id"]])])
                record = self.asset_tools.generate_icon(asset_id, args["meaning"], full_context)
                result, images = self._register_asset(record)
            elif tool == "search_source":
                result = {"matches": self.context.search(args["query"])}
            elif tool == "read_page":
                sid, page = args["source_id"], args["page"]
                p = self.context.page(sid, page, self.run_dir / "source_pages" / f"{safe_id(sid)}-{page}.png")
                self.images[f"{sid}-page-{page}"] = p
                self.source_page_images[f"{sid}-page-{page}"] = p
                self.reviews.clear()
                result, images = {"source_id": sid, "page": page, "image_id": f"{sid}-page-{page}"}, [p]
            elif tool == "inspect_image":
                from PIL import Image
                p = self.images[args["image_id"]]
                if "crop" in args:
                    box = args["crop"]
                    with Image.open(p) as im:
                        if len(box) != 4 or not 0 <= box[0] < box[2] <= im.width or not 0 <= box[1] < box[3] <= im.height:
                            raise ValueError("Crop must be within image pixels")
                        target = self.run_dir / "crops" / f"crop-{len(self.events)}.png"
                        target.parent.mkdir(exist_ok=True)
                        im.crop(tuple(box)).save(target)
                    p = target
                result, images = {"image_id": args["image_id"], "crop": args.get("crop")}, [p]
            elif tool == "measure_text":
                from .scene import measure_text, _font_info
                width, height = measure_text(**args)
                _, resolved, substituted = _font_info(args.get("font_family", "Arial"), args.get("font_weight", 400))
                result = {"width": width, "height": height, "units": "scene coordinates",
                          "resolved_font_family": resolved, "font_substituted": substituted}
            elif tool == "render":
                result, images = self._render(args)
            elif tool == "patch_scene":
                record = self.candidates[args["id"]]
                patch_data = {key: deepcopy(val) for key, val in args.items() if key != "id"}
                patch_data.setdefault("version", 1)
                patch_data.setdefault("base_sha256", hash_scene(record["scene"]))
                if self.editable_ids is not None:
                    scope = patch_data.setdefault("scope", {})
                    if not isinstance(scope, dict):
                        raise ValueError("Invalid patch scope")
                    requested_ids = scope.get("editable_ids", sorted(self.editable_ids))
                    if not isinstance(requested_ids, list) or not all(isinstance(i, str) for i in requested_ids) or not set(requested_ids).issubset(self.editable_ids):
                        raise ValueError("Patch cannot widen the caller's editable IDs")
                    if scope.get("allow_append") or scope.get("allow_remove"):
                        raise ValueError("Caller-scoped revisions lock item IDs and ordering")
                    scope.update({"editable_ids": requested_ids, "allow_append": False, "allow_remove": False})
                scene, receipt = apply_scene_patch(record["scene"], patch_data)
                result, images = self._render({**record, "scene": scene, "phase": "refined", "rationale": args.get("rationale", "local revision")})
                self.patch_count += 1
                patch_stem = f"patches/{self.patch_count:03d}-{safe_id(args['id'])}"
                files = {"base_file": patch_stem + ".base.scene.json", "patch_file": patch_stem + ".patch.json",
                         "receipt_file": patch_stem + ".receipt.json"}
                receipt["post_render_qa"] = result["qa"]
                receipt["qa_status"] = "objective_checks_passed_review_required" if result["qa"]["ok"] else "draft_only_post_render_qa_failed"
                write_json(self.run_dir / files["base_file"], record["scene"])
                write_json(self.run_dir / files["patch_file"], patch_data)
                write_json(self.run_dir / files["receipt_file"], receipt)
                entry = {**files, "base_sha256": receipt["base_sha256"], "result_sha256": receipt["result_sha256"],
                         "patch_sha256": receipt["patch_sha256"], "changed_ids": receipt["changed_ids"],
                         "qa_status": receipt["qa_status"]}
                self.candidates[args["id"]]["patch_history"] = record.get("patch_history", []) + [entry]
                result["patch_receipt"] = receipt
            elif tool == "review":
                result, images = self._independent_review(args)
            elif tool == "finish":
                result, images = self._finish(args)
            else:
                raise ValueError("Unknown tool; no arbitrary shell or file access")
        except (KeyError, ValueError, TypeError, ResearchAssetError) as exc:
            result = {"error": type(exc).__name__, "detail": str(exc)[:800]}
        self._record(tool, start, result)
        return {"tool": tool, "result": result}, images

    def run(self):
        terminal = None
        try:
            while not self.done and time.perf_counter()-self.started < self.max_seconds:
                turn = len([e for e in self.events if e["tool"] == "agent_turn"])+1
                call_start = time.perf_counter()
                response = self.gateway.create(stage=f"agent_turn_{turn}", instructions=self.instructions,
                            input=self.history, text={"format": {"type": "json_object"}})
                self._record("agent_turn", call_start, {})
                output_items = value(response, "output", [])
                self.history.extend([item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else item for item in output_items])
                validation_start = time.perf_counter()
                try:
                    answer = parse_response(response)
                    write_json(self.run_dir / "turns" / f"{turn:03d}.json", answer)
                    actions = validate_action_batch(answer)
                except (ValueError, TypeError) as exc:
                    feedback = {"error": "invalid_action_batch", "detail": str(exc)[:800],
                                "recoverable": True, "executed_actions": 0,
                                "minimum_actions": 1, "maximum_actions": 12,
                                "instruction": "Return a corrected JSON object with 1-12 valid actions; split larger batches. No actions from this batch were executed. The original call/time budget remains unchanged."}
                    self._record("action_batch_validation", validation_start, feedback)
                    self.history.append({"role": "user", "content": [{"type": "input_text", "text": json.dumps(feedback)}]})
                    continue
                print(json.dumps({"turn": turn, "summary": answer.get("summary", ""), "elapsed_s": round(time.perf_counter()-self.started, 1)}, ensure_ascii=False), flush=True)
                content = []
                for action in actions:
                    if action.get("tool") == "finish" and len(actions) != 1:
                        content.append({"type": "input_text", "text": json.dumps({"error": "finish_must_follow_inspection_in_a_separate_turn"})})
                        continue
                    result, images = self.execute(action)
                    content.append({"type": "input_text", "text": json.dumps(result, ensure_ascii=False)})
                    content.extend(image_input(p) for p in images)
                    if self.done:
                        terminal = result["result"]
                        break
                self.history.append({"role": "user", "content": content})
        except Exception as exc:
            terminal = {"status": "draft_only", "stop_reason": type(exc).__name__, "human_approval": "not reached"}
        if terminal is None:
            terminal = {"status": "draft_only", "stop_reason": "time_budget", "human_approval": "not reached"}
        terminal.update({"elapsed_seconds": time.perf_counter()-self.started, "started_utc": self.started_utc,
                         "calls": len(self.gateway.records), "render_count": self.render_count,
                         "candidate_ids": list(self.candidates), "rough_variants": sorted(self.rough_variants),
                         "complete_source_characters": self.context.characters})
        write_json(self.run_dir / "result.json", terminal)
        return terminal


def main():
    from openai import OpenAI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--style-image", type=Path, action="append", default=[])
    parser.add_argument("--max-calls", type=int, default=24)
    parser.add_argument("--max-seconds", type=float, default=1200)
    parser.add_argument("--reasoning-effort", choices=["medium", "high", "xhigh"], default="medium")
    parser.add_argument("--narrow-revision", action="store_true")
    parser.add_argument("--allow-reference-search", action="store_true")
    parser.add_argument("--allow-image-generation", action="store_true")
    parser.add_argument("--initial-scene", type=Path)
    parser.add_argument("--initial-design", type=Path)
    parser.add_argument("--editable-id", action="append")
    args = parser.parse_args()
    assets = json.loads(args.asset_manifest.read_text()) if args.asset_manifest else []
    harness = ResearchHarness(client=OpenAI(timeout=300, max_retries=0), sources=args.source, brief=args.brief,
              run_dir=args.output, assets=assets, style_images=args.style_image, max_calls=args.max_calls,
              max_seconds=args.max_seconds, reasoning_effort=args.reasoning_effort,
              require_exploration=not args.narrow_revision,
              allow_reference_search=args.allow_reference_search, allow_image_generation=args.allow_image_generation,
              initial_scene=json.loads(args.initial_scene.read_text()) if args.initial_scene else None,
              initial_design=json.loads(args.initial_design.read_text()) if args.initial_design else None,
              editable_ids=args.editable_id)
    print(json.dumps(harness.run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
