# Ardot handoff contract

Use this contract only after the user has completed human review in Ardot.

## Minimum current-revision bundle

The handoff must bind all transport artifacts to one current Ardot revision:

```json
{
  "schema_version": 2,
  "ardot": {
    "file_id": "...",
    "root_node_id": "...",
    "root_name": "...",
    "captured_at": "RFC3339 timestamp",
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
      "wechat_thumb_media_id": null
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

## Revision rules

- Hash the normalized extracted text, component order, current asset hashes, file/design ID, and root node ID.
- Regenerate the bundle after any Ardot edit. Never patch a previously compiled HTML file and continue calling it the same revision.
- The title and digest must come from named Ardot fields or an explicit delivery-settings node. If either is absent, ask only for that missing delivery metadata; do not reopen upstream writing.
- A cover may be a designated Ardot frame or a current asset. Do not infer a cover from an older article.
- Preserve native text as text. Rasterize only elements that cannot survive WeChat transport and record that conversion.
- `static` components do not need a capability profile. `horizontal-swipe` and `svg-smil-self-v1` require an information-equivalent fallback. Only `svg-smil-self-v1` may contain the policy's no-ID self-trigger SMIL subset.
- Keep the target-account capability profile outside this bundle and outside the organization pack. Reference it by ID; never embed tokens, account secrets, or another account's certification.
- After cover upload, bind the target-account `thumb_media_id` to the same cover asset hash and verify it in the saved draft.

## Blocking mismatches

Stop before delivery when:

- the selected root is ambiguous;
- current text differs from the transport artifact;
- an asset is missing or its hash changed after compilation;
- the cover cannot be resolved;
- the current cover hash has no target-account `thumb_media_id`, or the saved draft does not show that cover;
- an interactive component lacks a static equivalent;
- an interactive component lacks closed/open/fallback Ardot state evidence, matching fallback hashes, readback expectations, or a current target-account capability profile;
- a component uses JavaScript, `<details>`, any transport `id`, cross-ID SMIL timing, or an interaction mode outside `wechat-svg-smil-self-v1`;
- the target account has not been identified.
