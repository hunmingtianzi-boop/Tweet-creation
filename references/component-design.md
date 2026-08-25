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

- Use no more than two boxed components in sequence.
- Give each long article at least one image-led moment and one full-width color or type transition.
- Alternate layout families: open text, image, numbered process, evidence, action.
- A hero is one visual moment. Keep the title, short subtitle, optional eyebrow, and at most one action label.
- Use cards only when items are independently comparable. Use rails, bands, whitespace, or one continuous path for sequences.
- Real people, events, facilities, projects, and outcomes use real or officially supplied photography. Generated images are illustrative brand assets only.

## Image slots

- Hero background: 2:3 portrait, subject weighted to one side, large title-safe zone.
- Section opener: 3:2 landscape, one clear subject, no embedded copy.
- Gallery: consistent photographic treatment; do not mix generated illustration with documentary evidence in one gallery.
- Case evidence: real output, process, prototype, or event record; never a generic decorative image.

## Visual QA

Build an Ardot manifest and create a native component gallery before approving a new organization route:

```bash
python3 scripts/build_ardot_manifest.py article.json \
  --org organizations/ORG_ID \
  --output output/ORG_ID/article/ardot-manifest.json
```

Inspect high-impact sections with Ardot screenshots at 390 px. Confirm that route families differ in composition, not only color, and that no three consecutive sections repeat the same container pattern. Keep the gallery and example article editable as native components and instances.
