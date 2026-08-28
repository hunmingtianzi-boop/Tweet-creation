# Article specification

The compiler accepts UTF-8 JSON:

```json
{
  "schema_version": 1,
  "article_id": "example-article-slug",
  "organization_id": "example-organization",
  "article_type": "recruitment",
  "title": "Article title",
  "summary": "Optional draft summary",
  "route": "optional-route-override",
  "storyboard": {
    "status": "approved",
    "chapters": [
      {
        "id": "opening",
        "label": "Opening",
        "thesis": "One reader-facing idea",
        "composition": "image-led-opening",
        "visual_intent": "A concrete subject enters from open space",
        "density_intent": "Intentional hero pause; body sections return to compact-editorial density",
        "block_indices": [0]
      }
    ]
  },
  "visual_kit": {
    "status": "approved",
    "direction": "Short article-specific visual direction",
    "assets": [
      {
        "id": "spot.example-a",
        "role": "floating-spot",
        "storyboard_chapter": "opening",
        "source_text": "One exact sentence copied from the article",
        "concrete_subject": "A named organization object",
        "action": "enters along the reading direction",
        "composition_role": "anchor",
        "placement": "lead right edge",
        "ardot_component": {
          "file_url": "https://ardot.example/current-organization",
          "node_id": "12:34",
          "name": "WeChat/Ornament/FloatingSpot/Current Mode"
        }
      }
    ]
  },
  "typography": {
    "status": "approved",
    "moments": [
      {
        "role": "hero-title",
        "storyboard_chapter": "opening",
        "source_text": "Main title",
        "treatment": "stacked-title",
        "editable_text": true,
        "font_source": "licensed-or-system",
        "fallback_text_style": "Display/Hero/Fallback",
        "ardot_text_style": {
          "file_url": "https://ardot.example/current-organization",
          "node_id": "14:7",
          "style_id": "13:2",
          "name": "Type/Display/Stacked/Current Mode"
        }
      },
      {
        "role": "statement",
        "storyboard_chapter": "opening",
        "source_text": "Supporting statement",
        "treatment": "mixed-weight",
        "editable_text": true,
        "font_source": "licensed-or-system",
        "fallback_text_style": "Display/Statement/Fallback",
        "ardot_text_style": {
          "file_url": "https://ardot.example/current-organization",
          "node_id": "14:8",
          "style_id": "13:3",
          "name": "Type/Display/MixedWeight/Current Mode"
        }
      }
    ]
  },
  "visual_review_file": "article-visual-review.json",
  "blocks": [
    {
      "type": "hero",
      "component": "core.hero",
      "eyebrow": "OPTIONAL LABEL",
      "title": "Main title",
      "subtitle": "Supporting statement"
    }
  ]
}
```

`article_id` is a stable lowercase slug for this exact article. `organization_id` must match the organization pack. `article_type` must exist in `organization.json`. Omit `route` to use the article type’s configured route.

The same JSON drives both Ardot assembly and the final WeChat adapter. Ardot is the visual source of truth. A block may set optional `variant`; otherwise the selected route supplies the variant and `ardot.json` maps it to an exact native component.

Before visual authoring, validate the 4–10 chapter storyboard:

```bash
python3 scripts/build_storyboard.py article.json \
  --output output/<organization-id>/<slug>/storyboard-plan.json
```

Then generate and complete the mandatory article-specific visual kit:

```bash
python3 scripts/build_visual_kit.py article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/visual-kit-plan.json
```

The four required roles are `floating-spot`, `section-transition`, `inline-explainer`, and `closing-motif`. Every entry must bind to exact article copy and one approved storyboard chapter, with a specific subject/action and a composition role of `anchor`, `motion`, `connector`, or `punctuation`. Use at least three different composition roles and four distinct generated assets. Every asset must pass pixel Alpha/aspect validation and record its native Ardot component file URL, node ID, and exact name. Then generate the Ardot assembly manifest:

```bash
python3 scripts/build_ardot_manifest.py article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/ardot-manifest.json
```

Every storyboard chapter must declare `density_intent`; ordinary chapters default to `compact-editorial`, while intentional open space is reserved for Hero, transition, or ending moments. After assembly, create a separate screenshot-backed visual review and store its path in `visual_review_file`. It must cover five distinct Ardot nodes, include five density samples, and pass every check in [visual-review.md](visual-review.md). A Boolean or count written inside the article cannot self-approve the design.

When organization calibration chooses `expressive-native`, `typography.moments` must contain at least two grounded display moments (up to the organization maximum) across at least two semantic roles and treatments. Each moment references an approved `recipe_id` and contains a `construction` object with at least two allowed non-font techniques, the recipe's full technique set, unique `native_text_node_ids` / `accent_node_ids`, 1–4 lines, and `scale_ratio >= 1.15` when scale contrast is used. Its primary Ardot text node must appear in that construction. Each moment uses licensed/system fonts, stays editable, has a standard fallback, and records file/node/style/name evidence. A font swap alone fails. See [expressive-typography.md](expressive-typography.md). Do not reference an image or asset ID for display copy.

## Supported blocks

- `hero`: `title`, optional `subtitle`, `eyebrow`, `background`, `background_alt`, `cta`.
- `lead`: `paragraphs`.
- `section`: `title`, optional `number`, `kicker`.
- `text`: `paragraphs`.
- `statement`: `title`, optional `label`, `body`.
- `metrics`: `items` with `value`, `label`, and required `source_id` for final checks.
- `timeline`: `items` with `label`, `description`, optional `source_id`.
- `gallery`: `images` with `src`, `alt`, optional `caption`, `source_id`.
- `case`: `name`, `problem`, `approach`, `output`, optional `evidence`, `source_id`.
- `roles`: `items` with `name`, `description`.
- `quote`: `text`, `attribution`, and required `source_id` for final checks.
- `steps`: ordered `items`; each item may be a string or `{title, description}`.
- `image`: `src`, `alt`, optional `caption`, `source_id`.
- `cta`: `title`, optional `body`, `steps`, `button`; optional `qr` requires `src`, `alt`, and `origin` of `user-supplied` or `official`.
- `references`: `items` with `label` and `source_id`.
- `footer`: optional `name`, `tagline`, `logo`, and `credits`.

Relative image paths resolve from the article JSON. The compiler copies local images into the output `assets/` directory. Remote WeChat URLs remain unchanged.

Asset registry IDs such as `visual.hero-example` resolve from the organization pack for both Ardot upload and final transport. Keep generated visuals text-free; copy remains editable in Ardot text nodes.

## Evidence checks

- Every `source_id` must exist in the organization pack’s `sources.json`.
- A metric without `source_id` blocks `--check`.
- A quote without attribution or `source_id` blocks `--check`.
- Placeholders such as `待补充`, `待确认`, `TBD`, and `PLACEHOLDER` block `--check`.
- Missing local images block `--check`.
- Missing visual-kit roles, fewer than four distinct current-article generated micro assets, failed Alpha/aspect validation, missing native Ardot component evidence, or non-generated assets in the kit block `--check`.
- A missing organization/route calibration, incomplete storyboard, ungrounded visual subject, or failed `visual_review_file` blocks `--check`.
- Missing expressive typography recipe/construction evidence, fewer than two non-font techniques or editable layers, a font-swap-only moment, a baked title image, an unlicensed font, or an ungrounded display phrase blocks `--check` when the organization uses `expressive-native`.
- A QR image that is not explicitly official or user-supplied blocks `--check`.
