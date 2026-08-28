#!/usr/bin/env python3
"""Build a controlled A/B WeChat article experiment from one immutable input."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(__file__).resolve().parent
DEFAULT_CONTENT = EXPERIMENT / "content.json"
PALETTE = {
    "paper": "#F3F0E7",
    "paper2": "#E9E4D8",
    "ink": "#173A3B",
    "body": "#345253",
    "teal": "#1F6B66",
    "mint": "#BFD8C9",
    "coral": "#EA765C",
    "sun": "#F1C85B",
    "white": "#FFFEFA",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def content_digest(content: dict) -> str:
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def inline_style(**items: str) -> str:
    return ";".join(f"{key.replace('_', '-')}:{value}" for key, value in items.items())


def copy_assets(content: dict, variant_dir: Path) -> list[dict[str, str]]:
    assets_dir = variant_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for item in content["moments"]:
        source = ROOT / item["image"]
        target = assets_dir / source.name
        shutil.copy2(source, target)
        records.append({"source": item["image"], "output": f"assets/{target.name}"})
    return records


def title_art(content: dict) -> str:
    a, b = content["display_title"]
    return f'''<section data-component="hero.editorial" style="position:relative;overflow:hidden;padding:34px 22px 28px;background:{PALETTE['paper']};color:{PALETTE['ink']};">
  <div aria-hidden="true" style="position:absolute;right:-38px;top:-42px;width:164px;height:164px;border:24px solid {PALETTE['mint']};border-radius:50%;opacity:.7;"></div>
  <div aria-hidden="true" style="position:absolute;left:-24px;bottom:16px;width:118px;height:9px;background:{PALETTE['coral']};transform:rotate(-8deg);"></div>
  <p style="position:relative;margin:0 0 28px;font-size:10px;font-weight:800;letter-spacing:.19em;color:{PALETTE['teal']};">{esc(content['eyebrow'])}</p>
  <div style="position:relative;margin:0;line-height:.88;letter-spacing:-.065em;color:{PALETTE['ink']};">
    <div style="font-size:52px;font-weight:950;transform:rotate(-2deg);transform-origin:left center;">{esc(a)}</div>
    <div style="display:inline-block;margin:8px 0 0 40px;padding:2px 8px 7px;font-size:48px;font-weight:950;background:{PALETTE['sun']};transform:rotate(1.5deg);">{esc(b)}</div>
  </div>
  <p style="position:relative;margin:24px 0 0 2px;font-size:18px;font-weight:800;letter-spacing:.02em;">{esc(content['subtitle'])}</p>
</section>'''


def lead(content: dict) -> str:
    return f'''<section data-component="lead.open" style="padding:30px 22px 18px;background:{PALETTE['paper']};">
  <p style="margin:0;font-size:18px;line-height:1.68;font-weight:650;letter-spacing:-.015em;color:{PALETTE['ink']};">{esc(content['lead'])}</p>
  <div style="margin:25px 0 0;padding:2px 0 2px 16px;border-left:5px solid {PALETTE['coral']};font-size:14px;line-height:1.68;color:{PALETTE['body']};">{esc(content['thesis'])}</div>
</section>'''


def static_path(content: dict) -> str:
    rows = []
    for i, item in enumerate(content["ecosystem"]):
        color = PALETTE["coral"] if i % 2 == 0 else PALETTE["teal"]
        rows.append(f'''<div style="display:grid;grid-template-columns:48px 1fr;gap:13px;padding:17px 0;border-top:1px solid rgba(31,107,102,.25);">
  <div style="font-size:25px;font-weight:950;letter-spacing:-.06em;color:{color};">{esc(item['index'])}</div>
  <div><div style="font-size:11px;font-weight:850;letter-spacing:.13em;color:{color};">{esc(item['label'])}</div>
  <div style="margin-top:3px;font-size:21px;font-weight:900;color:{PALETTE['ink']};">{esc(item['name'])}</div>
  <div style="margin-top:5px;font-size:14px;line-height:1.62;color:{PALETTE['body']};">{esc(item['summary'])}</div></div>
</div>''')
    return f'''<section data-component="ecosystem.static-path" style="padding:25px 22px 16px;background:{PALETTE['paper']};">
  <div style="margin-bottom:16px;font-size:11px;font-weight:850;letter-spacing:.16em;color:{PALETTE['teal']};">一条持续向前的路径</div>
  {''.join(rows)}
</section>'''


def interactive_path(content: dict) -> str:
    cards = []
    for i, item in enumerate(content["ecosystem"]):
        color = PALETTE["coral"] if i % 2 == 0 else PALETTE["teal"]
        cards.append(f'''<details data-interaction="tap-reveal" style="min-width:78%;scroll-snap-align:start;padding:0;background:{PALETTE['white']};border-top:7px solid {color};box-shadow:0 9px 22px rgba(23,58,59,.09);">
  <summary style="cursor:pointer;list-style:none;padding:18px 18px 16px;color:{PALETTE['ink']};">
    <span style="display:block;font-size:30px;font-weight:950;letter-spacing:-.06em;color:{color};">{esc(item['index'])}</span>
    <span style="display:block;margin-top:16px;font-size:11px;font-weight:850;letter-spacing:.13em;color:{color};">{esc(item['label'])}</span>
    <span style="display:block;margin-top:3px;font-size:22px;font-weight:900;">{esc(item['name'])}</span>
    <span style="display:block;margin-top:12px;font-size:12px;font-weight:800;color:{color};">轻触展开 ↓</span>
  </summary>
  <div style="padding:0 18px 18px;font-size:14px;line-height:1.62;color:{PALETTE['body']};">{esc(item['summary'])}</div>
</details>''')
    return f'''<section data-component="ecosystem.tap-reveal-rail" style="padding:25px 0 22px;background:{PALETTE['paper']};">
  <div style="padding:0 22px 15px;"><div style="font-size:11px;font-weight:850;letter-spacing:.16em;color:{PALETTE['teal']};">向左滑动 · 轻触展开</div></div>
  <div data-interaction="horizontal-swipe" style="display:flex;gap:13px;overflow-x:auto;scroll-snap-type:x mandatory;padding:0 22px 14px;overscroll-behavior-x:contain;">{''.join(cards)}</div>
  <div aria-hidden="true" style="margin:0 22px;height:3px;background:linear-gradient(90deg,{PALETTE['coral']} 0 28%,{PALETTE['mint']} 28% 100%);"></div>
</section>'''


def bridge(content: dict) -> str:
    return f'''<section data-component="bridge.editorial" style="position:relative;padding:27px 22px 30px;background:{PALETTE['paper2']};">
  <div aria-hidden="true" style="position:absolute;right:18px;top:18px;font-size:54px;font-weight:950;color:{PALETTE['mint']};line-height:1;">×</div>
  <h2 style="position:relative;margin:0;width:78%;font-size:27px;line-height:1.08;letter-spacing:-.04em;color:{PALETTE['ink']};">{esc(content['bridge_title'])}</h2>
  <p style="position:relative;margin:18px 0 0;font-size:15px;line-height:1.72;color:{PALETTE['body']};">{esc(content['bridge_body'])}</p>
</section>'''


def static_moments(content: dict) -> str:
    figures = []
    for item in content["moments"]:
        figures.append(f'''<figure style="margin:0 0 15px;">
  <img src="assets/{esc(Path(item['image']).name)}" alt="{esc(item['alt'])}" style="display:block;width:100%;height:auto;">
  <figcaption style="padding:8px 2px 0;font-size:12px;line-height:1.5;color:{PALETTE['body']};">{esc(item['caption'])}</figcaption>
</figure>''')
    return f'''<section data-component="moments.static-stack" style="padding:29px 22px 16px;background:{PALETTE['paper']};">
  <h2 style="margin:0 0 18px;font-size:27px;letter-spacing:-.04em;color:{PALETTE['ink']};">现场，才是能力发生的地方</h2>
  {''.join(figures)}
</section>'''


def interactive_moments(content: dict) -> str:
    figures = []
    for item in content["moments"]:
        figures.append(f'''<figure style="min-width:86%;margin:0;scroll-snap-align:center;background:{PALETTE['white']};">
  <img src="assets/{esc(Path(item['image']).name)}" alt="{esc(item['alt'])}" style="display:block;width:100%;aspect-ratio:3/2;object-fit:cover;">
  <figcaption style="padding:12px 14px 14px;font-size:13px;line-height:1.5;color:{PALETTE['body']};">{esc(item['caption'])}</figcaption>
</figure>''')
    return f'''<section data-component="moments.swipe-story" style="padding:29px 0 20px;background:{PALETTE['paper']};">
  <div style="padding:0 22px;"><h2 style="margin:0;font-size:27px;letter-spacing:-.04em;color:{PALETTE['ink']};">现场，才是能力发生的地方</h2><p style="margin:8px 0 16px;font-size:12px;font-weight:800;color:{PALETTE['coral']};">左右滑动查看 3 个真实片段 →</p></div>
  <div data-interaction="horizontal-swipe" style="display:flex;gap:13px;overflow-x:auto;scroll-snap-type:x mandatory;padding:0 22px 14px;">{''.join(figures)}</div>
</section>'''


def metrics(content: dict) -> str:
    cells = []
    for item in content["metrics"]:
        cells.append(f'''<div style="flex:1;min-width:0;padding:16px 7px;border-top:4px solid {PALETTE['sun']};">
  <div style="font-size:25px;font-weight:950;letter-spacing:-.05em;color:{PALETTE['ink']};">{esc(item['value'])}</div>
  <div style="margin-top:5px;font-size:11px;line-height:1.45;color:{PALETTE['body']};">{esc(item['label'])}</div>
</div>''')
    return f'''<section data-component="metrics.open-ledger" style="padding:20px 22px 28px;background:{PALETTE['paper']};">
  <div style="display:flex;gap:12px;">{''.join(cells)}</div>
</section>'''


def closing(content: dict) -> str:
    return f'''<section data-component="closing.action" style="position:relative;overflow:hidden;padding:33px 22px 38px;background:{PALETTE['teal']};color:{PALETTE['white']};">
  <div aria-hidden="true" style="position:absolute;right:-18px;bottom:-25px;width:110px;height:110px;border:18px solid {PALETTE['sun']};border-radius:50%;"></div>
  <h2 style="position:relative;margin:0;width:82%;font-size:29px;line-height:1.08;letter-spacing:-.045em;">{esc(content['closing_title'])}</h2>
  <p style="position:relative;margin:18px 0 0;width:88%;font-size:15px;line-height:1.72;color:#E7F1EB;">{esc(content['closing_body'])}</p>
  <p style="position:relative;margin:24px 0 0;padding-top:13px;border-top:1px solid rgba(255,255,255,.35);font-size:13px;font-weight:850;color:{PALETTE['sun']};">{esc(content['cta'])}</p>
</section>'''


def article_fragment(content: dict, variant: str) -> str:
    interactive = variant == "b-dynamic"
    parts = [
        title_art(content),
        lead(content),
        interactive_path(content) if interactive else static_path(content),
        bridge(content),
        interactive_moments(content) if interactive else static_moments(content),
        metrics(content),
        closing(content),
    ]
    return f'<article data-experiment="{esc(content["experiment_id"])}" data-variant="{variant}" style="width:100%;max-width:390px;margin:0 auto;background:{PALETTE["paper"]};">' + "".join(parts) + "</article>"


def preview_document(fragment: str, label: str, digest: str) -> str:
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(label)}</title><style>
*{{box-sizing:border-box}}body{{margin:0;padding:28px 12px 64px;background:#D8D5CC;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC",sans-serif}}article{{box-shadow:0 18px 60px rgba(23,58,59,.18)}}summary::-webkit-details-marker{{display:none}}[data-interaction="horizontal-swipe"]::-webkit-scrollbar{{height:4px}}[data-interaction="horizontal-swipe"]::-webkit-scrollbar-thumb{{background:{PALETTE['coral']}}}
</style></head><body><div style="max-width:390px;margin:0 auto 10px;font:700 11px/1.4 ui-monospace,monospace;color:#51605e;">{esc(label)} · INPUT {digest[:10]}</div>{fragment}</body></html>'''


def build(content_path: Path = DEFAULT_CONTENT, output_root: Path | None = None) -> dict:
    content = json.loads(content_path.read_text(encoding="utf-8"))
    digest = content_digest(content)
    output_root = output_root or EXPERIMENT / "output"
    records = {}
    for variant, label in (("a-baseline", "A · 现有基线 workflow"), ("b-dynamic", "B · 动态组件 workflow")):
        variant_dir = output_root / variant
        variant_dir.mkdir(parents=True, exist_ok=True)
        assets = copy_assets(content, variant_dir)
        fragment = article_fragment(content, variant)
        (variant_dir / "wechat.html").write_text(fragment, encoding="utf-8")
        (variant_dir / "index.html").write_text(preview_document(fragment, label, digest), encoding="utf-8")
        if variant == "b-dynamic":
            fallback = article_fragment(content, "a-baseline").replace('data-variant="a-baseline"', 'data-variant="b-dynamic-fallback"')
            (variant_dir / "wechat-fallback.html").write_text(fallback, encoding="utf-8")
        records[variant] = {
            "label": label,
            "input_sha256": digest,
            "wechat_sha256": hashlib.sha256(fragment.encode("utf-8")).hexdigest(),
            "assets": assets,
            "interactions": [] if variant == "a-baseline" else ["tap-reveal", "horizontal-swipe"],
        }
    comparison = {
        "experiment_id": content["experiment_id"],
        "controlled_variables": ["content.json", "copy order", "photo set", "color tokens", "typography", "article width"],
        "independent_variable": "interaction rendering strategy",
        "variants": records,
        "parity_passed": records["a-baseline"]["input_sha256"] == records["b-dynamic"]["input_sha256"],
    }
    (output_root / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    a = "a-baseline/index.html"
    b = "b-dynamic/index.html"
    dashboard = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>A/B 公众号工作流实验</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#182f30;color:#fff;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}header{{padding:18px 24px}}h1{{margin:0;font-size:21px}}p{{margin:6px 0 0;font-size:12px;color:#bdd0c8}}main{{display:grid;grid-template-columns:1fr 1fr;gap:2px;height:calc(100vh - 76px)}}section{{min-width:0;background:#d8d5cc}}iframe{{width:100%;height:100%;border:0}}@media(max-width:850px){{main{{grid-template-columns:1fr;height:auto}}iframe{{height:820px}}}}</style></head><body><header><h1>同一输入 A/B 对比</h1><p>唯一变量：B 版加入轻触展开与横向滑动；input sha256 {digest[:12]}</p></header><main><section><iframe src="{a}" title="A 基线版"></iframe></section><section><iframe src="{b}" title="B 动态版"></iframe></section></main></body></html>'''
    (output_root / "compare.html").write_text(dashboard, encoding="utf-8")
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    comparison = build(args.content, args.output)
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
