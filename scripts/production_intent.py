"""User intent survives authoring, Ardot editing and final transport.

Hashes bind decisions to an artifact; they do not authenticate who approved it.
The current task must retain the actual grouped user/editor approval.
"""
import hashlib
import json
import copy


def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def generation_selection(document):
    raw = document.get("generation")
    if raw is None:
        return {"opaque": True, "rgba": True}  # legacy/undecided, never silent opt-out
    if not isinstance(raw, dict) or set(raw) != {"micro_component_count", "generate_backgrounds", "generate_cover"}:
        raise ValueError("generation requires micro_component_count, generate_backgrounds and generate_cover")
    count = raw["micro_component_count"]
    if type(count) is not int or not 0 <= count <= 4 or any(type(raw[k]) is not bool for k in ("generate_backgrounds", "generate_cover")):
        raise ValueError("invalid generation selection")
    return {"opaque": raw["generate_backgrounds"] or raw["generate_cover"], "rgba": count > 0}


def freeze_intent(article, export):
    from workflow_quality import validate_production_preferences
    result = validate_production_preferences(article)
    if not result["ready"]:
        raise ValueError("; ".join(result["errors"]))
    value = {"schema_version": 1, "preferences": copy.deepcopy(article["production_preferences"]),
             "route": article["route"], "transport_sha256": digest(export)}
    value["sha256"] = digest(value)
    return value


def validate_delivery_intent(handoff, export):
    article = handoff.get("article", {})
    intent = handoff.get("production_intent")
    if not isinstance(intent, dict):
        return ["missing frozen production_intent; refreeze the reviewed Ardot root"]
    errors = []
    try:
        if intent != freeze_intent(article, export):
            errors.append("approved production intent or transport changed; reconfirm and refreeze")
        prefs = article["production_preferences"]
        chapters = export.get("chapters", [])
        decorations = [d for c in chapters for d in c.get("decorations", [])]
        # Count assets, not repeated placement instances.
        count = len({d.get("asset_id") for d in decorations})
        if count != prefs["micro_component_count"]:
            errors.append("delivered micro asset count differs from confirmed choice")
        interactions = [i for c in chapters for i in (c.get("interaction") if isinstance(c.get("interaction"), list) else [c.get("interaction")]) if isinstance(i, dict)]
        dynamic = [i for i in interactions if i.get("mode") in {"svg", "horizontal-swipe"}]
        if not prefs["use_svg"] and dynamic:
            errors.append("SVG/swipe authored despite confirmed static selection")
        if prefs["use_svg"] and not dynamic:
            errors.append("requested interaction candidates are missing from the Ardot master")
        assets = {a.get("id"): a for a in handoff.get("assets", [])}
        backgrounds = [assets.get(c.get("background_layer", {}).get("asset_id"), {}) for c in chapters if c.get("background_layer")]
        if any(a.get("origin") not in {"generated-illustrative", "derived", "official", "photographed"} for a in backgrounds):
            errors.append("background origin must be explicit at final handoff")
        generated = any(a.get("origin") == "generated-illustrative" for a in backgrounds)
        if not prefs["generate_backgrounds"] and generated:
            errors.append("generated background contradicts confirmed native-surface selection")
        if prefs["generate_backgrounds"] and not generated:
            errors.append("requested generated background is absent from delivered layers")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return errors
