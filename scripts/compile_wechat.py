#!/usr/bin/env python3
"""Compile a structured organization article into preview and WeChat-safe HTML."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REMOTE_SRC = re.compile(r"^(?:https?://|data:)", re.I)
PLACEHOLDERS = re.compile(r"(?:待补充|待确认|待提供|PLACEHOLDER|\bTBD\b|\bTODO\b)", re.I)
UNSAFE_WECHAT = re.compile(r"<(?:script|style|iframe|form|link)\b", re.I)
SUPPORTED_BLOCKS = {
    "hero",
    "lead",
    "section",
    "text",
    "statement",
    "metrics",
    "timeline",
    "gallery",
    "case",
    "roles",
    "quote",
    "steps",
    "image",
    "cta",
    "references",
    "footer",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc


def style(**values: Any) -> str:
    return ";".join(
        f"{key.replace('_', '-')}:{value}"
        for key, value in values.items()
        if value is not None and value != ""
    )


def paragraphs(items: list[Any], color: str) -> str:
    return "".join(
        f'<p style="margin:0 0 14px;line-height:1.82;font-size:16px;color:{color};letter-spacing:.015em;">{esc(item)}</p>'
        for item in items
    )


def slug_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return cleaned or "asset"


@dataclass
class CompileContext:
    spec_path: Path
    org_dir: Path
    output_dir: Path
    organization: dict[str, Any]
    sources_doc: dict[str, Any]
    components_doc: dict[str, Any]
    assets_doc: dict[str, Any]
    route: dict[str, Any]
    check: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    copied_assets: list[dict[str, str]] = field(default_factory=list)
    component_ids: list[str] = field(default_factory=list)
    used_source_ids: set[str] = field(default_factory=set)

    @property
    def tokens(self) -> dict[str, str]:
        return self.organization["visual"]["tokens"]

    @property
    def source_ids(self) -> set[str]:
        return {
            item["id"]
            for item in self.sources_doc.get("sources", [])
            if isinstance(item, dict) and item.get("id")
        }

    @property
    def registered_components(self) -> set[str]:
        return {
            item["id"]
            for item in self.components_doc.get("components", [])
            if isinstance(item, dict) and item.get("id")
        }

    def use_source(self, source_id: Any, label: str, required: bool = False) -> None:
        if not source_id:
            if required:
                self.errors.append(f"{label} requires source_id")
            return
        if source_id not in self.source_ids:
            self.errors.append(f"{label} references unknown source_id: {source_id}")
            return
        self.used_source_ids.add(str(source_id))

    def component(self, block: dict[str, Any]) -> str:
        block_type = block.get("type", "unknown")
        component_id = str(block.get("component", f"core.{block_type}"))
        self.component_ids.append(component_id)
        if component_id not in self.registered_components:
            self.warnings.append(f"unregistered component ID: {component_id}")
        return component_id

    def variant(self, block: dict[str, Any], block_type: str) -> str:
        explicit = block.get("variant")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        configured = self.route.get("component_variants", {}).get(block_type)
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        defaults = {
            "warm-community": {
                "hero": "soft-stage", "section": "soft-marker", "statement": "editorial-pullout",
                "roles": "role-bands", "steps": "journey-path", "cta": "launch-pad",
            },
            "technical": {
                "hero": "technical-stage", "section": "index-rail", "statement": "open-rule",
                "metrics": "number-field", "timeline": "mission-line", "case": "process-strip",
                "steps": "process-rail", "cta": "action-gate",
            },
            "poster": {
                "hero": "poster-stage", "section": "poster-band", "statement": "poster-callout",
                "metrics": "number-field", "timeline": "action-line", "cta": "poster-gate",
            },
            "institutional": {
                "hero": "quiet-editorial", "section": "editorial-head", "statement": "open-rule",
                "metrics": "ledger", "timeline": "report-line", "case": "evidence-ledger",
                "cta": "quiet-gate",
            },
            "editorial": {
                "hero": "image-stage", "section": "editorial-head", "statement": "editorial-pullout",
                "gallery": "photo-story", "cta": "action-gate",
            },
        }
        return defaults.get(self.route.get("layout", "editorial"), {}).get(block_type, "standard")

    def asset_src(self, source: Any, label: str) -> str:
        if not isinstance(source, str) or not source.strip():
            self.errors.append(f"{label} requires a non-empty image src")
            return ""
        if REMOTE_SRC.match(source):
            return source
        candidate = (self.spec_path.parent / source).resolve()
        if not candidate.exists():
            registered = {
                item.get("id"): item
                for item in self.assets_doc.get("assets", [])
                if isinstance(item, dict)
            }
            if source in registered:
                location = registered[source].get("location")
                if isinstance(location, str) and REMOTE_SRC.match(location):
                    return location
                if isinstance(location, str):
                    candidate = (self.org_dir / location).resolve()
        if not candidate.exists() or not candidate.is_file():
            self.errors.append(f"missing local asset for {label}: {source}")
            return source
        digest = hashlib.sha1(str(candidate).encode("utf-8")).hexdigest()[:10]
        target_name = f"{slug_part(candidate.stem)}-{digest}{candidate.suffix.lower()}"
        asset_dir = self.output_dir / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        target = asset_dir / target_name
        if not target.exists() or candidate.stat().st_mtime_ns > target.stat().st_mtime_ns:
            shutil.copy2(candidate, target)
        relative = f"assets/{target_name}"
        record = {"source": str(candidate), "output": relative}
        if record not in self.copied_assets:
            self.copied_assets.append(record)
        return relative

    def image_html(self, item: dict[str, Any], label: str, extra_style: str = "") -> str:
        src = self.asset_src(item.get("src"), label)
        alt = item.get("alt")
        if not isinstance(alt, str) or not alt.strip():
            self.errors.append(f"{label} requires useful alt text")
            alt = ""
        if item.get("source_id"):
            self.use_source(item.get("source_id"), label)
        return (
            f'<img src="{esc(src)}" alt="{esc(alt)}" '
            f'style="display:block;width:100%;height:100%;object-fit:cover;{extra_style}">'
        )


def route_shape(ctx: CompileContext) -> dict[str, str]:
    layout = ctx.route["layout"]
    if layout == "warm-community":
        return {"radius": "18px", "border_width": "1px", "shadow": "0 10px 28px rgba(0,0,0,.06)"}
    if layout == "editorial":
        return {"radius": "8px", "border_width": "1px", "shadow": "0 8px 24px rgba(0,0,0,.05)"}
    return {"radius": "0", "border_width": "2px", "shadow": "none"}


def hero(ctx: CompileContext, block: dict[str, Any], component: str) -> str:
    t = ctx.tokens
    layout = ctx.route["layout"]
    variant = ctx.variant(block, "hero")
    background = block.get("background")
    background_style = ""
    if background:
        src = ctx.asset_src(background, "hero background")
        if not block.get("background_alt"):
            ctx.errors.append("hero background requires background_alt")
        background_style = style(
            background_image=f"url('{esc(src)}')",
            background_size="cover",
            background_position="center",
        )
    dark_stage = layout in {"poster", "technical"}
    section_bg = t["ink"] if dark_stage else t["surface_alt"]
    panel_bg = t["ink"] if dark_stage else t["surface"]
    title_color = t.get("on_accent", t["white"]) if dark_stage else t["ink"]
    body_color = t.get("on_accent", t["white"]) if dark_stage else t["body"]
    accent = t["accent_alt"] if dark_stage else t["accent"]
    if background:
        panel_bg = "rgba(10,13,18,.88)" if dark_stage else "rgba(255,255,255,.91)"
    cta = ""
    if block.get("cta"):
        cta = f'<div style="display:inline-block;margin-top:18px;padding:9px 13px;background:{accent};color:{t.get("on_accent_alt", t["ink"])};font-size:13px;font-weight:800;">{esc(block["cta"])}</div>'
    panel_width = "88%" if layout in {"editorial", "warm-community"} else "100%"
    panel_margin = "0 0 0 auto" if layout == "editorial" else "0"
    panel_border = f"border-left:7px solid {accent};" if layout in {"technical", "institutional"} else f"border-top:7px solid {accent};"
    return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" aria-label="{esc(block.get("background_alt", ""))}" style="min-height:560px;padding:26px;background:{section_bg};{background_style}display:flex;align-items:flex-end;">
<div style="width:{panel_width};margin:{panel_margin};padding:25px 23px;background:{panel_bg};{panel_border}">
<div style="font-size:10px;font-weight:900;letter-spacing:.14em;color:{accent};">{esc(block.get("eyebrow", ctx.organization["identity"]["short_name"]))}</div>
<h1 style="margin:13px 0 0;font-size:40px;line-height:1.12;letter-spacing:-.04em;color:{title_color};font-weight:900;">{esc(block["title"])}</h1>
<p style="margin:15px 0 0;max-width:28em;font-size:16px;line-height:1.72;color:{body_color};font-weight:650;">{esc(block.get("subtitle", ""))}</p>{cta}
</div></section>'''


def render_block(ctx: CompileContext, block: dict[str, Any], index: int) -> str:
    kind = block.get("type")
    if kind not in SUPPORTED_BLOCKS:
        ctx.errors.append(f"block {index} has unsupported type: {kind}")
        return ""
    component = ctx.component(block)
    variant = ctx.variant(block, str(kind))
    t = ctx.tokens
    shape = route_shape(ctx)

    if kind == "hero":
        return hero(ctx, block, component)

    if kind in {"lead", "text"}:
        items = block.get("paragraphs")
        if not isinstance(items, list) or not items:
            ctx.errors.append(f"block {index} ({kind}) requires paragraphs")
            items = []
        if kind == "lead":
            rendered_paragraphs = "".join(
                f'<p style="margin:0 0 {18 if item_index == 0 else 13}px;font-size:{19 if item_index == 0 else 15}px;line-height:{1.72 if item_index == 0 else 1.82};font-weight:{750 if item_index == 0 else 450};color:{t["ink"] if item_index == 0 else t["body"]};">{esc(item)}</p>'
                for item_index, item in enumerate(items)
            )
            return f'<section data-component="{esc(component)}" data-variant="lead-open" style="padding:38px 28px 31px;background:{t["surface"]};border-bottom:1px solid {t["border"]};">{rendered_paragraphs}</section>'
        return f'<section data-component="{esc(component)}" data-variant="text-open" style="padding:24px 28px 34px;background:{t["surface"]};">{paragraphs(items, t["body"])}</section>'

    if kind == "section":
        number = block.get("number")
        badge = f'<div style="flex:0 0 62px;font-size:34px;line-height:1;font-weight:900;color:{t["accent"]};">{esc(number)}</div>' if number is not None else ""
        kicker = f'<div style="margin-bottom:6px;font-size:10px;font-weight:800;letter-spacing:.1em;color:{t["accent"]};">{esc(block["kicker"])}</div>' if block.get("kicker") else ""
        if variant == "poster-band":
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:30px 25px;background:{t["accent"]};border-top:8px solid {t["accent_alt"]};">
<div style="font-size:11px;font-weight:900;letter-spacing:.12em;color:{t["accent_alt"]};">{esc(number if number is not None else block.get("kicker", ""))}</div><h2 style="margin:11px 0 0;font-size:29px;line-height:1.2;color:{t.get("on_accent", t["white"])};">{esc(block["title"])}</h2></section>'''
        if variant in {"index-rail", "editorial-head"}:
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="display:flex;gap:16px;padding:40px 26px 18px;background:{t["surface"]};border-top:3px solid {t["ink"]};">
{badge}<div style="flex:1;">{kicker}<h2 style="margin:0;font-size:27px;line-height:1.28;letter-spacing:-.02em;color:{t["ink"]};">{esc(block["title"])}</h2></div></section>'''
        return f'''<section data-component="{esc(component)}" style="display:flex;gap:12px;padding:34px 24px 14px;background:{t["surface"]};border-top:{shape["border_width"]} solid {t["border"]};">
{badge}<div style="flex:1;">{kicker}<h2 style="margin:0;font-size:25px;line-height:1.35;color:{t["ink"]};">{esc(block["title"])}</h2></div></section>'''

    if kind == "statement":
        body = f'<p style="margin:13px 0 0;font-size:14px;line-height:1.75;color:{t["body"]};">{esc(block["body"])}</p>' if block.get("body") else ""
        if variant in {"open-rule", "editorial-pullout"}:
            align = "right" if variant == "editorial-pullout" else "left"
            inset = "42px 25px 46px 58px" if variant == "editorial-pullout" else "35px 28px"
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:{inset};background:{t["surface_alt"]};text-align:{align};border-left:9px solid {t["accent"]};">
<div style="font-size:10px;font-weight:900;letter-spacing:.14em;color:{t["accent"]};">{esc(block.get("label", "KEY MESSAGE"))}</div>
<h3 style="margin:12px 0 0;font-size:27px;line-height:1.38;letter-spacing:-.02em;color:{t["ink"]};">{esc(block["title"])}</h3>{body}</section>'''
        if variant == "poster-callout":
            return f'''<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:34px 26px;background:{t["ink"]};border-bottom:10px solid {t["accent_alt"]};">
<div style="font-size:10px;font-weight:900;letter-spacing:.14em;color:{t["accent_alt"]};">{esc(block.get("label", "KEY MESSAGE"))}</div><h3 style="margin:12px 0 0;font-size:29px;line-height:1.3;color:{t["white"]};">{esc(block["title"])}</h3></section>'''
        return f'''<section data-component="{esc(component)}" style="padding:22px 24px;background:{t["surface_alt"]};">
<div style="padding:20px;background:{t["surface"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};box-shadow:{shape["shadow"]};">
<div style="font-size:10px;font-weight:800;letter-spacing:.1em;color:{t["accent"]};">{esc(block.get("label", "KEY MESSAGE"))}</div>
<h3 style="margin:10px 0 0;font-size:23px;line-height:1.45;color:{t["ink"]};">{esc(block["title"])}</h3>{body}</div></section>'''

    if kind == "metrics":
        items = block.get("items", [])
        if not isinstance(items, list) or not items:
            ctx.errors.append(f"block {index} (metrics) requires items")
            items = []
        cards = []
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                ctx.errors.append(f"metric {item_index} must be an object")
                continue
            ctx.use_source(item.get("source_id"), f"metric {item_index}", required=True)
            if variant in {"number-field", "ledger"}:
                cards.append(
                    f'<div style="display:inline-block;vertical-align:top;width:50%;min-height:132px;padding:21px 16px;background:{t["surface"]};border-top:2px solid {t["ink"]};">'
                    f'<div style="font-size:38px;line-height:1;font-weight:900;letter-spacing:-.04em;color:{t["accent"]};">{esc(item.get("value", ""))}</div>'
                    f'<div style="margin-top:12px;max-width:12em;font-size:12px;line-height:1.55;font-weight:750;color:{t["ink"]};">{esc(item.get("label", ""))}</div></div>'
                )
            else:
                cards.append(
                    f'<div style="display:inline-block;vertical-align:top;width:47%;min-height:114px;margin:0 1.5% 10px;padding:14px 12px;background:{t["surface_alt"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};">'
                    f'<div style="font-size:28px;line-height:1.08;font-weight:900;color:{t["accent"]};">{esc(item.get("value", ""))}</div>'
                    f'<div style="margin-top:8px;font-size:12px;line-height:1.5;font-weight:700;color:{t["ink"]};">{esc(item.get("label", ""))}</div></div>'
                )
        padding = "24px 18px 32px" if variant not in {"number-field", "ledger"} else "18px 24px 36px"
        return f'<section data-component="{esc(component)}" data-variant="{esc(variant)}" style="padding:{padding};background:{t["surface"]};">{"".join(cards)}</section>'

    if kind == "timeline":
        rows = []
        for item_index, item in enumerate(block.get("items", [])):
            if not isinstance(item, dict):
                ctx.errors.append(f"timeline item {item_index} must be an object")
                continue
            ctx.use_source(item.get("source_id"), f"timeline item {item_index}")
            rows.append(
                f'<div style="display:flex;gap:12px;margin-bottom:11px;"><div style="flex:0 0 76px;padding:8px;background:{t["accent_alt"]};color:{t.get("on_accent_alt", t["ink"])};font-size:12px;font-weight:900;">{esc(item.get("label", ""))}</div>'
                f'<div style="flex:1;padding:7px 0;font-size:14px;line-height:1.68;color:{t["body"]};">{esc(item.get("description", ""))}</div></div>'
            )
        return f'<section data-component="{esc(component)}" style="padding:22px 24px;background:{t["surface_alt"]};border-top:{shape["border_width"]} solid {t["border"]};border-bottom:{shape["border_width"]} solid {t["border"]};">{"".join(rows)}</section>'

    if kind == "gallery":
        slides = []
        for image_index, item in enumerate(block.get("images", [])):
            if not isinstance(item, dict):
                ctx.errors.append(f"gallery image {image_index} must be an object")
                continue
            image = ctx.image_html(item, f"gallery image {image_index}")
            slides.append(
                f'<div style="display:inline-block;vertical-align:top;width:84%;margin-right:10px;white-space:normal;">'
                f'<div style="height:220px;overflow:hidden;background:{t["surface_alt"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};">{image}</div>'
                f'<div style="padding:8px 2px 0;font-size:12px;line-height:1.5;color:{t["body"]};">{esc(item.get("caption", ""))}</div></div>'
            )
        if not slides:
            ctx.errors.append(f"block {index} (gallery) requires images")
        return f'''<section data-component="{esc(component)}" style="padding:14px 0 24px 24px;background:{t["surface"]};">
<div style="margin:0 24px 7px 0;text-align:right;font-size:10px;color:{t["accent"]};font-weight:800;letter-spacing:.08em;">左右滑动 →</div>
<div style="overflow-x:auto;overflow-y:hidden;white-space:nowrap;-webkit-overflow-scrolling:touch;padding-bottom:5px;">{"".join(slides)}</div></section>'''

    if kind == "case":
        ctx.use_source(block.get("source_id"), f"case block {index}")
        rows = "".join(
            f'<div style="padding:13px 14px;border-top:{shape["border_width"]} solid {t["border"]};font-size:14px;line-height:1.7;color:{t["body"]};"><b style="color:{t["accent"]};">{label}</b>　{esc(block.get(key, ""))}</div>'
            for label, key in (("问题", "problem"), ("方法", "approach"), ("产出", "output"))
        )
        evidence = f'<div style="padding:12px 14px;border-top:{shape["border_width"]} solid {t["border"]};background:{t["accent_alt"]};font-size:13px;line-height:1.65;color:{t.get("on_accent_alt", t["ink"])};"><b>证据</b>　{esc(block["evidence"])}</div>' if block.get("evidence") else ""
        return f'<section data-component="{esc(component)}" style="margin:16px 24px;background:{t["surface"]};border:{shape["border_width"]} solid {t["border"]};border-radius:{shape["radius"]};overflow:hidden;"><h3 style="margin:0;padding:15px 14px;background:{t["accent"]};color:{t.get("on_accent", t["white"])};font-size:20px;">{esc(block["name"])}</h3>{rows}{evidence}</section>'

    if kind == "roles":
        cards = []
        for item in block.get("items", []):
            cards.append(
                f'<div style="margin-bottom:10px;padding:15px 14px;background:{t["surface_alt"]};border-left:5px solid {t["accent"]};border-radius:{shape["radius"]};">'
                f'<div style="font-size:17px;font-weight:900;color:{t["ink"]};">{esc(item.get("name", ""))}</div>'
                f'<div style="margin-top:6px;font-size:13px;line-height:1.68;color:{t["body"]};">{esc(item.get("description", ""))}</div></div>'
            )
        return f'<section data-component="{esc(component)}" style="padding:12px 24px 24px;background:{t["surface"]};">{"".join(cards)}</section>'

    if kind == "quote":
        ctx.use_source(block.get("source_id"), f"quote block {index}", required=True)
        if not block.get("attribution"):
            ctx.errors.append(f"quote block {index} requires attribution")
        return f'''<section data-component="{esc(component)}" style="padding:30px 26px;background:{t["accent"]};color:{t.get("on_accent", t["white"])};">
<div style="font-size:34px;line-height:1;color:{t["accent_alt"]};">“</div><blockquote style="margin:2px 0 0;font-size:21px;line-height:1.65;font-weight:800;">{esc(block.get("text", ""))}</blockquote>
<div style="margin-top:12px;font-size:12px;opacity:.82;">— {esc(block.get("attribution", ""))}</div></section>'''

    if kind == "steps":
        rows = []
        for item_index, item in enumerate(block.get("items", []), 1):
            if isinstance(item, str):
                title, description = item, ""
            else:
                title, description = item.get("title", ""), item.get("description", "")
            desc = f'<div style="margin-top:4px;font-size:13px;line-height:1.6;color:{t["body"]};">{esc(description)}</div>' if description else ""
            rows.append(
                f'<div style="display:flex;gap:12px;margin-bottom:10px;"><div style="flex:0 0 32px;height:32px;background:{t["accent_alt"]};color:{t.get("on_accent_alt", t["ink"])};text-align:center;line-height:32px;font-weight:900;">{item_index:02d}</div>'
                f'<div style="flex:1;padding:5px 0;font-size:15px;font-weight:800;color:{t["ink"]};">{esc(title)}{desc}</div></div>'
            )
        return f'<section data-component="{esc(component)}" style="padding:20px 24px;background:{t["surface"]};">{"".join(rows)}</section>'

    if kind == "image":
        image = ctx.image_html(block, f"image block {index}")
        caption = f'<div style="padding:8px 2px 0;font-size:12px;line-height:1.5;color:{t["body"]};">{esc(block["caption"])}</div>' if block.get("caption") else ""
        return f'<section data-component="{esc(component)}" style="padding:16px 24px;background:{t["surface"]};"><div style="height:260px;overflow:hidden;border-radius:{shape["radius"]};">{image}</div>{caption}</section>'

    if kind == "cta":
        steps = "".join(
            f'<div style="margin-bottom:8px;font-size:14px;line-height:1.65;color:{t.get("on_accent", t["white"])};"><b style="color:{t["accent_alt"]};">{item_index:02d}</b>　{esc(item)}</div>'
            for item_index, item in enumerate(block.get("steps", []), 1)
        )
        body = f'<p style="margin:10px 0 15px;font-size:14px;line-height:1.75;color:{t.get("on_accent", t["white"])};">{esc(block["body"])}</p>' if block.get("body") else ""
        button = f'<div style="display:inline-block;margin-top:10px;padding:9px 13px;background:{t["accent_alt"]};color:{t.get("on_accent_alt", t["ink"])};font-size:13px;font-weight:900;">{esc(block["button"])}</div>' if block.get("button") else ""
        qr_html = ""
        if block.get("qr"):
            qr = block["qr"]
            if qr.get("origin") not in {"user-supplied", "official"}:
                ctx.errors.append(f"cta block {index} QR origin must be user-supplied or official")
            qr_html = f'<div style="width:150px;margin:18px auto 0;padding:8px;background:{t["white"]};">{ctx.image_html(qr, f"cta QR {index}", "object-fit:contain;")}</div>'
        return f'<section data-component="{esc(component)}" style="padding:26px 24px;background:{t["accent"]};"><h2 style="margin:0;font-size:25px;line-height:1.4;color:{t.get("on_accent", t["white"])};">{esc(block["title"])}</h2>{body}{steps}{button}{qr_html}</section>'

    if kind == "references":
        items = []
        for item_index, item in enumerate(block.get("items", [])):
            ctx.use_source(item.get("source_id"), f"reference {item_index}", required=True)
            items.append(f'<li style="margin:0 0 7px;line-height:1.6;">{esc(item.get("label", item.get("source_id", "")))}</li>')
        return f'<section data-component="{esc(component)}" style="padding:22px 26px;background:{t["surface_alt"]};font-size:12px;color:{t["body"]};"><div style="margin-bottom:9px;font-weight:900;color:{t["ink"]};">来源与说明</div><ol style="margin:0;padding-left:18px;">{"".join(items)}</ol></section>'

    if kind == "footer":
        logo_html = ""
        if block.get("logo"):
            logo = block["logo"]
            if isinstance(logo, str):
                logo_item = {"src": logo, "alt": f'{ctx.organization["identity"]["name"]} logo'}
            else:
                logo_item = logo
            logo_html = f'<div style="width:64px;height:64px;margin:0 auto 12px;">{ctx.image_html(logo_item, "footer logo", "object-fit:contain;")}</div>'
        return f'<section data-component="{esc(component)}" style="padding:32px 24px;text-align:center;background:{t["surface"]};border-top:{shape["border_width"]} solid {t["border"]};">{logo_html}<div style="font-size:17px;font-weight:900;color:{t["ink"]};">{esc(block.get("name", ctx.organization["identity"]["name"]))}</div><div style="margin-top:7px;font-size:12px;line-height:1.6;color:{t["body"]};">{esc(block.get("tagline", ""))}</div><div style="margin-top:12px;font-size:10px;color:{t["body"]};opacity:.72;">{esc(block.get("credits", ""))}</div></section>'

    raise AssertionError(f"unhandled block type: {kind}")


def load_context(spec_path: Path, org_dir: Path, output_dir: Path, check: bool) -> tuple[CompileContext, dict[str, Any]]:
    spec_path = spec_path.resolve()
    org_dir = org_dir.resolve()
    spec = read_json(spec_path)
    organization = read_json(org_dir / "organization.json")
    sources_doc = read_json(org_dir / "sources.json")
    components_doc = read_json(org_dir / "components.json")
    assets_doc = read_json(org_dir / "assets.json")

    errors: list[str] = []
    if spec.get("schema_version") != 1:
        errors.append("article.schema_version must be 1")
    if spec.get("organization_id") != organization.get("id"):
        errors.append("article.organization_id must match organization pack")
    article_type = spec.get("article_type")
    article_types = organization.get("article_types", {})
    if article_type not in article_types:
        errors.append(f"unknown article_type: {article_type}")
        article_config = {}
    else:
        article_config = article_types[article_type]
    route_id = spec.get("route") or article_config.get("route") or organization.get("visual", {}).get("default_route")
    route_map = {item["id"]: item for item in organization.get("visual", {}).get("routes", [])}
    route = route_map.get(route_id)
    if route is None:
        errors.append(f"unknown route: {route_id}")
        route = {"id": str(route_id), "label": str(route_id), "layout": "editorial", "dominant_style": "unknown"}

    output_dir.mkdir(parents=True, exist_ok=True)
    ctx = CompileContext(
        spec_path=spec_path,
        org_dir=org_dir,
        output_dir=output_dir.resolve(),
        organization=organization,
        sources_doc=sources_doc,
        components_doc=components_doc,
        assets_doc=assets_doc,
        route=route,
        check=check,
        errors=errors,
    )
    return ctx, spec


def compile_article(spec_path: Path, org_dir: Path, output_dir: Path, check: bool) -> dict[str, Any]:
    ctx, spec = load_context(spec_path, org_dir, output_dir, check)
    serialized = json.dumps(spec, ensure_ascii=False)
    markers = sorted(set(match.group(0) for match in PLACEHOLDERS.finditer(serialized)))
    if markers:
        ctx.errors.append(f"article contains placeholders: {', '.join(markers)}")
    blocks = spec.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        ctx.errors.append("article.blocks must be a non-empty array")
        blocks = []
    rendered = "".join(
        render_block(ctx, block, index)
        for index, block in enumerate(blocks)
        if isinstance(block, dict)
    )
    if len(rendered_blocks := [block for block in blocks if isinstance(block, dict)]) != len(blocks):
        ctx.errors.append("every article block must be an object")

    t = ctx.tokens
    fragment = (
        f'<section data-organization="{esc(ctx.organization.get("id", ""))}" '
        f'data-route="{esc(ctx.route.get("id", ""))}" '
        f'style="max-width:100%;margin:0 auto;background:{t["surface"]};font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;">'
        f"{rendered}</section>"
    )
    if UNSAFE_WECHAT.search(fragment):
        ctx.errors.append("wechat fragment contains an unsafe tag")
    max_chars = ctx.organization.get("publishing", {}).get("max_content_chars")
    if isinstance(max_chars, int) and len(fragment) > max_chars:
        ctx.errors.append(f"wechat fragment exceeds configured max_content_chars: {len(fragment)} > {max_chars}")

    preview = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(spec.get("title", "WeChat preview"))}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#e8e8e8}}main{{width:min(430px,100%);margin:24px auto;background:{t["surface"]};box-shadow:0 12px 42px rgba(0,0,0,.13)}}@media(max-width:480px){{main{{margin:0;box-shadow:none}}}}</style>
</head><body><main>{fragment}</main></body></html>'''

    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    (ctx.output_dir / "wechat.html").write_text(fragment, encoding="utf-8")
    (ctx.output_dir / "index.html").write_text(preview, encoding="utf-8")
    report = {
        "ok": not ctx.errors,
        "article": {
            "title": spec.get("title"),
            "organization_id": spec.get("organization_id"),
            "article_type": spec.get("article_type"),
            "route_id": ctx.route.get("id"),
            "route_layout": ctx.route.get("layout"),
        },
        "counts": {
            "blocks": len(rendered_blocks),
            "html_characters": len(fragment),
            "copied_assets": len(ctx.copied_assets),
        },
        "component_ids": list(dict.fromkeys(ctx.component_ids)),
        "source_ids": sorted(ctx.used_source_ids),
        "copied_assets": ctx.copied_assets,
        "warnings": list(dict.fromkeys(ctx.warnings)),
        "errors": list(dict.fromkeys(ctx.errors)),
        "outputs": {
            "preview": str((ctx.output_dir / "index.html").resolve()),
            "wechat": str((ctx.output_dir / "wechat.html").resolve()),
            "report": str((ctx.output_dir / "compile-report.json").resolve()),
        },
    }
    (ctx.output_dir / "compile-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path)
    parser.add_argument("--org", type=Path, required=True, help="Organization pack directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Exit non-zero when final QA fails")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = compile_article(args.article, args.org, args.output, args.check)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.check and not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
