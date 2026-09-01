# WeChat interaction capability policy

Use this reference whenever the reviewed Ardot article contains a non-static component. The fixed workflow capability is the generation, probing, verification, and deterministic fallback of a narrow pure-SVG/CSS subset. It is not a claim that every WeChat account and client will run every SVG animation.

Before running a command, resolve the single same-release runtime and external
artifact root through [runtime-location.md](runtime-location.md).

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
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_interaction_policy.py" candidate.html \
  --fallback fallback.html \
  --output interaction-policy-report.json
```

An `ok: true`, `status: candidate` result means the source and fallback satisfy the fixed syntax policy. It does not authorize the dynamic payload. Until certification completes, `recommended_payload` remains `static-fallback`.

## Draft readback

Upload body images first, compile SVG image references to the returned WeChat URLs, save the candidate to one draft, and immediately retrieve the saved body. Re-run:

The first ordinary session compile intentionally selects static when no mobile profile exists. After saving that baseline, bootstrap sanitizer/mobile evidence by compiling a separate, fresh-live-root probe:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" \
  --transport-fidelity HANDOFF_JSON --live-root-export PROBE_LIVE_ROOT_JSON \
  --upload-map DELIVERY/upload-map.json --session-draft --interaction-probe \
  --output DELIVERY/interaction-probe --check
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 save-draft HANDOFF_JSON \
  DELIVERY/interaction-probe/candidate-report.json \
  --target-account appid:EXACT_APPID
```

`current-session-interaction-probe` can only update the already mapped draft. It cannot create a draft, satisfy publication preflight, or be published. Reopen it through the active host callback, capture the real saved body and iOS/Android evidence, then compile a normal `current-session-draft` with the bound readback/profile/host trace. Update and reopen the same draft once more before considering dynamic delivery.

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_interaction_policy.py" candidate.html \
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
  "schema_version": 2,
  "source": "wechat-host-mobile-compatibility-profile-v2",
  "signature_algorithm": null,
  "assurance_scope": "current-session-live",
  "key_id": null,
  "nonce": "32-to-64-lowercase-hex",
  "policy_version": "wechat-svg-smil-self-v1",
  "status": "passed",
  "target_account_id": "...",
  "draft_id": "...",
  "probe_sha256": "sha256:exact-candidate-bytes",
  "readback_sha256": "sha256:exact-saved-draft-body-bytes",
  "verified_at": "RFC3339",
  "valid_until": "RFC3339",
  "clients": [
    {
      "platform": "ios",
      "wechat_version": "...",
      "result": "passed",
      "preview_evidence": {
        "path": "ios-preview.png",
        "sha256": "sha256:...",
        "byte_length": 123,
        "captured_at": "RFC3339 with timezone",
        "device_session_id": "actual-ios-preview-session"
      }
    },
    {
      "platform": "android",
      "wechat_version": "...",
      "result": "passed",
      "preview_evidence": {
        "path": "android-preview.png",
        "sha256": "sha256:...",
        "byte_length": 123,
        "captured_at": "RFC3339 with timezone",
        "device_session_id": "actual-android-preview-session"
      }
    }
  ],
  "host_session_id": "current-host-session",
  "host_trace_sha256": "sha256:current-host-trace",
  "signature": null
}
```

For `current-session-live`, the standalone validator can check the profile's structure, exact candidate/readback hashes, target account/draft, real PNG bytes, freshness and distinct iOS/Android device sessions, but it intentionally exposes no CLI switch that turns those serialized files into live authority. Dynamic selection additionally requires an isolated trusted embedding harness to pass a fresh in-process `CurrentSessionMobileAuthority.authorize_mobile_evidence` response bound to every profile, account, draft, candidate, readback, host-session, device-session and evidence hash. A hand-written trace/profile, command-line Boolean, or ordinary repository Python object is not independent evidence and cannot unlock dynamic output in the standalone process. For `portable-signed`, the same exact client evidence is Ed25519-signed by the host trust root, `signature_algorithm/key_id/signature` are populated, and current-session host fields remain signed facts. Without either the isolated harness callback or portable signature, select static.

Invalidate or re-probe when the policy version, target account, sanitizer behavior, or relevant WeChat client behavior changes. A `pending`, failed, expired, mismatched, or incomplete profile must select the static fallback and update the same draft rather than creating a duplicate.

## Cover is a separate gate

SVG does not solve the cover field. The official route must upload the current cover through permanent material and set the returned target-account `media_id` as `thumb_media_id`. Body-image URLs, SVG image URLs, and another account's material IDs cannot substitute for it. Browser fallback is complete only when the visible draft shows the actual cover after saving and reopening.
