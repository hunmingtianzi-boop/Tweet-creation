# Organization pack schema

An organization pack is a reusable directory containing four JSON files:

```text
organization-pack/
├── organization.json
├── sources.json
├── components.json
├── assets.json
└── assets/
    ├── official/       # Logo, QR, official identity files
    ├── photos/         # Real people, events, projects, venues
    ├── generated/      # Approved illustrative bitmaps
    └── derived/        # Crops, compressed copies, background removal
```

Run `python3 scripts/orgs.py validate PACK_DIR` after every material edit.

## `organization.json`

Required top-level fields:

- `schema_version`: currently `1`.
- `id`: lowercase slug shared by every registry.
- `status`: `provisional`, `confirmed`, or `migrated-draft`.
- `identity`: name, short name, summary, category, audiences, content pillars.
- `personality`: numeric `authority`, `technical`, `warmth`, `experimental`, and `action` values from 0 to 100.
- `voice`: traits, headline patterns, preferred terms, and avoid terms.
- `visual`: tokens, motifs, avoid rules, routes, and default route.
- `article_types`: mapping of stable article-type IDs to route and block recommendations.
- `asset_policy`: logo, QR, photography, and image-generation boundaries.
- `publishing`: authoring and draft/publication policy.
- `provenance`: source IDs and review metadata.

Required visual tokens:

```json
{
  "ink": "#111111",
  "body": "#4A4A4A",
  "accent": "#1F5EFF",
  "accent_alt": "#FFD84D",
  "surface": "#FFFFFF",
  "surface_alt": "#F4F2EC",
  "border": "#111111",
  "white": "#FFFFFF"
}
```

Routes use a layout family from `editorial`, `poster`, `technical`, `institutional`, or `warm-community`. These are compositional behaviors, not fixed brands.

## `sources.json`

Contains `sources` and normalized `facts`.

- Each source has a stable ID, title, kind, locator, and optional access date/notes.
- Each fact has a stable ID, concise claim, one or more `source_ids`, confidence (`verified`, `reported`, or `provisional`), and optional last-checked date.
- Metrics, eligibility conditions, partner claims, and attributed quotes should resolve to fact/source IDs rather than relying on memory.

## `components.json`

Contains reusable semantic components and article-type recommendations. A component needs an ID, kind, title, and optional uses/variant. Keep organization-specific styling in `organization.json`; component IDs describe meaning, not color.

Recommended stable core IDs include:

- `core.hero`, `core.lead`, `core.section`, `core.text`;
- `core.statement`, `core.metrics`, `core.timeline`;
- `core.gallery`, `core.case`, `core.roles`, `core.quote`;
- `core.steps`, `core.image`, `core.cta`, `core.references`, `core.footer`.

Organization packs may add custom IDs without changing the compiler when they map to a supported semantic block type.

## `assets.json`

Each asset has an ID, kind, title, path or URL, style, uses, origin, and optional source ID. Local paths resolve relative to the organization pack.

Allowed origins include `user-supplied`, `official`, `photographed`, `generated-illustrative`, and `derived`. A `logo` or `qr` asset must be `user-supplied` or `official`; otherwise validation fails.

Do not store account secrets, access tokens, or private credentials in an organization pack.

Generate an article-type asset plan with `scripts/orgs.py asset-plan`, then register approved files with `scripts/orgs.py register-asset`. The plan may recommend generated illustrations, but logos and QR codes always remain official or user-supplied assets.
