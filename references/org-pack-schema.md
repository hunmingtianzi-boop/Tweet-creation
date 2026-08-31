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

New packs also declare the public generated-image watermark policy under
`provenance`. `key_id` names an external key without containing it:

```json
{
  "generated_image_watermark": {
    "mode": "required",
    "scheme": "org-wechat-dct-v1",
    "key_id": "external"
  }
}
```

`mode` is `required` or `optional`. `key_id` is a lowercase hyphenated public
lookup slug of at most 64 characters; it must not resemble key material. The
embed/detect secret and raw watermark-ID
registry never belong in this file or anywhere else in the organization pack.

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

Routes use a layout family from `editorial`, `poster`, `technical`, `institutional`, or `warm-community`. These are compositional behaviors, not fixed brands. A route may additionally carry a reviewed `style_grammar` when provenance uses `explicit-style-grammar`; this selection is route-local, so sibling routes without it remain source-zero.

`publishing.interaction_policy` stores only the portable expectation: default static payload, policy version `wechat-svg-smil-self-v1`, candidate modes `svg-smil-self` / `horizontal-swipe`, and the requirement for a static equivalent. It must not contain an account certification. Sanitizer readback, probe draft IDs, iOS/Android versions, screenshots, validity windows, access tokens, and `thumb_media_id` values belong to the target account's delivery environment and must be rebuilt for every公众号.

`visual.calibration` records `status`, `approved_routes`, a benchmark with Ardot `file_url`, `page_name`, and `article_node_id`, plus review metadata. Approval also requires a generated `background_family` with `id`, `strategy: generated-family`, `master_asset_id`, 1–3 `companion_asset_ids`, one `surface_mode`, a normalized `copy_safe_zone`, `body_text_color`, `minimum_contrast_ratio >= 4.5`, and `maximum_copy_safe_stddev <= 0.12` (recommended `0.10`). All referenced files must be local, final opaque PNGs so validation can inspect actual pixels, family luminance/color distance, opposite-tone blocks, copy-zone variance, and copy contrast before article layout begins. Its `typography` object selects `expressive-native` or `restrained-native`, requires editable licensed/system-font text and standard body copy, lists approved treatments, and sets a 2–4 moment ceiling. `expressive-native` additionally requires at least two `approved_recipes`; each recipe has a slug ID, approved treatment, at least two allowed non-font techniques, `minimum_editable_layers >= 2`, and a fallback style. New organizations start at `not-started`; full-article production remains blocked until the chosen route, pixel-checked family, and typography recipes are approved. See [visual-calibration.md](visual-calibration.md) and [expressive-typography.md](expressive-typography.md).

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

Each asset has an ID, kind, title, path or URL, style, uses, origin, and optional source ID. Local paths resolve relative to the organization pack. Real evidence photos declare `visual_role: documentary-evidence` and a `source_id`. Generated backgrounds declare `visual_role: illustrative-atmosphere`, `background_family_id`, and `background_variant` (`master` or `companion`). Generated micro illustrations declare `visual_role: article-micro`, exactly one of the four `roles`, the current slug in `generated_for_articles`, and stored P0 cutout quality metadata: `alpha_verified`, `cutout_verified`, exact SHA/dimensions, and robust bbox/padding/matte evidence. Confirmed packs re-run the pixel gate and reject stale evidence.

An eligible opaque `generated-illustrative` background or fully generated
raster cover is registered from its marked final derivative and carries only
public evidence:

```json
{
  "watermark": {
    "scheme": "org-wechat-dct-v1",
    "payload_fingerprint": "<64 lowercase hex characters>",
    "key_id": "external",
    "key_epoch": 1,
    "source_location": "assets/generated/background-raw.png",
    "source_sha256": "<sha256>",
    "marked_sha256": "<sha256>",
    "local_verified": true,
    "report_location": "assets/derived/background-watermark.json",
    "report_sha256": "<sha256>",
    "psnr_db": 44.37,
    "psnr_threshold_db": 42.0
  }
}
```

Both paths remain inside the pack; the source and final files are distinct.
The source normally lives under the Git-ignored
`assets/generated/unwatermarked-masters/` directory and must be restored from
the organization's private asset store on a new machine. Validation rehashes
both images and the report, independently recalculates PSNR, authenticates the
current final pixels with the external key, and independently reruns the
complete-frame 390px/JPEG-Q75 simulation. It does not trust copied report
numbers or an `authenticated: true` field. Photographs, official/user images, logos, QR
codes, transparent `article-micro` files, SVG/SMIL, remote images, and QA
evidence are outside V1 and stay byte-identical. See
[provenance-watermark.md](provenance-watermark.md).

Allowed origins include `user-supplied`, `official`, `photographed`, `generated-illustrative`, and `derived`. A `logo` or `qr` asset must be `user-supplied` or `official`; otherwise validation fails.

Do not store account secrets, access tokens, watermark keys, raw watermark IDs,
private watermark registries, or other private credentials in an organization
pack.

Generate an article-type asset plan with `scripts/orgs.py asset-plan`, then register approved files with `scripts/orgs.py register-asset`. For a newly generated micro illustration, pass `--role ROLE --generated-for ARTICLE_ID --visual-role article-micro`; registration requires deterministically decodable 8-bit RGBA, robust Alpha geometry, a tight subject crop, no clipped substantive pixels, and no rectangular/rounded/near-solid matte. Spacing belongs in Ardot, not in a large transparent PNG canvas. Every article gets a fresh visual-kit plan and must produce four different assets for all four roles before layout. Logos and QR codes always remain official or user-supplied assets.

## Visual-reference provenance

The default mode is source-zero. `organization.provenance` declares `visual_reference_policy: source-zero`, current `visual_input_source_ids`, `isolation_reviewed_at`, and all four excluded kinds: `prior-article-layout`, `prior-ardot-file`, `prior-article-screenshot`, `other-organization-visual-pack`. These fields make the isolation claim executable instead of leaving it in notes.

When the user explicitly selects a reviewed style grammar, provenance may instead use `visual_reference_policy: explicit-style-grammar`. It additionally requires:

- non-empty `style_reference_source_ids` that also appear in `provenance.source_ids` and `sources.json`;
- `style_reference_scope: abstract-visual-grammar-only`;
- ISO `reference_reviewed_at`;
- every `style_reference_non_copy_constraints` value: `text`, `photographs`, `logos`, `specific-layout`, `component-geometry`, `artwork`;
- at least one route with a valid `style_grammar`.

The route grammar accepts only nine abstract tokens: `color_motion`, `saturation`, `material`, `lighting`, `layering`, `edge_energy`, `copy_safe_zone`, `photo_responsibility`, and `background_responsibility`. It repeats the six non-copy constraints and stores a canonical lowercase SHA-256 over normalized `tokens + non_copy_constraints`. Optional `preset_id` and `label` are discovery metadata and are not hashed. When `preset_id` is present it must resolve to `style-presets/<preset-id>.json`, whose canonical grammar SHA must equal the route SHA; an unknown preset or a modified-and-resigned route fails. Reference content-shaped fields, URLs, and explicit copy/replicate/verbatim instructions are rejected.

For a later organization, register the reviewed preset JSON itself as the style source and do not reopen the original reference. See [style-options.md](style-options.md).
