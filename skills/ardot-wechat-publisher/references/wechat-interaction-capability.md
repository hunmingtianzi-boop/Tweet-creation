# WeChat interaction capability policy

Use this reference whenever the reviewed Ardot article contains a non-static component. The fixed workflow capability is the generation, probing, verification, and deterministic fallback of a narrow pure-SVG/CSS subset. It is not a claim that every WeChat account and client will run every SVG animation.

## Fixed policy

Policy ID: `wechat-svg-smil-self-v1`.

Allowed as a candidate:

- inline SVG with no JavaScript and no `id`;
- `<set>` and `<animateTransform>` whose `begin` is exactly `click` on the element being animated;
- one-way reveal, color change, or translate motion that remains understandable if it never runs;
- SVG `<image>` only after the image URL has been replaced with a target-account WeChat `mmbiz.qpic.cn` URL;
- CSS horizontal swipe with inline `overflow-x:auto|scroll`, a visible swipe cue, and a complete static stack fallback.

Always reject:

- JavaScript, `on*` handlers, `javascript:` URLs, external stylesheets, or `<style>` transport dependencies;
- `<details>`, `<summary>`, `<foreignObject>`, `<use>`, forms, iframes, objects, or embeds;
- every transport `id`, `href="#..."`, `url(#...)`, and cross-element timing such as `begin="card.click"`;
- unprobed SMIL elements, including `<animate>` and `<animateMotion>`;
- an interactive component without a static information-equivalent.

WeChat was observed to preserve inline SVG, `<set>`, `<animateTransform>`, self `begin="click"`, a WeChat-hosted SVG image, and CSS overflow when saving and reopening a probe draft, while removing every `id`. The sanitized evidence fixture is stored at `tests/fixtures/wechat-capability/`; it records `mobile_runtime.status: pending`. Structure survival is not runtime certification.

## Ardot handoff

Keep three native, editable states for every interaction:

1. closed or initial state;
2. open or completed state;
3. information-equivalent static fallback.

Record distinct Ardot node IDs, screenshots, and hashes for these states. Each transport component uses a stable `data-fallback-key` and a `data-fallback-hash="sha256:..."` derived from its normalized source content. The dynamic and static forms must carry the same key and hash.

## Candidate validation

Run the repository validator before transmitting a dynamic candidate:

```bash
python3 scripts/wechat_interaction_policy.py candidate.html \
  --fallback fallback.html \
  --output interaction-policy-report.json
```

An `ok: true`, `status: candidate` result means the source and fallback satisfy the fixed syntax policy. It does not authorize the dynamic payload. Until certification completes, `recommended_payload` remains `static-fallback`.

## Draft readback

Upload body images first, compile SVG image references to the returned WeChat URLs, save the candidate to one draft, and immediately retrieve the saved body. Re-run:

```bash
python3 scripts/wechat_interaction_policy.py candidate.html \
  --fallback fallback.html \
  --readback saved-draft-body.html \
  --mobile-profile account-capability.json \
  --target-account-id TARGET_ACCOUNT_ID \
  --require-certified
```

Readback must preserve, per semantic component:

- interaction markers and fallback keys/hashes;
- `<set>` / `<animateTransform>` counts;
- exact self `begin="click"` values;
- normalized SMIL structure signatures, including target attribute, transform type, values, duration, repeat count, and fill behavior;
- WeChat-hosted image references and body content order.

Draft readback proves only that the sanitizer retained the structure. It cannot prove the WeChat client executed the interaction.

## Mobile capability profile

Dynamic delivery additionally requires an unexpired account-specific profile. Keep this profile in the delivery environment, never in the portable organization pack:

```json
{
  "schema_version": 1,
  "policy_version": "wechat-svg-smil-self-v1",
  "status": "passed",
  "target_account_id": "...",
  "draft_id": "...",
  "probe_sha256": "64 hex",
  "readback_sha256": "64 hex",
  "verified_at": "RFC3339",
  "valid_until": "RFC3339",
  "clients": [
    {
      "platform": "ios",
      "wechat_version": "...",
      "result": "passed",
      "preview_evidence": "..."
    },
    {
      "platform": "android",
      "wechat_version": "...",
      "result": "passed",
      "preview_evidence": "..."
    }
  ]
}
```

Invalidate or re-probe when the policy version, target account, sanitizer behavior, or relevant WeChat client behavior changes. A `pending`, failed, expired, mismatched, or incomplete profile must select the static fallback and update the same draft rather than creating a duplicate.

## Cover is a separate gate

SVG does not solve the cover field. The official route must upload the current cover through permanent material and set the returned target-account `media_id` as `thumb_media_id`. Body-image URLs, SVG image URLs, and another account's material IDs cannot substitute for it. Browser fallback is complete only when the visible draft shows the actual cover after saving and reopening.
