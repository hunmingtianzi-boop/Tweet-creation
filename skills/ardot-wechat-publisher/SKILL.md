---
name: ardot-wechat-publisher
description: Deliver a user-reviewed, already-designed Ardot WeChat article into a target WeChat Official Account draft, verify the imported result, and publish only after explicit confirmation. Use only for the last mile from an existing final Ardot article; do not research, rewrite, generate visuals, recalibrate branding, or redo layout.
---

# Ardot WeChat Publisher

Treat the current reviewed Ardot article as the visual and editorial source of truth. This skill begins after the user has finished editing in Ardot and ends with a verified WeChat draft or, when separately authorized, a published article.

## Mandatory delivery preflight

Use this repository copy of the publisher Skill, not a stale installed copy. Resolve the repository root that contains both `scripts/runtime_preflight.py` and [the runtime contract](../../references/runtime-preflight.md); if that root is unavailable, stop instead of guessing relative paths. Build a fresh current-session profile, run the credential-free binding gate from that root before opening either external link, then make real host-owned read-only calls against the exact current Ardot root and visible target WeChat account/API identity:

```bash
python3 -I -S scripts/secure_runner.py scripts/runtime_preflight.py output/runtime/runtime-profile.json \
  --phase delivery --binding-only \
  --output output/runtime/delivery-preflight-report-UNIQUE.json
```

The `-I -S` secure runner is mandatory for preflight, transport validation/compilation, and hosted-asset watermark verification. Direct `python3 scripts/...`, `PYTHONPATH`, site hooks, and unlocked dependency roots are blockers; a new harness platform must add reviewed distribution hashes to `runtime/python-dependency-lock.json` before delivery.

Stop unless `ok` and `binding_ready` are both true. `phase_ready: false` is expected because the local validator cannot authenticate its own profile. Execute `host_setup_actions` immediately: prepare the selected Ardot route (MCP connect/OAuth or the declared UI fallback), open/read the exact reviewed Ardot root, keep image inspection blocking, and prepare the selected WeChat route before compiling or uploading anything. The API route authorizes its publisher provider; only the UI route opens the credential-free WeChat base and requests QR login. Ardot MCP OAuth and web login are separate; if a login/authorization page appears, leave the safe page open, tell the user which login is needed, wait, and then re-probe without persisting the token-bearing redirect URL. Continue only after the current host tool trace shows: repository publisher Skill path/hash loaded; current Ardot file and exact article root read successfully; write/export callables present in the same provider/session; target WeChat account matched with draft read/write access. Do not reuse an authoring/startup report, trust a self-reported profile, or treat a Browser/Computer Use listing as a successful login probe. This preflight is read-only and does not authorize draft creation or publication.

`host.receipt.attest` is an optional assurance upgrade, not a draft-write prerequisite. If the current harness exposes it, select `portable-signed-audit` and keep the signed finalization chain below. If it is absent, require preflight mode `current-session-draft`: the active task must itself own the visible Ardot reread and WeChat write/readback trace, use the unsigned session-candidate commands below, and report `portable_audit_verified=false`. Missing attestation alone must never be relabeled as a login failure, but unsigned mode cannot authorize publication, group send, or a portable proof claim.

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
- handoff schema v5 workflow-attribution evidence from the current root: policy `tuozhe-ai-ecosystem-workflow-v1`, exact text `感谢拓浙 AI 生态提供本篇内容生产工作流支持。`, its text SHA-256, Ardot node/component, and derived native-editable/visible/terminal order; refreeze every older bundle rather than exempting it;
- a hash-bound `ardot-current-root-layer-export-v1` transport-fidelity export from that same root: continuous article-root chapter geometry, an exact current-root `transport_sections`/body-asset census, source-node identity for every layer instance, approved WeChat-native font and render styles, complete `1170 x (chapter_height * 3)` zero-text backgrounds, independent approved cutouts/photos, actual Ardot interaction-state exports plus fallbacks, and one exact-height 390 px reference screenshot per chapter;
- public watermark evidence for every eligible generated raster carrier, including final pixel SHA, report hash, key identifier, and `local_verified` status; never request or copy the private watermark-ID registry into the handoff;
- closed/open/static-fallback Ardot nodes for every requested non-static component;
- target WeChat Official Account identity;
- desired terminal state: saved and reopened draft with an explicit assurance label by default; publication only when separately requested and the portable signed-audit chain is available.

Read [references/handoff-contract.md](references/handoff-contract.md) when extracting or validating the Ardot handoff. If the current Ardot state cannot be read, stop and ask the user to open the final design or provide a current export. Never fall back to a stale local artifact without the user choosing it.

## Delivery route

Prefer the official WeChat server API. Use browser editing only as a declared fallback when API credentials or permissions are unavailable.

### 1. Freeze the reviewed revision

- Read the current Ardot root, not an upstream content file.
- Record file/design ID, root node ID, capture time, and `ardot-root-revision-v1`. Recompute the revision from the current root's full normalized visible-text order, complete component order, exact `transport_sections` source-node/style census, exact `body_asset_ids`, asset ID/SHA map, file ID, and root ID; two matching self-reported strings are not evidence.
- Capture current Ardot screenshot evidence for the article root. Closed, open/completed, and static-fallback state screenshots are mandatory before enabling any non-static component.
- Extract native text and asset references. Do not flatten the entire article into one long image.
- Freeze the complete chapter layer export and its `ardot-transport-revision-v1` hash. Re-read the current root through the active Ardot host immediately before compile and save a separate fresh export with a timezone-aware `captured_at` strictly later than freeze and different bytes/inode; never rename, copy, hard-link or otherwise reuse frozen evidence as live proof. In `portable-signed-audit` mode, require a real `host.receipt.attest` callable and its short-lived `ardot-host-live-read-receipt-v1`, Ed25519-signed with a host-only private key. Verify it only against the public key in a root-owned, non-symlink, group/other-nonwritable trust-store file; `ORG_WECHAT_HOST_RECEIPT_TRUST_STORE` may select that protected absolute path, while a raw environment public key is forbidden. It must bind the runtime digest/nonce, trusted bundle, actual provider/session/request and intended final HTML path. In `current-session-draft` mode, bind the exact fresh export path identity, device/inode, SHA-256 and bytes into `candidate-report.json`, while the current host trace supplies origin evidence. An unsigned JSON or model-written receipt can never upgrade either mode into portable audit. The ordinary article JSON and any HTML previously rendered from block templates are semantic/authoring inputs only; they cannot become a delivery payload.
- Do not admit an Ardot section screenshot, QA image, review contact sheet, or section composite into the body. A complex surface is exported as a text-free 3x background; documentary photos and true-alpha cutouts remain independent layers, and every cutout keeps its approved asset ID/SHA.
- Resolve the fixed workflow attribution from the current root and include its node, exact text, and final reading-order position in the revision hash. Reject a hidden, rasterized, duplicated, changed, or non-terminal credit; do not trust self-reported Boolean fields without the current-root export.
- Run `python3 scripts/validate_workflow_attribution.py HANDOFF_JSON` against the hashed current-root node export before compiling or transmitting. A Markdown contract or manifest expected-field list is not evidence.

### 2. Compile transport artifacts

- For `portable-signed-audit`, run `python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py HANDOFF_JSON --intended-html OUTPUT/wechat.html --live-root-export LIVE_ROOT_JSON --live-root-receipt LIVE_RECEIPT_JSON --require-live-root`, then `python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py --transport-fidelity HANDOFF_JSON --live-root-export LIVE_ROOT_JSON --live-root-receipt LIVE_RECEIPT_JSON --output OUTPUT --check`. The receipt must be issued and Ed25519-signed by the harness from the actual Ardot tool response; the repository has no signing key and must never fabricate it.
- For `current-session-draft`, run `python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py HANDOFF_JSON --intended-html OUTPUT/wechat-candidate.html --live-root-export LIVE_ROOT_JSON --require-live-root --session-draft`, then `python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py --transport-fidelity HANDOFF_JSON --live-root-export LIVE_ROOT_JSON --session-draft --output OUTPUT --check`. Require `candidate_valid=true`, `draft_write_eligible=false`, `delivery_eligible=false`, and `portable_audit_verified=false`. The unsigned report is a structural binding only; it never grants a portable write entitlement. The active task may paste/upload only this exact candidate as a reversible current-host action while it owns the visible Ardot reread and WeChat trace. Never call the article-JSON renderer for delivery; `--authoring-preview` is explicitly non-delivery.
- Map every top-level chapter one-to-one from its frozen Ardot section node. Preserve native text order/style/geometry, exact independent asset hashes, text-free background crop, and interaction state. No manually chosen `padding`, color surface, role-width constant, screenshot splice, or freehand SVG may replace the frozen data.
- Remove JavaScript and external stylesheet dependencies.
- Keep a static equivalent for every non-static component. Never silently lose information when degrading an interaction.
- For any interaction, read [references/wechat-interaction-capability.md](references/wechat-interaction-capability.md). Enforce policy `wechat-svg-smil-self-v1` with the repository validator. Only no-ID self-trigger `<set>` / `<animateTransform begin="click">` and inline CSS horizontal swipe may enter a candidate; JavaScript, `<details>`, every transport `id`, cross-ID timing, fragment references, and unprobed SMIL are blocking.
- Bind each dynamic/static pair with the same `data-fallback-key` and normalized `data-fallback-hash`. A candidate without a complete static fallback is invalid.
- Immediately before upload/copy/paste, validate the exact compiled artifact again. Signed mode requires `compile-report.json.artifact_binding.wechat_html`, `artifact_binding.live_root_export`, and `artifact_binding.live_root_receipt`, then reruns the validator with `OUTPUT/wechat.html`, both live artifacts, and `--require-compile-report`. Session mode requires `candidate-report.json.artifact_binding.candidate_html`, the exact `artifact_binding.live_root_export`, a null receipt binding, and reruns with `OUTPUT/wechat-candidate.html`, `LIVE_ROOT_JSON`, `OUTPUT/candidate-report.json`, `--require-compile-report --session-draft`. Copying the directory, rewriting either report, or changing/substituting the HTML or live export invalidates the binding.
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
- Export `wechat-saved-draft-readback-v1` with target account, draft ID, observation time and one entry per frozen chapter: section mapping, normalized visible-text-node IDs/hash, all hosted asset IDs plus downloaded files whose SHA-256 is recomputed, and a hash-bound `390 × chapter_height` reopened-draft screenshot. Resolve the exact target-account reference from the active delivery preflight, not from the readback's self-report, and pass it as `--expected-target-account EXACT_ACCOUNT_FROM_ACTIVE_PREFLIGHT`. Signed mode also requires `wechat-host-saved-draft-receipt-v1` and reruns the validator with `OUTPUT/wechat.html`, both receipts, `OUTPUT/compile-report.json`, and `--require-readback`. Session mode reruns with `OUTPUT/wechat-candidate.html`, the exact live export, `OUTPUT/candidate-report.json`, `--require-compile-report --expected-target-account EXACT_ACCOUNT_FROM_ACTIVE_PREFLIGHT --readback READBACK_JSON --require-readback --session-draft`; require `session_readback_structural_match=true` while keeping `portable_audit_verified=false`. The current task must visibly reopen the draft and own that readback trace. Local files or plausible WeChat URLs alone prove neither external origin nor publication.
- If the sanitizer changes a marker, fallback hash, SMIL signature, image URL, or content order—or the mobile profile is absent, pending, failed, expired, or mismatched—update the same draft with its information-equivalent static fallback and read it back again.
- Do not call the handoff complete until the returned draft is coherent and all required content is present.

### 6. Stop at the requested terminal state

- Default result: a saved and reopened draft in the target account, with draft ID, revision hash, cover evidence, interaction policy/status, selected dynamic or fallback payload, verification report, a clear preview/open path, and an explicit assurance label. Say `portable signed audit verified` only when both host receipts pass; otherwise say `current-session draft structurally verified; portable_audit_verified=false`.
- Formal publication requires both a passing `portable-signed-audit` chain and a fresh explicit confirmation naming the target account and article. Current-session unsigned mode stops at the saved/reopened draft even if publication was requested; explain that the missing signer blocks only that irreversible step. Submission success is not publication success; poll the publication-status endpoint until a terminal result and return the permanent article URL.
- Group send is separate from publication and always requires its own explicit confirmation. Never infer group-send permission from a request to import, save, or publish.

## Browser fallback

Use browser fallback only when the official API path is unavailable and the user still asks to continue.

- Confirm the visible logged-in account before entering content.
- Copy only from the validated frozen-layer artifact selected for this assurance mode: signed `wechat.html` or unsigned `wechat-candidate.html`. Never use an article-JSON authoring preview, previous clipboard, screenshot splice, or old experiment output.
- Import title, digest, rich body, images, and cover; verify the editor after paste.
- Confirm in the real body editor and after reopening the draft that the exact fixed attribution remains the final visible text.
- Save and reopen the draft to verify the actual cover. Do not report a complete import while the cover remains empty or only exists as a body image.
- Browser readback still requires the chapter-by-chapter `wechat-saved-draft-readback-v1` evidence and transport-fidelity validator; it may establish structure preservation, but dynamic eligibility still requires the matching iOS/Android capability profile defined in the interaction reference.
- Save as draft only. Unsigned current-session mode never presses **发表** or initiates group send. Signed mode still requires the separate authorization above.
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
