"""Normalize resolved Ardot batch_read trees, not an LLM-authored scene export.

Bindings select semantic roles/assets and approved font mappings only. Geometry,
copy, style, z order, text descendants and state hashes come from the raw tree.
Unsupported/truncated nodes fail with their IDs. No network, design writes or
host-attestation claims occur in this converter.
"""
import copy
import math
from production_intent import digest


def normalize_capture(capture, bindings):
    if capture.get("source") != "ardot-batch-read-capture-v1":
        raise ValueError("expected an actual resolved Ardot batch_read capture")
    root = capture.get("root")
    if not isinstance(root, dict) or root.get("id") != capture.get("root_node_id"):
        raise ValueError("capture root identity mismatch")
    index, positions, sequence, parents = {}, {}, {}, {}
    def walk(node, x=0, y=0, parent=None):
        if not isinstance(node, dict) or not node.get("id") or node["id"] in index:
            raise ValueError("duplicate, incomplete or compressed Ardot node; reread IDs at greater depth")
        node_id = node["id"]
        if any(node.get(k) for k in ("rotation", "isMask", "effects")):
            raise ValueError(f"unsupported transform/mask/effect on {node_id}; resolve in Ardot")
        if node.get("blendMode", "NORMAL") not in {"NORMAL", "PASS_THROUGH"}:
            raise ValueError(f"unsupported blend mode on {node_id}")
        if node.get("children") and node.get("opacity", 1) != 1:
            raise ValueError(f"unsupported inherited opacity on {node_id}")
        geometry = {}
        for key in ("x", "y", "width", "height"):
            value = node.get(key)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{node_id}.{key} must be resolved numeric geometry")
            geometry[key] = value
        geometry["x"] += x
        geometry["y"] += y
        index[node_id], positions[node_id], parents[node_id] = node, geometry, parent
        sequence[node_id] = len(sequence)
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError(f"compressed children on {node_id}; reread them")
        for child in children:
            walk(child, geometry["x"], geometry["y"], node_id)
    walk(root)
    if root["width"] != 390:
        raise ValueError("current Ardot root must be 390 px wide")
    def descendants(node_id):
        return [node_id] + [kid for child in index[node_id].get("children", []) for kid in descendants(child["id"])]
    def visible(node_id):
        return index[node_id].get("visible", True) and (parents[node_id] is None or visible(parents[node_id]))
    def local(node_id, parent_id):
        if node_id not in descendants(parent_id):
            raise ValueError(f"node {node_id} is outside section {parent_id}")
        value = dict(positions[node_id])
        value["x"] -= positions[parent_id]["x"]
        value["y"] -= positions[parent_id]["y"]
        return value
    def paint(node):
        if isinstance(node.get("fill"), str):
            return node["fill"]
        fills = [f for f in node.get("fills", []) if f.get("visible", True)]
        if len(fills) != 1 or fills[0].get("type") != "SOLID" or fills[0].get("opacity", 1) != 1:
            raise ValueError(f"unsupported text paint on {node['id']}")
        color = fills[0]["color"]
        return "#" + "".join(f"{round(color[k] * 255):02x}" for k in ("r", "g", "b"))
    def text_style(node):
        font = node.get("fontName", {})
        mapped = bindings.get("font_mapping", {}).get(font.get("family"))
        if mapped not in {"system-sans-cn", "system-serif-cn"}:
            raise ValueError(f"unapproved font mapping on {node['id']}")
        size = float(node["fontSize"])
        line = node.get("lineHeight")
        if not isinstance(line, dict) or line.get("unit") not in {"PIXELS", "PERCENT"}:
            raise ValueError(f"unresolved line height on {node['id']}")
        spacing = node.get("letterSpacing", {"unit": "PIXELS", "value": 0})
        if not isinstance(spacing, dict) or spacing.get("unit") != "PIXELS":
            raise ValueError(f"unresolved letter spacing on {node['id']}")
        return {"font_family": mapped, "font_size_px": size,
                "line_height_ratio": float(line["value"]) / (size if line["unit"] == "PIXELS" else 100),
                "font_weight": int(node["fontWeight"]), "font_style": "italic" if "italic" in str(font.get("style", "")).lower() else "normal",
                "text_decoration": str(node.get("textDecoration", "none")).lower().replace("strikethrough", "line-through"),
                "color": paint(node), "letter_spacing_px": spacing["value"],
                "text_align": str(node.get("textAlignHorizontal", "left")).lower(),
                "opacity": node.get("opacity", 1), "rotation_deg": 0, "blend_mode": "normal"}
    def asset_layer(binding, section_id, role):
        result = copy.deepcopy(binding)
        node_id = result["source_node_id"]
        node = index[node_id]
        if not visible(node_id):
            raise ValueError(f"selected asset node is hidden: {node_id}")
        result["geometry"] = local(node_id, section_id)
        result["z_index"] = sequence[node_id]
        image_fills = [f for f in node.get("fills", []) if f.get("type") == "IMAGE"]
        mode = image_fills[0].get("scaleMode", "FILL") if image_fills else "FILL"
        if mode not in {"FILL", "FIT"} or any(f.get("imageTransform") for f in image_fills):
            raise ValueError(f"unsupported image crop on {node_id}")
        result["render_style"] = {"object_fit": "cover" if mode == "FILL" else "contain", "object_position": "50% 50%", "opacity": node.get("opacity", 1), "rotation_deg": 0, "blend_mode": "normal", "mask": "none"}
        if role == "background":
            if any(str(index[n].get("type")).lower() == "text" and visible(n) for n in descendants(node_id)):
                raise ValueError("background subtree contains text")
            result.update(z_index=0, width_px=390 * 3, height_px=index[section_id]["height"] * 3,
                          export_scale=3, contains_text=False, text_baked=False, text_node_count=0)
        elif role == "article-micro":
            if any(str(index[n].get("type")).lower() == "text" and visible(n) for n in descendants(node_id)):
                raise ValueError("cutout subtree contains native text; bind it independently")
            result.update(role=role, independent=True, contained_in_background=False)
        else:
            result["role"] = role
        return result
    chapters, component_order, covered = [], [], set()
    for spec in bindings["chapters"]:
        section = spec["section_node_id"]
        chapter = {"chapter_id": spec["chapter_id"], "section_node_id": section,
                   "geometry": local(section, root["id"]), "geometry_space": "article-root-390-v1",
                   "reference_screenshot": copy.deepcopy(spec["reference_screenshot"])}
        chapter["background_layer"] = asset_layer(spec["background_layer"], section, "background")
        covered.update(descendants(spec["background_layer"]["source_node_id"]))
        chapter["visible_text_nodes"] = []
        for item in spec["visible_text_nodes"]:
            node_id = item["node_id"]
            node = index[node_id]
            if str(node.get("type")).lower() != "text" or not visible(node_id) or not isinstance(node.get("content"), str):
                raise ValueError(f"not a complete visible native text node: {node_id}")
            chapter["visible_text_nodes"].append({**item, "text": node["content"], "native_editable_text": True,
                "geometry": local(node_id, section), "style": text_style(node), "z_index": sequence[node_id], "component_name": node["name"]})
            component_order.append({"node_id": node_id, "component_name": node["name"]})
            covered.add(node_id)
        for field, role in (("decorations", "article-micro"), ("photos", "documentary-evidence")):
            chapter[field] = [asset_layer(item, section, role) for item in spec.get(field, [])]
            for item in spec.get(field, []):
                covered.update(descendants(item["source_node_id"]))
        chapter["interaction"] = []
        for item in spec.get("interaction", []):
            node_id = item["source_node_id"]
            states = item["state_node_ids"]
            if set(states) != {"closed", "open", "fallback"} or len(set(states.values())) != 3:
                raise ValueError("interaction requires three distinct native state nodes")
            if not all(state_id in descendants(node_id) and state_id != node_id for state_id in states.values()):
                raise ValueError("interaction states must belong to the bound component")
            layer = {**item, "geometry": local(node_id, section), "z_index": sequence[node_id],
                     "render_style": {"opacity": 1, "rotation_deg": 0, "blend_mode": "normal", "overflow": "hidden"}}
            layer["ardot_states"] = {name: {"node_id": state_id, "tree_sha256": digest(index[state_id])} for name, state_id in item["state_node_ids"].items()}
            layer.pop("state_node_ids")
            covered.update(descendants(node_id))
            chapter["interaction"].append(layer)
        chapters.append(chapter)
    unbound = [n for n in index if visible(n) and n not in covered and not index[n].get("children")]
    if unbound:
        raise ValueError(f"unbound visible leaves; do not silently omit them: {unbound}")
    bound_ids = []
    for chapter in chapters:
        bound_ids.extend([chapter["section_node_id"], chapter["background_layer"]["source_node_id"]])
        bound_ids.extend(n["node_id"] for n in chapter["visible_text_nodes"])
        bound_ids.extend(n["source_node_id"] for field in ("decorations", "photos", "interaction") for n in chapter[field])
    if len(bound_ids) != len(set(bound_ids)):
        raise ValueError("a source node cannot be bound as multiple transport layers")
    component_order = [{"node_id": n, "component_name": index[n].get("name", n)} for n in sorted(bound_ids, key=sequence.get)]
    return {"schema_version": 1, "source": "ardot-host-normalized-export-v1", "article": copy.deepcopy(bindings["article"]),
            "ardot": {"file_id": capture["file_id"], "root_node_id": root["id"], "captured_at": capture["captured_at"], "revision_algorithm": "ardot-root-revision-v1"},
            "chapters": chapters, "assets": copy.deepcopy(bindings["assets"]), "component_order": component_order,
            "capture_binding": {"sha256": digest(capture), "bindings_sha256": digest(bindings), "host_attested": False}}
