"""Atomic, replayable edits and declared symbol-consistency checks for scenes.

These checks establish structural integrity and consistency with the author's
registry, not the truth of a scientific claim or the quality of a drawing.
No files, network resources, model calls, or executable code are accessed.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re


class ScenePatchError(ValueError):
    """A patch failed before its input scene was changed."""


def _json_bytes(value) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ScenePatchError("Scene and patch must contain finite JSON data") from exc


def hash_scene(scene: dict) -> str:
    """Canonical SHA-256, independent of dictionary insertion order."""
    return hashlib.sha256(_json_bytes(scene)).hexdigest()


def _item_map(scene: dict) -> dict:
    if not isinstance(scene, dict) or not isinstance(scene.get("canvas"), dict):
        raise ScenePatchError("A scene requires a canvas object")
    items = scene.get("items")
    if not isinstance(items, list):
        raise ScenePatchError("A scene requires an items array")
    result = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ScenePatchError("Every item requires a string ID")
        item_id = item["id"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,99}", item_id):
            raise ScenePatchError("Invalid scene item ID")
        if item_id in result:
            raise ScenePatchError("Duplicate scene item ID")
        if not isinstance(item.get("type"), str) or item["type"] not in {"shape", "text", "image", "formula", "edge"}:
            raise ScenePatchError("Invalid scene item type")
        result[item_id] = item
    return result


def validate_symbol_consistency(scene: dict) -> dict:
    """Check optional concept -> symbol declarations without judging semantics.

    metadata.symbol_registry maps concept IDs to {kind, asset_ref?, shape?}.
    metadata.concept_bindings maps visual item IDs to concept IDs. All image
    members of a concept must reuse one exact asset reference; shape members
    reuse one geometry. Fill/stroke colour may vary by branch. Existing scenes
    without these optional declarations are accepted unchanged.
    """
    items = _item_map(scene)
    metadata = scene.get("metadata", {})
    if not isinstance(metadata, dict):
        return {"pass": False, "checked": True, "errors": [{"code": "invalid_metadata"}]}
    registry = metadata.get("symbol_registry")
    bindings = metadata.get("concept_bindings")
    if registry is None and bindings is None:
        return {"pass": True, "checked": False, "errors": [],
                "scope": "No symbol declarations; semantic correctness was not checked."}
    errors = []
    if not isinstance(registry, dict) or not isinstance(bindings, dict):
        return {"pass": False, "checked": True, "errors": [{"code": "invalid_symbol_registry_or_bindings"}]}
    for concept_id, symbol in registry.items():
        if (not isinstance(concept_id, str) or not concept_id or not isinstance(symbol, dict)
                or not isinstance(symbol.get("kind"), str) or not symbol["kind"].strip()):
            errors.append({"code": "missing_canonical_kind", "concept": str(concept_id)})
            continue
        if set(symbol) - {"kind", "asset_ref", "shape", "description"}:
            errors.append({"code": "unknown_symbol_field", "concept": concept_id})
        if "asset_ref" in symbol and (not isinstance(symbol["asset_ref"], str) or not symbol["asset_ref"]):
            errors.append({"code": "invalid_symbol_asset", "concept": concept_id})
        if "shape" in symbol and (not isinstance(symbol["shape"], str) or symbol["shape"] not in {"rect", "ellipse", "polygon", "line"}):
            errors.append({"code": "invalid_symbol_shape", "concept": concept_id})
    members = {}
    for item_id, concept_id in bindings.items():
        if item_id not in items:
            errors.append({"code": "unknown_concept_item", "item": item_id})
            continue
        if not isinstance(concept_id, str) or concept_id not in registry:
            errors.append({"code": "unknown_concept", "item": item_id})
            continue
        members.setdefault(concept_id, []).append(items[item_id])
    for concept_id, group in members.items():
        symbol = registry[concept_id]
        if not isinstance(symbol, dict):
            continue
        item_types = {item.get("type") for item in group}
        if len(item_types) > 1:
            errors.append({"code": "mixed_symbol_types", "concept": concept_id})
        images = [item for item in group if item.get("type") == "image"]
        if images:
            expected = symbol.get("asset_ref", images[0].get("source"))
            for item in images:
                if item.get("source") != expected:
                    errors.append({"code": "symbol_asset_mismatch", "concept": concept_id, "item": item["id"]})
        elif "asset_ref" in symbol:
            errors.append({"code": "asset_symbol_requires_images", "concept": concept_id})
        shapes = [item for item in group if item.get("type") == "shape"]
        if shapes:
            expected = symbol.get("shape", shapes[0].get("shape", "rect"))
            for item in shapes:
                if item.get("shape", "rect") != expected:
                    errors.append({"code": "symbol_shape_mismatch", "concept": concept_id, "item": item["id"]})
        elif "shape" in symbol:
            errors.append({"code": "shape_symbol_requires_shapes", "concept": concept_id})
    return {"pass": not errors, "checked": True, "errors": errors,
            "concept_count": len(registry), "bound_item_count": len(bindings),
            "scope": "Declared kind/asset/geometry consistency only; colours may vary. No semantic truth verification."}


def _deep_merge(original: dict, updates: dict) -> dict:
    result = deepcopy(original)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _ids(value, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ScenePatchError(f"{label} must be an array of item IDs")
    if len(set(value)) != len(value):
        raise ScenePatchError(f"{label} contains duplicate IDs")
    return value


def apply_scene_patch(scene: dict, patch: dict) -> tuple[dict, dict]:
    """Apply finite data atomically; return a new scene and a replay receipt.

    Required: base_sha256. Optional: version=1, updates=[{id,...fields}],
    remove_ids, append, metadata (replacement), rationale, and scope.
    Nested update dictionaries, notably style, are merged recursively.
    A scope with editable_ids locks all other items and forbids new items unless
    allow_append=True. Removing scoped items requires allow_remove=True.
    Canvas, item IDs, types, and the order of retained items are never mutated.
    Geometry QA must still run on the returned scene before final delivery.
    """
    _json_bytes(scene)
    _json_bytes(patch)
    before = _item_map(scene)
    if not isinstance(patch, dict) or set(patch) - {
        "version", "base_sha256", "updates", "remove_ids", "append", "metadata", "scope", "rationale"
    }:
        raise ScenePatchError("Patch contains unknown fields")
    if patch.get("version", 1) != 1:
        raise ScenePatchError("Only patch version 1 is supported")
    base_hash = hash_scene(scene)
    if patch.get("base_sha256") != base_hash:
        raise ScenePatchError("Patch base_sha256 does not match the current scene")
    updates = patch.get("updates", [])
    appended = patch.get("append", [])
    if not isinstance(updates, list) or not isinstance(appended, list):
        raise ScenePatchError("updates and append must be arrays")
    removals = set(_ids(patch.get("remove_ids", []), "remove_ids"))
    if len(updates) + len(appended) + len(removals) > 1000:
        raise ScenePatchError("Patch operation limit exceeded")
    if not removals.issubset(before):
        raise ScenePatchError("Cannot remove an unknown item ID")
    scope = patch.get("scope", {})
    if not isinstance(scope, dict) or set(scope) - {"editable_ids", "allow_append", "allow_remove"}:
        raise ScenePatchError("Invalid patch scope")
    for key in ("allow_append", "allow_remove"):
        if key in scope and type(scope[key]) is not bool:
            raise ScenePatchError("Scope grants must be booleans")
    scoped = "editable_ids" in scope
    editable = set(_ids(scope["editable_ids"], "editable_ids")) if scoped else set(before)
    if not editable.issubset(before):
        raise ScenePatchError("Scope contains unknown item IDs")
    if removals and (not removals.issubset(editable) or not scope.get("allow_remove", not scoped)):
        raise ScenePatchError("Removal is outside the granted scope")
    changed = set()
    replacements = {}
    for update in updates:
        if not isinstance(update, dict) or not isinstance(update.get("id"), str):
            raise ScenePatchError("Every update requires an item ID")
        item_id = update["id"]
        if item_id not in before or item_id not in editable:
            raise ScenePatchError("Update contains an unknown or locked item ID")
        if item_id in replacements or item_id in removals:
            raise ScenePatchError("Duplicate/conflicting operations for one item ID")
        if "type" in update and update["type"] != before[item_id].get("type"):
            raise ScenePatchError("An item type cannot change through a local patch")
        replacement = _deep_merge(before[item_id], update)
        replacements[item_id] = replacement
        if replacement != before[item_id]:
            changed.add(item_id)
    if appended and not scope.get("allow_append", not scoped):
        raise ScenePatchError("Appending items is outside the granted scope")
    new_map = _item_map({"canvas": scene["canvas"], "items": appended})
    if set(new_map) & set(before):
        raise ScenePatchError("Appended IDs must be new, including IDs removed by this patch")
    updated = deepcopy(scene)
    updated["items"] = [deepcopy(replacements.get(item["id"], item)) for item in scene["items"]
                        if item["id"] not in removals] + deepcopy(appended)
    if "metadata" in patch:
        if not isinstance(patch["metadata"], dict):
            raise ScenePatchError("metadata must be an object")
        updated["metadata"] = deepcopy(patch["metadata"])
    _item_map(updated)
    audit = validate_symbol_consistency(updated)
    if not audit["pass"]:
        raise ScenePatchError("Symbol-consistency validation failed: " +
                              ", ".join(issue["code"] for issue in audit["errors"]))
    unchanged_ids = sorted(set(before) - changed - removals)
    after = _item_map(updated)
    unchanged_hashes = {item_id: hash_scene(before[item_id]) for item_id in unchanged_ids}
    if any(hash_scene(after[item_id]) != expected for item_id, expected in unchanged_hashes.items()):
        raise ScenePatchError("An unchanged item failed its integrity check")
    receipt = {"version": 1, "base_sha256": base_hash, "patch_sha256": hash_scene(patch),
               "result_sha256": hash_scene(updated), "changed_ids": sorted(changed),
               "added_ids": list(new_map), "removed_ids": sorted(removals),
               "unchanged_ids": unchanged_ids, "unchanged_item_sha256": unchanged_hashes,
               "canvas_unchanged": updated["canvas"] == scene["canvas"],
               "metadata_changed": updated.get("metadata") != scene.get("metadata"),
               "scope": deepcopy(scope), "symbol_consistency": audit,
               "qa_status": "geometry_and_semantic_review_required"}
    return updated, receipt
