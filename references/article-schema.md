# Article specification

The compiler accepts UTF-8 JSON:

```json
{
  "schema_version": 1,
  "organization_id": "example-organization",
  "article_type": "recruitment",
  "title": "Article title",
  "summary": "Optional draft summary",
  "route": "optional-route-override",
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

`organization_id` must match the organization pack. `article_type` must exist in `organization.json`. Omit `route` to use the article type’s configured route.

The same JSON drives both Ardot assembly and the final WeChat adapter. Ardot is the visual source of truth. A block may set optional `variant`; otherwise the selected route supplies the variant and `ardot.json` maps it to an exact native component.

Generate the Ardot assembly manifest before visual authoring:

```bash
python3 scripts/build_ardot_manifest.py article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/ardot-manifest.json
```

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
- A QR image that is not explicitly official or user-supplied blocks `--check`.
