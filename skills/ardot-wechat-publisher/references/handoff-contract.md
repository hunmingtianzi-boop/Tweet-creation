# Ardot handoff contract

Use this contract only after the user has completed human review in Ardot.

## Minimum current-revision bundle

The handoff must bind all transport artifacts to one current Ardot revision:

```json
{
  "schema_version": 4,
  "ardot": {
    "file_id": "...",
    "root_node_id": "...",
    "root_name": "...",
    "captured_at": "RFC3339 timestamp",
    "revision_algorithm": "ardot-root-revision-v1",
    "revision_hash": "sha256:..."
  },
  "article": {
    "title": "...",
    "digest": "...",
    "author": "...",
    "content_html": "wechat.html",
    "cover_asset_id": "cover",
    "body_asset_ids": ["photo-1"]
  },
  "workflow_attribution": {
    "policy_id": "tuozhe-ai-ecosystem-workflow-v1",
    "classification": "repository-usage-credit",
    "text": "感谢拓浙 AI 生态提供本篇内容生产工作流支持。",
    "text_sha256": "sha256:44315ffe62d9d46b4e2adfd141944a0ed4bb0fc21b8faf6ec9a295621990b4de",
    "ardot_node_id": "...",
    "component_name": "WeChat/Footer/WorkflowAttribution/<Mode>",
    "node_kind": "TEXT",
    "native_editable_text": true,
    "visible": true,
    "terminal": true,
    "organization_identity": false,
    "body_fact": false,
    "visual_reference": false,
    "node_export_file": "qa/ardot-root-nodes.json",
    "node_export_sha256": "sha256:..."
  },
  "assets": [
    {
      "id": "photo-1",
      "path": "assets/photo-1.png",
      "sha256": "...",
      "role": "body-image"
    },
    {
      "id": "cover",
      "path": "assets/cover.png",
      "sha256": "...",
      "role": "cover",
      "wechat_thumb_media_id": null,
      "watermark": {
        "scheme": "org-wechat-dct-v1",
        "payload_fingerprint": "<64 lowercase hex characters>",
        "key_id": "external-key-epoch-1",
        "key_epoch": 1,
        "psnr_db": 44.37,
        "psnr_threshold_db": 42.0,
        "source_location": "assets/generated/unwatermarked-masters/cover.png",
        "source_sha256": "...",
        "marked_sha256": "...",
        "report_location": "assets/derived/cover-watermark.json",
        "report_sha256": "...",
        "local_verified": true,
        "transport_status": null
      }
    }
  ],
  "components": [
    {
      "id": "...",
      "transport_mode": "static|horizontal-swipe|svg-smil-self-v1",
      "policy_version": "wechat-svg-smil-self-v1",
      "ardot_states": {
        "closed_node_id": "...",
        "open_node_id": "...",
        "fallback_node_id": "...",
        "screenshot_sha256": ["...", "...", "..."]
      },
      "fallback_id": "...",
      "fallback_sha256": "...",
      "readback_expectations": {
        "fallback_key": "...",
        "fallback_hash": "sha256:...",
        "smil_signature": "sha256:..."
      },
      "capability_profile_id": "target-account/policy-version"
    }
  ]
}
```

Equivalent tool-native data is acceptable; a literal JSON file is not required. The invariants are required.

`node_export_file` is a local, non-symlink, immutable export inside the handoff directory. It uses this minimal shape; `visible_text_nodes` is the current root's full visible text reading order, not a sample:

```json
{
  "schema_version": 1,
  "source": "ardot-current-root-export",
  "file_id": "...",
  "root_node_id": "...",
  "captured_at": "RFC3339 timestamp",
  "revision_algorithm": "ardot-root-revision-v1",
  "revision_hash": "sha256:...",
  "visible_text_nodes": [
    {
      "node_id": "...",
      "component_name": "WeChat/Footer/WorkflowAttribution/<Mode>",
      "node_kind": "TEXT",
      "text": "感谢拓浙 AI 生态提供本篇内容生产工作流支持。",
      "native_editable_text": true,
      "visible": true,
      "rasterized": false
    }
  ],
  "component_order": [
    {"node_id": "...", "component_name": "WeChat/Hero/<Mode>"},
    {"node_id": "...", "component_name": "WeChat/Footer/WorkflowAttribution/<Mode>"}
  ],
  "assets": [
    {"id": "cover", "sha256": "<64 lowercase hex characters>"}
  ]
}
```

`revision_hash` is not a supplied label. The validator recomputes
`ardot-root-revision-v1` as SHA-256 over canonical JSON containing the algorithm,
file ID, root node ID, every normalized visible-text node in order, the complete
component order, and the current asset ID/SHA pairs sorted by asset ID. It
requires the recomputed value to match both the export and handoff, and requires
the export asset map to match `handoff.assets`. Every handoff asset path is also
resolved inside the bundle and rehashed from its actual non-symlink file. Editing
body text, component order, or an asset therefore invalidates the frozen revision
even when both JSON files repeat the same stale string.

Run the executable gate before delivery:

```bash
python3 scripts/validate_workflow_attribution.py handoff.json \
  --report workflow-attribution-preflight.json
```

After saving and reopening the draft, export its actual visible body text to a UTF-8 text file and rerun the gate. The readback must come from WeChat, not the source HTML:

```bash
python3 scripts/validate_workflow_attribution.py handoff.json \
  --saved-draft-visible-text saved-draft-visible-text.txt \
  --require-readback \
  --report workflow-attribution-readback.json
```

Exit `0` passes, `1` is a blocking attribution mismatch, and `2` is an unreadable/invalid handoff input.

## Revision rules

- Recompute `ardot-root-revision-v1` from normalized extracted text, complete component order, current asset hashes, file/design ID, and root node ID; never accept two matching self-reported revision strings without recomputation.
- Schema v4 is mandatory. Resolve `workflow_attribution` from the current Ardot root export: its node belongs to that root, is a visible native editable `TEXT` node, contains the exact fixed text, and is last in normalized visible reading order. Include its node, text, and order in `revision_hash`; the Boolean fields are summaries, not self-authenticating evidence. Legacy v3 bundles must be refrozen from the current root.
- Regenerate the bundle after any Ardot edit. Never patch a previously compiled HTML file and continue calling it the same revision.
- The title and digest must come from named Ardot fields or an explicit delivery-settings node. If either is absent, ask only for that missing delivery metadata; do not reopen upstream writing.
- A cover may be a designated Ardot frame or a current asset. Do not infer a cover from an older article.
- Preserve native text as text. Rasterize only elements that cannot survive WeChat transport and record that conversion.
- `static` components do not need a capability profile. `horizontal-swipe` and `svg-smil-self-v1` require an information-equivalent fallback. Only `svg-smil-self-v1` may contain the policy's no-ID self-trigger SMIL subset.
- Keep the target-account capability profile outside this bundle and outside the organization pack. Reference it by ID; never embed tokens, account secrets, or another account's certification.
- After cover upload, bind the target-account `thumb_media_id` to the same cover asset hash and verify it in the saved draft.
- For every eligible generated raster carrier, bind the public watermark evidence to the marked asset hash. Keep the secret and raw watermark-ID mapping outside this bundle, the organization pack, Ardot, and logs.
- After saving the draft, download the actual WeChat-hosted body/cover derivative, run authenticated detection, and bind the result to its downloaded SHA-256, byte length, format, dimensions, expected payload fingerprint, and asset ID before recording `transport_verified` or `transport_lost`. URL or HTML readback alone is insufficient. A cropped/rotated/bordered phone screenshot is outside V1's guarantee and is not a substitute for the hosted object.

## Blocking mismatches

Stop before delivery when:

- the selected root is ambiguous;
- `workflow_attribution` is absent or differs from policy `tuozhe-ai-ecosystem-workflow-v1`; its text/hash, current-root node, component name, node kind, editability, visibility, uniqueness, or terminal order fails; or the handoff is legacy schema v3;
- current text differs from the transport artifact;
- an asset is missing or its hash changed after compilation;
- an eligible generated raster lacks matching `local_verified` watermark evidence, its public evidence exposes a raw watermark ID or identity data, or the first embed/re-embed is attempted in the publisher;
- the cover cannot be resolved;
- the current cover hash has no target-account `thumb_media_id`, or the saved draft does not show that cover;
- an interactive component lacks a static equivalent;
- an interactive component lacks closed/open/fallback Ardot state evidence, matching fallback hashes, readback expectations, or a current target-account capability profile;
- a component uses JavaScript, `<details>`, any transport `id`, cross-ID SMIL timing, or an interaction mode outside `wechat-svg-smil-self-v1`;
- the target account has not been identified.
- required watermark mode has any locally verified carrier without authenticated `transport_verified` evidence from the actual WeChat-hosted derivative.
- saved-draft normalized visible text does not contain the exact workflow attribution once and end with it. A surviving `data-*` marker alone does not pass because WeChat may sanitize markers.
