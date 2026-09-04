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
    ├── generated/      # Provider originals and approved opaque illustrative bitmaps
    └── derived/        # Hash-bound crops, compressed copies, and RGBA cutouts
```

Run `python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" "$ORG_WECHAT_RUNTIME_ROOT/scripts/orgs.py" validate PACK_DIR` after every material edit.

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

`visual.calibration` records `status`, `approved_routes`, a benchmark with Ardot `file_url`, `page_name`, and `article_node_id`, plus review metadata. Generated raster backgrounds are optional. When the startup choice is `generate_backgrounds: true`, calibration must include a generated `background_family` with `id`, `strategy: generated-family`, `master_asset_id`, 1–3 `companion_asset_ids`, one `surface_mode`, a normalized `copy_safe_zone`, `body_text_color`, `minimum_contrast_ratio >= 4.5`, and `maximum_copy_safe_stddev <= 0.12` (recommended `0.10`). All referenced files must be local, final opaque PNGs so validation can inspect actual pixels, family luminance/color distance, opposite-tone blocks, copy-zone variance, and copy contrast before article layout begins. When the choice is false, omit `background_family` and calibrate a continuous Ardot-native surface using fills, gradients, and open editable vectors; do not create raster atmosphere assets. Its `typography` object selects `expressive-native` or `restrained-native`, requires editable licensed/system-font text and standard body copy, lists approved treatments, and sets a 2–4 moment ceiling. `expressive-native` additionally requires at least two `approved_recipes`; each recipe has a slug ID, approved treatment, at least two allowed non-font techniques, `minimum_editable_layers >= 2`, and a fallback style. New organizations start at `not-started`; full-article production remains blocked until the chosen route and typography recipes are approved, plus the pixel-checked family when generated backgrounds were selected. See [visual-calibration.md](visual-calibration.md) and [expressive-typography.md](expressive-typography.md).

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

Each asset has an ID, kind, title, path or URL, style, uses, origin, and optional source ID. Local paths resolve relative to the organization pack. Real evidence photos declare `visual_role: documentary-evidence` and a `source_id`. Generated backgrounds declare `visual_role: illustrative-atmosphere`, `background_family_id`, and `background_variant` (`master` or `companion`). A newly registered micro illustration is the **derived RGBA result**, not the provider original: it declares `origin: derived`, `visual_role: article-micro`, exactly one role from the four-role catalog, the current slug in `generated_for_articles`, a validated `cutout` lineage object, and stored P0 quality metadata (`alpha_verified`, `cutout_verified`, exact SHA/dimensions, and robust bbox/padding/matte evidence). Confirmed packs re-hash the lineage files, re-run the pixel gate, and reject stale evidence.

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
    "original_source_location": "assets/generated/background-raw.png",
    "original_source_sha256": "<sha256>",
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
For an oversized source, `source_location` is the deterministic embed carrier,
while `original_source_location` preserves the pre-resize original; validation
recomputes the carrier bytes from the original and rejects a substituted resize.
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

Generate reusable article-type assets with `scripts/orgs.py asset-plan`. It intentionally does not invent generic micro-component slots. After the storyboard, run `scripts/build_visual_kit.py` and prepare only the 0–4 article-specific roles selected in `production_preferences` / `visual_kit.selected_roles` through the following raw→derived contract.

### Micro-illustration raw→derived lineage

The ChatGPT/provider download is a **raw generation source**. Keep its original bytes under `assets/generated/`. The synthetic migration image and its strict native-RGBA admission gate are not part of startup. For each real selected article component, request a source suited to the subject: native transparency may run with `--require-native-alpha`, while a deliberately uniform controlled-key source may run with the plan's exact `--key-color`. Provider/file-extension claims are never trusted. The raw file is normally not a standalone `assets[]` entry. It must never carry `visual_role: article-micro`, a visual-kit `role`, or be placed in Ardot as the final component image. Regardless of source route, the registered derivative must pass the same strict final RGBA8/cutout checks.

Every formal cutout also requires `org-wechat-provider-image-acquisition-v2` passed as `--acquisition-report`. In addition to article/slot/prompt, ordered attempts, distinct provider requests, SHA and timezone-aware timestamps, v2 binds the verified installed-release registry census; exact adapter bytes and the adapter-declared `generation_route_id`; the same-session runtime binding; canonical request metadata; and one create-once Browser ingestion report per downloaded raw source. The validator reopens every ingestion report and raw target, recomputes SHA-256 and byte length, and requires the accepted target to be the processor's exact source path. No synthetic RGBA migration image is required before source reading. Real transparent outputs retain their own quality checks.

Current-session v2 acquisition is operationally accepted after the same-session runtime binding, canonical request, create-once ingestion, exact raw bytes, and the real asset's selected quality chain validate. It must remain `current-session-operator-harness-trusted`, `host_attested=false`, and `portable=false`; these serialized files do not become independent host attestation. Preparation, registration, pack validation, and ready-for-layout each revalidate the complete chain. The compatibility callback is only an optional trusted-harness veto policy. See [provider-acquisition-authority.md](provider-acquisition-authority.md).

Create a separate output and report with the actual processor. All three paths are create-once and distinct; replace the example prompt hash with the SHA-256 of the exact generation prompt. Use `--require-native-alpha` for a direct transparent source or `--key-color` for a safely removable controlled background; the two flags are mutually exclusive. For normal current-session operation, omit `--portable-trust-store`; no startup RGBA probe is required and the result stays non-attested and non-portable.

Run this only inside the canonical current organization pack created by `orgs.py init`. Its `assets/generated/` and `assets/derived/` directories must already exist as real, non-symlink directories; the processor intentionally never creates parent directories. Keep the raw source and acquisition report under that pack's existing `assets/generated/`, and choose new, non-existing derivative and report paths under its existing `assets/derived/`. Do not use recursive directory creation at cutout time, redirect either parent through a symlink, or reuse an existing output/report path.

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/prepare_micro_cutout.py" \
  organizations/new-account-id/assets/generated/article-object-raw.png \
  organizations/new-account-id/assets/derived/article-object-cutout.png \
  --report organizations/new-account-id/assets/derived/article-object-cutout.json \
  --role floating-spot \
  --article-id article-slug \
  --asset-slot-id kit.floating-spot \
  --prompt-sha256 sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --generation-route chatgpt-web-image-route-v1 \
  --acquisition-report organizations/new-account-id/assets/generated/article-object-acquisition.json \
  --portable-trust-store /PROTECTED/HOST-PUBLIC-KEYS.json \
  --require-native-alpha
```

Before generating that real slot, choose either entry from
`source_generation.source_options`. Use its exact prompt and
`processor_args`; the controlled-key option's `controlled_key_color` may differ
across slots, so never hard-code one shared green key for the whole visual kit.
Both options are valid first attempts. The older `fallback_*` fields remain
compatibility aliases only and do not impose native-first ordering. This
source-level flexibility does not relax the derivative gate.

The create-once `org-wechat-micro-cutout-derivation-v1` report binds the raw and final locations and file/pixel hashes; article ID, slot ID and role; generation route and prompt hash; processor script/config hashes and method; background/mask/edge assessment; black/white composite probes; and the final RGBA inspection. The validator resolves both files relative to the report, requires the source under `assets/generated/` and the output under `assets/derived/`, and re-computes the hashes and current pixel inspection. A copied report or an `approved: true` claim cannot substitute for those bytes.

Register only the derivative. These are the standalone `register-asset` arguments for a micro illustration; portable use additionally supplies the protected trust store, while current-session use retains the operator/harness-trusted boundary:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/orgs.py" register-asset organizations/new-account-id \
  --id spot.article-object \
  --kind illustration \
  --title "Article object spot" \
  --location assets/derived/article-object-cutout.png \
  --origin derived \
  --style article-specific \
  --use recruitment \
  --role floating-spot \
  --cutout-report assets/derived/article-object-cutout.json \
  --portable-trust-store /PROTECTED/HOST-PUBLIC-KEYS.json \
  --generated-for article-slug \
  --visual-role article-micro
```

`--kind` must be `illustration` or `decoration`; exactly one `--role` is allowed; `--generated-for` must include the report's `article_id`; and `--location` must resolve to the same derivative named by `--cutout-report`. Successful registration derives and stores this auditable shape rather than trusting caller-supplied lineage:

```json
{
  "origin": "derived",
  "visual_role": "article-micro",
  "roles": ["floating-spot"],
  "generated_for_articles": ["article-slug"],
  "cutout": {
    "report_location": "assets/derived/article-object-cutout.json",
    "report_sha256": "sha256:<report-bytes>",
    "source_location": "assets/generated/article-object-raw.png",
    "source_sha256": "sha256:<provider-original-bytes>",
    "output_sha256": "sha256:<derived-rgba-bytes>",
    "method": "native-rgba-normalize-v1",
    "article_id": "article-slug",
    "asset_slot_id": "kit.floating-spot",
    "prompt_sha256": "sha256:<exact-prompt>",
    "generation_route": "chatgpt-web-image-route-v1",
    "authority_binding_sha256": "sha256:<canonical-authority-challenge>",
    "authority_scope_at_creation": "current-session-operator-harness-trusted",
    "acquisition_assurance": "operator-harness-trusted-current-session",
    "host_attested": false,
    "portable": false,
    "processor_script_sha256": "sha256:<processor-bytes>",
    "config_sha256": "sha256:<canonical-config>"
  }
}
```

Direct registration of a ChatGPT original as `article-micro` is forbidden, even if it looks transparent or its mode says RGBA. New micro registration with a role fails unless `origin=derived` and `--cutout-report` verifies. Its slot must be exactly `kit.<role>`. The derivative must also be deterministically decodable RGBA8 with real transparent pixels, robust Alpha geometry, a tight subject crop, no clipped substantive pixels, no halo/debris, and no rectangular/rounded/near-solid matte. Spacing belongs in Ardot, not in a large transparent PNG canvas. Each article records a confirmed count from 0–4 and an equal-length `visual_kit.selected_roles` subset. The ready gate requires one distinct derivative, accepted provider-original SHA, provider request ID, acquisition authority binding, and output SHA for every selected role, so a copied or recropped raw cannot fill several roles. A zero-component article creates none and cannot use old decorations as a substitute. Logos and QR codes always remain official or user-supplied assets.

## Visual-reference provenance

The default mode is source-zero. `organization.provenance` declares `visual_reference_policy: source-zero`, current `visual_input_source_ids`, explicit pack-relative `visual_input_allowed_roots`, `isolation_reviewed_at`, and all four excluded kinds: `prior-article-layout`, `prior-ardot-file`, `prior-article-screenshot`, `other-organization-visual-pack`. Every selected `sources.json` item also declares an allowed kind, a pack-relative locator, and `content_sha256`. Validation rehashes the current file/tree, rejects every symlink component, and rejects legacy/example/output/other-organization paths (including common Chinese old-draft directory names) even when they sit below an allowed root. This is fail-closed content isolation without claiming an unavailable host filesystem lease.

When the user explicitly selects a reviewed style grammar, provenance may instead use `visual_reference_policy: explicit-style-grammar`. It additionally requires:

- non-empty `style_reference_source_ids` that also appear in `provenance.source_ids` and `sources.json`;
- `style_reference_scope: abstract-visual-grammar-only`;
- ISO `reference_reviewed_at`;
- every `style_reference_non_copy_constraints` value: `text`, `photographs`, `logos`, `specific-layout`, `component-geometry`, `artwork`;
- at least one route with a valid `style_grammar`.

The route grammar accepts only nine abstract tokens: `color_motion`, `saturation`, `material`, `lighting`, `layering`, `edge_energy`, `copy_safe_zone`, `photo_responsibility`, and `background_responsibility`. It repeats the six non-copy constraints and stores a canonical lowercase SHA-256 over normalized `tokens + non_copy_constraints`. Optional `preset_id` and `label` are discovery metadata and are not hashed. When `preset_id` is present it must resolve to `style-presets/<preset-id>.json`, whose canonical grammar SHA must equal the route SHA; an unknown preset or a modified-and-resigned route fails. Reference content-shaped fields, URLs, and explicit copy/replicate/verbatim instructions are rejected.

For a later organization, register the reviewed preset JSON itself as the style source and do not reopen the original reference. See [style-options.md](style-options.md).
