# Ardot handoff contract

Use this contract only after the user has completed human review in Ardot.

## Contract shape

The handoff must bind all transport artifacts to one current Ardot revision. The
ellipses below are explanatory placeholders, not a copyable passing fixture;
the exporter must materialize the full current-root layer census and all hashes:

```json
{
  "schema_version": 5,
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
    "body_asset_ids": ["opening-background", "opening-cutout"]
  },
  "workflow_attribution": {
    "policy_id": "tuozhe-ai-ecosystem-workflow-v1",
    "classification": "repository-usage-credit",
    "text": "感谢拓浙 AI 生态提供本篇内容生产工作流支持。",
    "text_sha256": "sha256:44315ffe62d9d46b4e2adfd141944a0ed4bb0fc21b8faf6ec9a295621990b4de",
    "ardot_node_id": "51:5",
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
  "transport_fidelity": {
    "source": "ardot-current-root-layer-export-v1",
    "export": {
      "source": "ardot-current-root-layer-export-v1",
      "revision_algorithm": "ardot-transport-revision-v1",
      "revision_hash": "sha256:...",
      "current_root_revision_hash": "sha256:...",
      "file_id": "...",
      "root_node_id": "...",
      "artboard": {"width_px": 390, "height_px": 4200},
      "chapters": [
        {
          "source": "ardot-current-root-layer-export-v1",
          "chapter_id": "opening",
          "section_node_id": "51:1",
          "order": 1,
          "geometry_space": "article-root-390-v1",
          "geometry": {"x": 0, "y": 0, "width": 390, "height": 720},
          "reference_screenshot": {"path": "qa/opening.png", "sha256": "sha256:...", "width_px": 390, "height_px": 720},
          "background_layer": {
            "asset_id": "opening-background",
            "path": "assets/opening-background.png",
            "sha256": "sha256:...",
            "width_px": 1170,
            "height_px": 2160,
            "export_scale": 3,
            "contains_text": false,
            "text_baked": false,
            "text_node_count": 0,
            "source_node_id": "51:2",
            "render_style": {"object_fit": "cover", "object_position": "50% 50%", "opacity": 1, "rotation_deg": 0, "blend_mode": "normal", "mask": "none"},
            "background_node_export": {
              "path": "qa/opening-background-node.json",
              "sha256": "sha256:..."
            },
            "z_index": 0
          },
          "visible_text_nodes": [
            {
              "node_id": "51:4",
              "order": 1,
              "text": "...",
              "text_sha256": "sha256:...",
              "native_editable_text": true,
              "visible": true,
              "rasterized": false,
              "semantic_role": "hero-title",
              "tag": "h1",
              "z_index": 2,
              "style": {"font_family": "system-sans-cn", "font_size_px": 40, "line_height_ratio": 1.15, "font_weight": 800, "font_style": "normal", "text_decoration": "none", "color": "#FFFFFF", "letter_spacing_px": -0.2, "text_align": "left", "opacity": 1, "rotation_deg": 0, "blend_mode": "normal"},
              "geometry": {"x": 24, "y": 96, "width": 342, "height": 120}
            },
            {
              "node_id": "51:5",
              "order": 2,
              "text": "感谢拓浙 AI 生态提供本篇内容生产工作流支持。",
              "text_sha256": "sha256:44315ffe62d9d46b4e2adfd141944a0ed4bb0fc21b8faf6ec9a295621990b4de",
              "native_editable_text": true,
              "visible": true,
              "rasterized": false,
              "semantic_role": "workflow-attribution",
              "tag": "p",
              "z_index": 3,
              "style": {"font_family": "system-sans-cn", "font_size_px": 12, "line_height_ratio": 1.7, "font_weight": 400, "font_style": "normal", "text_decoration": "none", "color": "#FFFFFF", "letter_spacing_px": 0, "text_align": "center", "opacity": 1, "rotation_deg": 0, "blend_mode": "normal"},
              "geometry": {"x": 24, "y": 680, "width": 342, "height": 24}
            }
          ],
          "decorations": [
            {
              "asset_id": "opening-cutout",
              "source_node_id": "51:3",
              "path": "assets/opening-cutout.png",
              "sha256": "sha256:...",
              "role": "article-micro",
              "micro_role": "floating-spot",
              "alpha": {"required": true, "verified": true},
              "independent": true,
              "contained_in_background": false,
              "z_index": 1,
              "geometry": {"x": 246, "y": 420, "width": 112, "height": 112},
              "render_style": {"object_fit": "contain", "object_position": "50% 50%", "opacity": 1, "rotation_deg": 0, "blend_mode": "normal", "mask": "none"}
            }
          ],
          "photos": [],
          "interaction": null
        }
      ]
    }
  },
  "assets": [
    {
      "id": "opening-background",
      "path": "assets/opening-background.png",
      "sha256": "sha256:...",
      "role": "body-image"
    },
    {
      "id": "opening-cutout",
      "path": "assets/opening-cutout.png",
      "sha256": "sha256:...",
      "role": "body-image"
    },
    {
      "id": "cover",
      "path": "assets/cover.png",
      "sha256": "...",
      "role": "cover",
      "wechat_thumb_media_id": "target-account-thumb-media-id-required-before-final-compile",
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
  "components": []
}
```

Equivalent tool-native data is acceptable while authoring, but final transport requires an immutable local schema-v5 manifest so its layer files and hashes can be independently validated. The invariants are required.

The transport revision is the SHA-256 of canonical JSON for the entire export with `revision_hash` omitted. It therefore changes when chapter order, geometry, text style, background, cutout, or interaction state changes even if the visible wording stays identical.

Choose one assurance mode. Without a host signer, use `current-session-draft`: the active host trace must show the exact Ardot reread, candidate compilation, real WeChat draft write, reopen, and chapter readback. It produces only `wechat-candidate.html` and `candidate-report.json`; `portable_audit_verified`, `delivery_eligible`, and `finalization_verified` remain false. Run:

```bash
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --intended-html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --require-live-root --session-draft
python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --session-draft --output delivery --check
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --compile-report delivery/candidate-report.json --require-compile-report \
  --session-draft
```

With a real host attestor, `portable-signed-audit` retains both Ed25519 receipts and the terminal `wechat.html` / `compile-report.json` chain. Run:

```bash
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --intended-html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --require-live-root
python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --output delivery --check
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --compile-report delivery/compile-report.json --require-compile-report
```

In `portable-signed-audit`, the host-issued receipt has this exact signed field set; it is a sidecar, never
embedded in the handoff or organization pack:

```json
{
  "schema_version": 1,
  "source": "ardot-host-live-read-receipt-v1",
  "signature_algorithm": "ed25519",
  "key_id": "host-key-epoch",
  "nonce": "32-to-64-lowercase-hex",
  "provider": "current-provider-id",
  "session_id": "current-session-id",
  "request_id": "actual-tool-request-id",
  "runtime_binding_nonce": "binding-only preflight nonce",
  "runtime_binding_digest": "sha256:...",
  "trusted_bundle_sha256": "sha256:...",
  "file_id": "...",
  "root_node_id": "...",
  "root_revision_hash": "sha256:...",
  "transport_revision_hash": "sha256:...",
  "handoff_sha256": "sha256:...",
  "frozen_export_sha256": "sha256:...",
  "live_export_sha256": "sha256:...",
  "output_html_path_identity_sha256": "sha256:...",
  "captured_at": "RFC3339 timestamp from the live export",
  "observed_at": "RFC3339 host observation timestamp",
  "expires_at": "RFC3339 timestamp no more than ten minutes later",
  "signature": "ed25519:<base64 64-byte signature>"
}
```

The harness keeps the Ed25519 private key outside the repository/model process.
A real `host.receipt.attest` callable performs signing, while the repository
reads the matching public key only from a root-owned, non-symlink,
group/other-nonwritable JSON trust store. `ORG_WECHAT_HOST_RECEIPT_TRUST_STORE`
may select that protected absolute path; a raw environment public key is
forbidden. The signer derives runtime/provider/request fields from its own trace and checks
the trusted-bundle digest against an allowed release; it never signs arbitrary
model-provided values. The repository has no receipt-issuing CLI by design.

After reopening the WeChat draft in `portable-signed-audit`, the same host trust authority issues a second
sidecar with this exact field set:

```json
{
  "schema_version": 1,
  "source": "wechat-host-saved-draft-receipt-v1",
  "signature_algorithm": "ed25519",
  "key_id": "host-key-epoch",
  "nonce": "32-to-64-lowercase-hex",
  "provider": "current-wechat-provider-id",
  "session_id": "current-wechat-session-id",
  "request_id": "actual-readback-request-id",
  "runtime_binding_nonce": "same binding-only preflight nonce",
  "runtime_binding_digest": "sha256:...",
  "trusted_bundle_sha256": "sha256:...",
  "target_account_ref": "resolved target account",
  "draft_id": "actual reopened draft",
  "title": "exact frozen handoff article title",
  "digest": "exact frozen handoff article digest",
  "cover_asset_id": "cover asset bound by handoff.article and handoff.assets",
  "thumb_media_id": "actual target-account cover material id",
  "cover_hosted_url": "https://mmbiz.qpic.cn/actual-saved-cover-derivative",
  "cover_downloaded_sha256": "sha256:...",
  "cover_downloaded_byte_length": 123456,
  "handoff_sha256": "sha256:...",
  "transport_revision_hash": "sha256:...",
  "output_html_path_identity_sha256": "sha256:...",
  "compiled_html_sha256": "sha256:...",
  "compile_report_sha256": "sha256:...",
  "live_receipt_sha256": "sha256:...",
  "readback_sha256": "sha256:...",
  "observed_at": "RFC3339 host observation timestamp",
  "expires_at": "RFC3339 timestamp no more than ten minutes later",
  "signature": "ed25519:<base64 64-byte signature>"
}
```

The bound `wechat-saved-draft-readback-v1` has the same exact title, digest,
`cover_asset_id`, and `thumb_media_id`. Its `cover_hosted_derivative` contains
only `url`, `downloaded_path`, `downloaded_sha256`, and
`downloaded_byte_length`; the URL must be the actual HTTPS
`mmbiz.qpic.cn` object from the reopened draft, and the local non-symlink file
must reproduce both the declared hash and byte length. The cover ID must name
exactly one `role: "cover"` handoff asset and match
`handoff.article.cover_asset_id`. The receipt repeats these values and also
signs the complete readback bytes.

For a newly uploaded cover, upload the cover material before the compile that
will be used for the draft write. Write the returned target-account
`thumb_media_id` into that exact `role: "cover"` asset, then regenerate the
handoff SHA, take a new fresh live-root capture, and regenerate the selected
candidate/report chain. A provisional chain compiled while
`wechat_thumb_media_id` was null or empty is invalid and must never be pasted;
the validator does not accept an arbitrary readback thumb ID to fill that gap.

For current-session readback, use the candidate chain and do not invent either receipt:

```bash
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --compile-report delivery/candidate-report.json --require-compile-report \
  --expected-target-account 'exact-account-ref-from-delivery-preflight' \
  --readback saved-draft-readback.json --require-readback --session-draft
```

Require `session_readback_structural_match: true` and `portable_audit_verified: false`, plus the active host trace showing the actual account, draft write, reopen, and export. For portable readback, use final `wechat.html`, final `compile-report.json`, the original live receipt, and `--readback-receipt saved-draft-readback-receipt.json`. Neither path authorizes formal publication or group-send.

The frozen chapters use `article-root-390-v1` geometry and cover the current Ardot artboard continuously: first `y=0`, every next `y` equals the previous bottom, and the final bottom equals `artboard.height_px`. A height sum alone cannot prove this because gaps and overlaps may cancel.

For final delivery, every background must be the complete `1170 x (chapter_height * 3)` export. Its hash-bound `background_node_export` uses source `ardot-background-only-node-export-v1` and must match the current file/root/section/source node, asset ID/SHA, width/height/export scale, `text_descendant_count: 0`, and `text_descendant_node_ids: []`. A declaration on the PNG record alone is not evidence that text was excluded.

Every `mode: "svg"` interaction additionally requires `ardot_state_export` (`ardot-interaction-state-export-v1`) as a local hash-bound JSON file, plus `fallback_key`, `fallback_semantic_sha256`, and `fallback_asset`. Its `ardot_states` object has exactly `closed`, `open`, and `fallback`; each carries a non-empty, mutually distinct `node_id` and a `sha256:<64 hex>` canonical `tree_sha256`. The state export repeats these three records in that order and binds the current file/root/section/source node plus `svg_structure_sha256`. The validator recomputes that structure hash from the actual frozen SVG and again from compiled/saved-draft SVG bytes; state names or a supplied SVG hash alone never count as proof.

Every compiled top-level layer carries a canonical render signature over its source-node layer ID, tag, role, source hash, geometry, z-index, exact inline style, and interaction mode. HTML postflight checks the complete per-chapter layer sequence, strict allowed subtree grammar and exact image occurrence/parent order, and rehashes copied image bytes. Text layers allow characters only; interaction wrappers allow exactly one SVG or one fallback image. `compile-report.json.artifact_binding.wechat_html` then binds the final path-identity hash, device/inode, SHA-256, byte length, handoff SHA and transport revision, and must be rechecked immediately before upload/paste.

The article-JSON adapter is authoring-only. It requires the explicit `--authoring-preview` flag, emits no delivery `wechat.html`, and must never be pasted into the official-account editor.

`node_export_file` is a local, non-symlink, immutable export inside the handoff directory. The following is a non-copyable schema sketch, not a passing minimum bundle; every placeholder and every canonical layer record must be materialized by the exporter. `visible_text_nodes` is the current root's full visible text reading order, not a sample:

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
      "node_id": "51:4",
      "component_name": "WeChat/Hero/Title/<Mode>",
      "node_kind": "TEXT",
      "text": "...",
      "native_editable_text": true,
      "visible": true,
      "rasterized": false
    },
    {
      "node_id": "51:5",
      "component_name": "WeChat/Footer/WorkflowAttribution/<Mode>",
      "node_kind": "TEXT",
      "text": "感谢拓浙 AI 生态提供本篇内容生产工作流支持。",
      "native_editable_text": true,
      "visible": true,
      "rasterized": false
    }
  ],
  "component_order": [
    {"node_id": "51:1", "component_name": "WeChat/Section/Opening/<Mode>"},
    {"node_id": "51:2", "component_name": "WeChat/Background/Opening/<Mode>"},
    {"node_id": "51:3", "component_name": "WeChat/Micro/Opening/<Mode>"},
    {"node_id": "51:4", "component_name": "WeChat/Hero/Title/<Mode>"},
    {"node_id": "51:5", "component_name": "WeChat/Footer/WorkflowAttribution/<Mode>"}
  ],
  "transport_sections": [
    {
      "chapter_id": "opening",
      "section_node_id": "51:1",
      "order": 1,
      "geometry_space": "article-root-390-v1",
      "geometry": {"x": 0.0, "y": 0.0, "width": 390.0, "height": 720.0},
      "layers": ["complete canonical source-node layer records; no samples"]
    }
  ],
  "body_asset_ids": ["opening-background", "opening-cutout"],
  "assets": [
    {"id": "opening-background", "sha256": "sha256:..."},
    {"id": "opening-cutout", "sha256": "sha256:..."},
    {"id": "cover", "sha256": "sha256:..."}
  ]
}
```

`revision_hash` is not a supplied label. The validator recomputes
`ardot-root-revision-v1` as SHA-256 over canonical JSON containing the algorithm,
file ID, root node ID, every normalized visible-text node in order, the complete
component order, exact `transport_sections`, exact `body_asset_ids`, and the current asset ID/SHA pairs sorted by asset ID. It
requires the recomputed value to match both the export and handoff, and requires
the export asset map to match `handoff.assets`. Every handoff asset path is also
resolved inside the bundle and rehashed from its actual non-symlink file. Editing
body text, section/layer geometry or style, source node, component order, or an asset therefore invalidates the frozen revision
even when both JSON files repeat the same stale string.

`component_order` is also the complete visible render-node census, not a sample of named components. Its unique node IDs must equal the union of every transported section node and every background/decoration/photo/text/interaction source node exactly once. An extra visible Ardot component that is absent from `transport_sections`, or a transport layer missing from `component_order`, blocks the handoff even after all JSON hashes are recomputed.

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

- Recompute `ardot-root-revision-v1` from normalized extracted text, complete component order, exact transport section/layer/source/style/body-asset census, current asset hashes, file/design ID, and root node ID; never accept two matching self-reported revision strings without recomputation.
- Schema v5 is mandatory. Resolve `workflow_attribution` from the current Ardot root export: its node belongs to that root, is a visible native editable `TEXT` node, contains the exact fixed text, and is last in normalized visible reading order. Include its node, text, and order in the content revision; bind the full layer export to the independent transport revision. The Boolean fields are summaries, not self-authenticating evidence. Every older bundle must be refrozen from the current root.
- Regenerate the bundle after any Ardot edit. Never patch a previously compiled HTML file and continue calling it the same revision.
- Immediately before compilation, capture the same root again through the active Ardot-capable host into a separate file and pass it with `--live-root-export ...`. Its timezone-aware `captured_at` must be strictly later than the frozen export, its bytes must differ, and it must not be the same file or a hard link. The fresh text/section/layer/style/source/asset snapshot must equal the frozen root revision. In `current-session-draft`, the same observable host session must retain the real reread trace, bind the exact live export/candidate HTML/candidate report, write the WeChat draft, reopen it, and validate every chapter with `--session-draft --require-readback`; this mode can create and verify a draft but cannot claim portable audit or publication. In `portable-signed-audit`, a real `host.receipt.attest` callable additionally issues and Ed25519-signs `ardot-host-live-read-receipt-v1`; the protected trust store verifies the receipt and the secure final chain. The current Codex Desktop adapter declares the attestor unavailable, so it uses current-session draft mode rather than blocking delivery/full outright.
- Native text uses an explicit supported WeChat system family and exact allowlisted style. Every raster layer declares source node and complete supported `render_style`; unknown visual properties, fonts, rotation, blend or mask must be resolved in Ardot rather than silently dropped.
- The title and digest must come from named Ardot fields or an explicit delivery-settings node. If either is absent, ask only for that missing delivery metadata; do not reopen upstream writing.
- A cover may be a designated Ardot frame or a current asset. Do not infer a cover from an older article.
- Preserve native text as text. Rasterize only elements that cannot survive WeChat transport and record that conversion.
- A chapter screenshot, contact sheet, QA image, or section composite is evidence only and can never be a body asset. Export each complex background without text as the complete `1170 x (chapter_height * 3)` layer with its background-only node export, keep documentary photos separate, and keep every micro raster as the exact approved true-alpha cutout SHA.
- `static` components do not need a capability profile. `horizontal-swipe` and `svg-smil-self-v1` require an information-equivalent fallback. Only `svg-smil-self-v1` may contain the policy's no-ID self-trigger SMIL subset.
- Keep the target-account capability profile outside this bundle and outside the organization pack. Reference it by ID; never embed tokens, account secrets, or another account's certification.
- After cover upload, bind the target-account `thumb_media_id` to the same cover asset hash and verify it in the saved draft.
- For every eligible generated raster carrier, bind the public watermark evidence to the marked asset hash. Keep the secret and raw watermark-ID mapping outside this bundle, the organization pack, Ardot, and logs.
- After saving the draft, download the actual WeChat-hosted body/cover derivative, run authenticated detection, and bind the result to its downloaded SHA-256, byte length, format, dimensions, expected payload fingerprint, and asset ID before recording `transport_verified` or `transport_lost`. URL or HTML readback alone is insufficient. A cropped/rotated/bordered phone screenshot is outside V1's guarantee and is not a substitute for the hosted object.

## Blocking mismatches

Stop before delivery when:

- the selected root is ambiguous;
- `workflow_attribution` is absent or differs from policy `tuozhe-ai-ecosystem-workflow-v1`; its text/hash, current-root node, component name, node kind, editability, visibility, uniqueness, or terminal order fails; or `schema_version` is anything other than 5;
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
- `transport_fidelity` is missing, uses any source other than `ardot-current-root-layer-export-v1`, does not map every chapter/section node exactly once, changes the canonical layer revision, admits a section composite/QA screenshot, lacks an exact-size background-only export, rasterizes native copy, omits an independent cutout, or substitutes a freehand SVG.
- fresh current-root evidence is missing, reuses/hard-links/byte-copies the frozen evidence, lacks a strictly later timezone-aware capture time, or differs in any text, chapter y/bottom, layer source node, z/style, interaction state or body asset; in current-session mode, the current host trace or exact candidate binding is missing, or `portable_audit_verified` is not false; in portable mode, either short-lived host-signed receipt is invalid or missing;
- compiled HTML contains an unsigned descendant/attribute, duplicate or reparented image, extra root content, or differs in path identity/device/inode/SHA/byte length/handoff/revision from its required compile-report artifact binding;
- saved-draft chapter readback lacks matching account/draft/time, order/text-node hash, hosted asset download hashes, or a hash-bound 390 px screenshot for every section; current-session readback lacks the real host write/reopen trace or `session_readback_structural_match: true`; portable readback lacks `wechat-host-saved-draft-receipt-v1` binding the full final compile/readback byte chain; or either mode is used to publish/group-send without separate explicit confirmation.
