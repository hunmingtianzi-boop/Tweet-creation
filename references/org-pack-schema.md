# Organization pack schema

An organization pack is a reusable directory containing five JSON files:

```text
organization-pack/
├── organization.json
├── sources.json
├── components.json
├── assets.json
├── ardot.json
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
- `visual`: tokens, motifs, avoid rules, routes, default route, and screenshot-backed route calibration metadata.
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

`visual.calibration` records `status`, `approved_routes`, a benchmark with Ardot `file_url`, `page_name`, and `article_node_id`, plus review metadata. Approval also requires a generated `background_family` with `id`, `strategy: generated-family`, `master_asset_id`, 1–3 `companion_asset_ids`, and `copy_safe_zone`. Its `typography` object selects `expressive-native` or `restrained-native`, requires editable licensed/system-font text and standard body copy, lists approved treatments, and sets a 2–4 moment ceiling. New organizations start at `not-started`; full-article production remains blocked until the chosen route, family, and typography strategy are approved. See [visual-calibration.md](visual-calibration.md) and [expressive-typography.md](expressive-typography.md).

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

## `ardot.json`

Connects the portable organization pack to its editable visual system. It records:

- link status and Ardot design-file URL/ID;
- semantic variable set and organization mode;
- foundation, component, and example page names;
- exact native component aliases for route variants.

New packs start as `not-linked`. Set `linked` only after a real Ardot file, variable mode, and first visual calibration exist. This file contains no account secret.

## `assets.json`

Each asset has an ID, kind, title, path or URL, style, uses, origin, and optional source ID. Local paths resolve relative to the organization pack. Real evidence photos declare `visual_role: documentary-evidence` and a `source_id`. Generated backgrounds declare `visual_role: illustrative-atmosphere`, `background_family_id`, and `background_variant` (`master` or `companion`). Generated micro illustrations declare `visual_role: article-micro`, exactly one of the four `roles`, the current slug in `generated_for_articles`, and stored Alpha quality metadata.

Allowed origins include `user-supplied`, `official`, `photographed`, `generated-illustrative`, and `derived`. A `logo` or `qr` asset must be `user-supplied` or `official`; otherwise validation fails.

Do not store account secrets, access tokens, or private credentials in an organization pack.

Generate an article-type asset plan with `scripts/orgs.py asset-plan`, then register approved files with `scripts/orgs.py register-asset`. For a newly generated micro illustration, pass `--role ROLE --generated-for ARTICLE_ID --visual-role article-micro`; registration runs the pixel Alpha/aspect check. Every article gets a fresh visual-kit plan and must produce four different assets for all four roles before layout. Logos and QR codes always remain official or user-supplied assets.

## Source-zero provenance

`organization.provenance` must declare `visual_reference_policy: source-zero`, current `visual_input_source_ids`, `isolation_reviewed_at`, and all four excluded kinds: `prior-article-layout`, `prior-ardot-file`, `prior-article-screenshot`, `other-organization-visual-pack`. These fields make the isolation claim executable instead of leaving it in notes.
