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

## Image slots

- Mandatory micro kit: floating spot, section transition, inline explainer, and closing motif; four different article-specific generated assets, each with verified Alpha and a native Ardot component node.
- Hero background: 2:3 portrait, subject weighted to one side, large title-safe zone.
- Section opener: 3:2 landscape, one clear subject, no embedded copy.
- Gallery: consistent photographic treatment; do not mix generated illustration with documentary evidence in one gallery.
- Case evidence: real output, process, prototype, or event record; never a generic decorative image.

## Visual QA

Build and approve the article-specific visual kit before the Ardot manifest and native component gallery:

```bash
python3 scripts/build_visual_kit.py article.json \
  --org organizations/ORG_ID \
  --output output/ORG_ID/article/visual-kit-plan.json
```

Only after `ready_for_layout: true`:

```bash
python3 scripts/build_ardot_manifest.py article.json \
  --org organizations/ORG_ID \
  --output output/ORG_ID/article/ardot-manifest.json
```

Inspect high-impact sections with Ardot screenshots at 390 px. Confirm that route families differ in composition, not only color; boxes do not exceed 20%; no two boxes are consecutive; at least three moments visibly break symmetry or the text edge; and expressive type is selective, editable, and legible. Record five distinct Ardot nodes and all required checks in the separate screenshot-backed visual review. Keep the gallery and example article editable as native components and instances.
