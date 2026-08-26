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
  "visual_kit": {
    "status": "approved",
    "direction": "Short article-specific visual direction",
    "assets": [
      {"id": "spot.example-a", "role": "floating-spot", "placement": ["lead-edge"]},
      {"id": "visual.example-transition", "role": "section-transition", "placement": ["before-section-01"]},
      {"id": "spot.example-b", "role": "inline-explainer", "placement": ["inside-process"]},
      {"id": "spot.example-a", "role": "closing-motif", "placement": ["before-cta"]}
    ]
  },
  "layout_review": {
    "visual_reviewed": true,
    "content_sections": 8,
    "boxed_sections": 1,
    "maximum_consecutive_boxed_sections": 1,
    "asymmetric_or_edge_breaking_moments": 3,
    "every_block_has_container": false
  },
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

Before visual authoring, generate and complete the mandatory article-specific visual kit:

```bash
python3 scripts/build_visual_kit.py article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/visual-kit-plan.json
```

The four required roles are `floating-spot`, `section-transition`, `inline-explainer`, and `closing-motif`. Use at least three distinct `generated-illustrative` registry assets across them. Every kit asset must include this `article_id` in its registry `generated_for_articles`, so old generic decoration cannot silently satisfy the gate. Then generate the Ardot assembly manifest:

```bash
python3 scripts/build_ardot_manifest.py article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/ardot-manifest.json
```

After visual review in Ardot, record the measured result in `layout_review`. Final transport is blocked unless closed boxes are at most 20% of content sections, no two boxes are consecutive, at least three asymmetric or edge-breaking moments are present, and the review confirms that the article is not a stack of containers.

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
- Missing visual-kit roles, fewer than three unique generated micro assets, or non-generated assets in the kit block `--check`.
- A missing or failed `layout_review` blocks `--check`.
- A QR image that is not explicitly official or user-supplied blocks `--check`.
