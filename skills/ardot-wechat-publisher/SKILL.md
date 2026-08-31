---
name: ardot-wechat-publisher
description: Deliver a user-reviewed, already-designed Ardot WeChat article into a target WeChat Official Account draft, verify the imported result, and publish only after explicit confirmation. Use only for the last mile from an existing final Ardot article; do not research, rewrite, generate visuals, recalibrate branding, or redo layout.
---

# Ardot WeChat Publisher

Treat the current reviewed Ardot article as the visual and editorial source of truth. This skill begins after the user has finished editing in Ardot and ends with a verified WeChat draft or, when separately authorized, a published article.

## Mandatory delivery preflight

Use this repository copy of the publisher Skill, not a stale installed copy. Resolve the repository root that contains both `scripts/runtime_preflight.py` and [the runtime contract](../../references/runtime-preflight.md); if that root is unavailable, stop instead of guessing relative paths. Build a fresh current-session profile, run the credential-free binding gate from that root before opening either external link, then make real host-owned read-only calls against the exact current Ardot root and visible target WeChat account/API identity:

```bash
python3 scripts/runtime_preflight.py output/runtime/runtime-profile.json \
  --phase delivery --binding-only \
  --output output/runtime/delivery-preflight-report-UNIQUE.json
```

Stop unless `ok` and `binding_ready` are both true. `phase_ready: false` is expected because the local validator cannot authenticate its own profile. Execute `host_setup_actions` immediately: prepare the selected Ardot route (MCP connect/OAuth or the declared UI fallback), open/read the exact reviewed Ardot root, keep image inspection blocking, and prepare the selected WeChat route before compiling or uploading anything. The API route authorizes its publisher provider; only the UI route opens the credential-free WeChat base and requests QR login. Ardot MCP OAuth and web login are separate; if a login/authorization page appears, leave the safe page open, tell the user which login is needed, wait, and then re-probe without persisting the token-bearing redirect URL. Continue only after the current host tool trace shows: repository publisher Skill path/hash loaded; current Ardot file and exact article root read successfully; write/export callables present in the same provider/session; target WeChat account matched with draft read/write access. Do not reuse an authoring/startup report, trust a self-reported profile, or treat a Browser/Computer Use listing as a successful login probe. This preflight is read-only and does not authorize draft creation or publication.

## Hard scope boundary

- Do not open or create a shared document.
- Do not research the organization, rewrite copy, generate images, change art direction, build an organization pack, or redesign the article.
- Do not inspect an older article, example, PDF, HTML export, `article.json`, or screenshot as a substitute for the current Ardot state.
- Make only transport-required changes. Report every such change, including removed unsupported markup, compressed images, or a component fallback.
- If the user requests upstream changes, hand that work to the relevant authoring workflow; do not silently expand this skill.

## Required handoff

Obtain or resolve these values before transmitting content:

- current Ardot file or design identifier;
- exact final article root node or frame;
- title, digest, body text, body images, and cover from that current root;
- handoff schema v4 workflow-attribution evidence from the current root: policy `tuozhe-ai-ecosystem-workflow-v1`, exact text `感谢拓浙 AI 生态提供本篇内容生产工作流支持。`, its text SHA-256, Ardot node/component, and derived native-editable/visible/terminal order; refreeze legacy v3 rather than exempting it;
- public watermark evidence for every eligible generated raster carrier, including final pixel SHA, report hash, key identifier, and `local_verified` status; never request or copy the private watermark-ID registry into the handoff;
- closed/open/static-fallback Ardot nodes for every requested non-static component;
- target WeChat Official Account identity;
- desired terminal state: verified draft by default, publication only when explicitly requested.

Read [references/handoff-contract.md](references/handoff-contract.md) when extracting or validating the Ardot handoff. If the current Ardot state cannot be read, stop and ask the user to open the final design or provide a current export. Never fall back to a stale local artifact without the user choosing it.

## Delivery route

Prefer the official WeChat server API. Use browser editing only as a declared fallback when API credentials or permissions are unavailable.

### 1. Freeze the reviewed revision

- Read the current Ardot root, not an upstream content file.
- Record file/design ID, root node ID, capture time, and `ardot-root-revision-v1`. Recompute the revision from the current root's full normalized visible-text order, complete component order, asset ID/SHA map, file ID, and root ID; two matching self-reported strings are not evidence.
- Capture current Ardot screenshot evidence for the article root. Closed, open/completed, and static-fallback state screenshots are mandatory before enabling any non-static component.
- Extract native text and asset references. Do not flatten the entire article into one long image.
- Resolve the fixed workflow attribution from the current root and include its node, exact text, and final reading-order position in the revision hash. Reject a hidden, rasterized, duplicated, changed, or non-terminal credit; do not trust self-reported Boolean fields without the current-root export.
- Run `python3 scripts/validate_workflow_attribution.py HANDOFF_JSON` against the hashed current-root node export before compiling or transmitting. A Markdown contract or manifest expected-field list is not evidence.

### 2. Compile transport artifacts

- Produce WeChat-safe inline HTML from the frozen Ardot revision.
- Preserve reading order, typography hierarchy, images, and component meaning.
- Remove JavaScript and external stylesheet dependencies.
- Keep a static equivalent for every non-static component. Never silently lose information when degrading an interaction.
- For any interaction, read [references/wechat-interaction-capability.md](references/wechat-interaction-capability.md). Enforce policy `wechat-svg-smil-self-v1` with the repository validator. Only no-ID self-trigger `<set>` / `<animateTransform begin="click">` and inline CSS horizontal swipe may enter a candidate; JavaScript, `<details>`, every transport `id`, cross-ID timing, fragment references, and unprobed SMIL are blocking.
- Bind each dynamic/static pair with the same `data-fallback-key` and normalized `data-fallback-hash`. A candidate without a complete static fallback is invalid.
- Generate a delivery manifest that binds the HTML and every exported asset to the same Ardot revision hash.
- Preserve eligible marked image bytes and their public evidence. Do not add the first watermark, re-embed, or overwrite an unmarked/marked asset in the publisher.

### 3. Preflight the target account

- Show the resolved target account name before any write.
- Confirm that the account has the required draft, material, and publishing permissions.
- Retrieve secrets from the configured secret store or authorization provider. Never place AppSecret, access tokens, or authorization tokens in the organization pack, article directory, logs, or Git.
- Retrieve the watermark detector key from the same external secret boundary when the handoff contains locally verified carriers. It is at least 32 random bytes and enters the local detector only as `hex:` or `base64:` material. Never expose the key or raw watermark ID in the delivery manifest or logs.
- For API details and permission sets, read [references/wechat-api-delivery.md](references/wechat-api-delivery.md).

### 4. Create or update a draft

- Upload body images through the WeChat article-image endpoint and replace all local or external image URLs with returned WeChat URLs.
- Upload the cover through the permanent-material flow and use its `thumb_media_id`.
- Block draft add/update when `thumb_media_id` is absent. A body-image URL, an SVG image URL, or another account's material ID is not a cover.
- Compute an idempotency key from target account ID plus Ardot revision hash. Reuse and update the mapped draft when possible; do not create duplicate drafts on retries.
- Create or update the draft using the compiled title, digest, content, author settings, cover, and other approved article settings.

### 5. Read back and verify

- Immediately retrieve the saved draft from WeChat.
- Compare title, digest, text order, image count and URLs, cover, and expected component markers with the delivery manifest.
- Export the reopened saved draft's actual visible body text, then rerun `validate_workflow_attribution.py` with `--saved-draft-visible-text FILE --require-readback`. Require exactly one occurrence and require it to be terminal. Treat the `data-workflow-attribution` marker as a diagnostic only; WeChat may remove it.
- Verify the actual saved cover as well as `thumb_media_id`; missing cover evidence is a failed draft verification.
- Download each locally verified carrier from the actual returned `mmbiz.qpic.cn` body URL or saved cover derivative and run authenticated pixel detection. Bind the detector result to the downloaded byte SHA-256, byte length, format, dimensions, expected payload fingerprint, and asset ID; record no raw watermark ID. `payload_authenticated` means only that the HMAC payload survived—it is not a copyright/authorship verdict. HTML/image-count readback is not watermark evidence; required-mode delivery cannot advance to publication until every required carrier is `transport_verified`.
- Detect the complete hosted body/cover object. V1 does not promise recovery from a cropped screenshot, added borders, rotation, perspective, or a partial phone capture. If WeChat creates a geometrically cropped cover derivative, test that actual derivative and block required-mode publication when it fails.
- For policy-compliant SVG/SMIL or CSS swipe, run structure-signature readback and require an unexpired capability profile matching this target account, policy version, and both iOS and Android preview evidence. Readback alone is never mobile runtime proof.
- If the sanitizer changes a marker, fallback hash, SMIL signature, image URL, or content order—or the mobile profile is absent, pending, failed, expired, or mismatched—update the same draft with its information-equivalent static fallback and read it back again.
- Do not call the handoff complete until the returned draft is coherent and all required content is present.

### 6. Stop at the requested terminal state

- Default result: verified draft in the target account, with draft ID, revision hash, cover evidence, interaction policy/status, selected dynamic or fallback payload, verification report, and a clear preview/open path.
- Formal publication requires a fresh explicit confirmation naming the target account and article. Submission success is not publication success; poll the publication-status endpoint until a terminal result and return the permanent article URL.
- Group send is separate from publication and always requires its own explicit confirmation. Never infer group-send permission from a request to import, save, or publish.

## Browser fallback

Use browser fallback only when the official API path is unavailable and the user still asks to continue.

- Confirm the visible logged-in account before entering content.
- Copy from the frozen current-revision transport artifact, not from a previous clipboard or old experiment output.
- Import title, digest, rich body, images, and cover; verify the editor after paste.
- Confirm in the real body editor and after reopening the draft that the exact fixed attribution remains the final visible text.
- Save and reopen the draft to verify the actual cover. Do not report a complete import while the cover remains empty or only exists as a body image.
- Browser readback may establish structure preservation, but dynamic eligibility still requires the matching iOS/Android capability profile defined in the interaction reference.
- Save as draft only. Do not press **发表** or initiate group send without the separate authorization above.
- If the editor hangs, sanitizes the content, or cannot verify the pasted result, stop and report an incomplete import. Never claim that a draft exists without authoritative UI or API evidence.

## Completion report

Return only the last-mile facts that help the user verify delivery:

- target account;
- Ardot file/root and revision hash;
- draft ID or publication ID and permanent URL when applicable;
- whether official API or browser fallback was used;
- readback/preview result;
- cover verification and interaction policy/profile status;
- watermark transport status for each eligible generated carrier, distinguishing `local_verified`, `transport_verified`, and `transport_lost`;
- any transport changes or static fallbacks;
- any unresolved blocker.
