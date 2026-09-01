# Component design and article rhythm

The semantic block type describes the content job. The visual route decides how that job looks. Do not create a new block type only to change color, border radius, or decoration.

## Route families

The compiler provides four route-aware component families:

- `warm-community`: soft editorial layering, human scale, generous breathing room, image-led moments, and warm participation cues.
- `technical`: precise rails, visible process, strong information hierarchy, and restrained engineering surfaces.
- `poster`: high-contrast fields, oversized action copy, hard crops, and compact event information.
- `institutional`: calm editorial spacing, verified evidence, fine rules, and formal hierarchy.

Each route may override defaults with `component_variants`:

```json
{
  "layout": "technical",
  "component_variants": {
    "hero": "image-stage",
    "section": "index-rail",
    "metrics": "number-field",
    "case": "process-strip",
    "cta": "action-gate"
  }
}
```

An individual article block may set `variant` when one deliberate exception is needed. Prefer route defaults so a whole article stays coherent.

## Rhythm rules

- Read [organic-layout.md](organic-layout.md) before building or revising a long article.
- Generate and componentize the article-specific micro-illustration kit before any long-article layout.
- Closed boxes may occupy at most 20% of content sections and may never appear consecutively.
- Give each long article at least one image-led moment and one full-width color or type transition.
- Alternate layout families: open text, floating illustration, image, continuous path, evidence, action, quiet whitespace.
- A hero is one visual moment. Keep the title, short subtitle, optional eyebrow, and at most one action label.
- Give an expressive route 2–4 native display-type moments across hero, chapter, statement, key phrase, or CTA roles. Change scale, weight, stacking, baseline, or native outline treatment; do not turn headings into generated bitmaps. Keep body typography standard. See [expressive-typography.md](expressive-typography.md).
- Use cards only when items are independently comparable. A semantic block does not automatically deserve its own background, border, radius, or shadow. Use rails, bands, whitespace, asymmetric illustration placement, or one continuous path for sequences.
- Real people, events, facilities, projects, and outcomes use real or officially supplied photography. Generated images are illustrative brand assets only.

## Micro-component geometry

Treat a micro component as an editorial accent that enters the reading flow, not as a self-contained poster:

- no raster/illustration layer may exceed `0.72` of the 390 px row;
- the complete native group may not exceed `0.82` of the row;
- the four mandatory roles must appear across at least three reviewed sections, use both left and right offsets, at least three distinct offsets, at least three composition relations, and visibly different scales;
- use `text-edge-entry`, `between-paragraphs`, `continuous-path`, `chapter-bridge`, and `cta-anchor` as placement relationships rather than centering every item in its own horizontal band;
- never flatten the illustration and its copy into one image.

If a native micro component carries copy, emphasize the primary phrase with scale and typography—not a container. The primary phrase is at least `22 px` and `1.35×` local body text, remains an editable Ardot text node, and combines `scale-contrast` with at least one of mixed weight, color contrast, intentional line break, baseline offset, or a vector accent. A border, filled rectangle, rounded chip, badge, or closed shape around the words is a blocking defect. Glyph outline/offset treatments are allowed only when they follow letterforms rather than enclosing the text block.

## Interaction rhythm

- 常规文章默认 2–3 个 semantic interaction modules；2 个分布在 `early` + `middle`，3 个再增加 `late`，每个属于不同 storyboard chapter。
- 一个 module 是一个连续版面区域与一个读者任务。四张部门揭开卡是一个 module、四个 transport instances；照片横滑组整体是一个 module。
- 每个 module 必须解决按需展开、顺序/并列浏览或逐步解释中的一种。纯装饰运动、文章专属微插图和表现型字体不计数。
- module 内可以组合 `svg-smil-self` 与 `horizontal-swipe`，但每个实际 instance 都有独立 fallback key/hash 和静态等价内容。
- 交互不豁免开放式构图、20% 方框比例与禁止连续盒子的规则。不要把 2–3 个 module 排成相邻组件墙。
- 原文只有 0–1 个合理机会时，记录 user/editor-confirmed `static-exception`；不得拆分同一区域、重复文案或隐藏必要事实来凑数。

详见 [interaction-composition.md](interaction-composition.md)。

## Image slots

- Mandatory micro kit: floating spot, section transition, inline explainer, and closing motif; four different article-specific generated assets, each with verified Alpha and a native Ardot component node.
- Hero background: 2:3 portrait, subject weighted to one side, large title-safe zone.
- Section opener: 3:2 landscape, one clear subject, no embedded copy.
- Gallery: consistent photographic treatment; do not mix generated illustration with documentary evidence in one gallery.
- Case evidence: real output, process, prototype, or event record; never a generic decorative image.

## Visual QA

Build and approve the article-specific visual kit before the Ardot manifest and native component gallery:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_kit.py" article.json \
  --org organizations/ORG_ID \
  --output output/ORG_ID/article/visual-kit-plan.json
```

Only after `ready_for_layout: true`:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_ardot_manifest.py" article.json \
  --org organizations/ORG_ID \
  --output output/ORG_ID/article/ardot-manifest.json
```

Inspect high-impact sections with Ardot screenshots at 390 px. Confirm that route families differ in composition, not only color; boxes do not exceed 20%; no two boxes are consecutive; at least three moments visibly break symmetry or the text edge; micro components remain partial-width and staggered; copy-bearing micro components are unframed with enlarged native type; and expressive type is selective, editable, and legible. Record five distinct Ardot nodes and all required checks plus the measured schema-v3 micro-component placements in the separate screenshot-backed visual review. Keep the gallery and example article editable as native components and instances.
