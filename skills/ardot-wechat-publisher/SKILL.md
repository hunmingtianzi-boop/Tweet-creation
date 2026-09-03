---
name: ardot-wechat-publisher
description: On Codex Desktop only, deliver a user-reviewed, already-designed Ardot WeChat article into a target WeChat Official Account draft, verify the imported result, and publish only after explicit confirmation. Use only for the last mile from an existing final Ardot article; do not use from another harness or research, rewrite, generate visuals, recalibrate branding, or redo layout.
---

# Ardot WeChat Publisher

Treat the current reviewed Ardot article as the visual and editorial source of truth. This skill begins after the user has finished editing in Ardot and ends with a verified WeChat draft or, when separately authorized, a published article.

This executable publisher supports Codex Desktop only. At the start, state that
the same-release three workflow Skills, the locked platform, an active Ardot
Remote connection/login with permission for the exact final file/root, and the
exact target WeChat account login or execution-time API route are required.
Ardot MCP OAuth and Ardot web login are separate; verify both only when the
selected route needs them. A clone, old profile, open homepage, saved Cookie or
similarly named tool in another harness proves none of these conditions. Stop
before upload or draft mutation until the current Codex session closes every
required live probe.

## Mandatory delivery preflight

Use the exact loaded publisher Skill after verifying it against the installed release manifest; a repository checkout is not proof of what the harness loaded. First read [the installed runtime location contract](references/runtime-location.md), resolve the same-release sibling `org-wechat-studio` as `ORG_WECHAT_RUNTIME_ROOT`, keep the user's project as the working directory, and invoke every shared script by its absolute path. The shared runtime contract is `ORG_WECHAT_RUNTIME_ROOT/references/runtime-preflight.md`; stop if the sibling or release bytes do not verify. Build a fresh current-session profile before opening either external link, then make real read-only calls against the exact current Ardot root and visible target WeChat account/API identity. Current Codex Desktop has no `host.registry.export` callable, so initialize its census from only the tool IDs actually visible in the current model registry:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \
  init-current-session-census \
  --phase delivery --session-id CURRENT_HOST_SESSION_ID \
  --visible-tool-id EACH_ACTUALLY_VISIBLE_DELIVERY_TOOL_ID \
  --skills-root /ABSOLUTE/INSTALLED/SKILLS/ROOT \
  --release-manifest /ABSOLUTE/INSTALLED/SKILLS/ROOT/.org-wechat-release-manifests/RELEASE_SHA.json \
  --output "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json"
```

`build-census` remains a future adapter-development contract, not a supported
end-user route in this release. Continue with the Codex current-session census:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" init-profile \
  "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json" \
  "$ORG_WECHAT_SESSION_ROOT/delivery-target.json" \
  --phase delivery --output "$ORG_WECHAT_SESSION_ROOT/delivery-profile-UNIQUE.json"

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \
  "$ORG_WECHAT_SESSION_ROOT/delivery-profile-UNIQUE.json" \
  --phase delivery --binding-only \
  --output "$ORG_WECHAT_SESSION_ROOT/delivery-preflight-report-UNIQUE.json"
```

The `-I -S` secure runner is mandatory for preflight, transport validation/compilation, and hosted-asset watermark verification. Direct `python3 scripts/...`, `PYTHONPATH`, site hooks, and unlocked dependency roots are blockers. No other harness/platform may deliver until a reviewed adapter, login routes, full forward test and locked release are shipped.

Stop unless `ok` and `binding_ready` are both true. `phase_ready: false` is expected because the local validator cannot authenticate its own profile. Execute `host_setup_actions` immediately: prepare the selected Ardot route (MCP connect/OAuth or the declared UI fallback), open/read the exact reviewed Ardot root, keep image inspection blocking, and prepare the selected WeChat route before compiling or uploading anything. The API route authorizes its publisher provider; only the UI route opens the credential-free WeChat base and requests QR login. Ardot MCP OAuth and web login are separate; if a login/authorization page appears, leave the safe page open, tell the user which login is needed, wait, and then re-probe without persisting the token-bearing redirect URL. Continue only after the current host tool trace shows: repository publisher Skill path/hash loaded; current Ardot file and exact article root read successfully; write/export callables present in the same provider/session; target WeChat account matched with draft read/write access. Do not reuse an authoring/startup report, trust a self-reported profile, or treat a Browser/Computer Use listing as a successful login probe. This preflight is read-only and does not authorize draft creation or publication.

Keep four Ardot facts separate: local MCP configuration, current-task tool
injection, same-session OAuth/exact-root read access, and the outcome of each
remote mutation. `codex mcp list/get` proves only the first. If the route is
configured but the current task lacks the required tool IDs, reload/open a new
Codex task; this repository cannot hot-inject them. For a non-idempotent
`create_design`, bind a unique nonce/title before calling. Timeout, 5xx, or a
truncated response means `create-unknown`: never retry blindly. Reconcile via
read-only discovery or the user's Ardot UI first and create again only after
absence is established.

Treat `wechat.draft` and `wechat.current_session.publish.authority` as separate capabilities. The local publisher entrypoint may prove draft API availability, but it must never be promoted into a live publication authority. If the census/profile does not expose the latter as a real host callable, report that API draft work is available while file-only current-session API publication is unavailable; the formal alternatives are portable signed publication or an explicitly declared live UI route.

`host.receipt.attest` is an optional portable-assurance upgrade, not a prerequisite for draft creation. If the current harness exposes it, select `portable-signed-audit`. Without it, `current-session-live` draft creation/readback remains available and must report `portable_audit_verified=false`. The checked-in Codex adapter exposes the separate `wechat.current-session-readback` Browser capture route, and the standalone publisher accepts its create-once bundle through `--capture-bundle`; neither is publication authority. API publication is narrower: the `CurrentSessionHostAuthority` object is only a non-cryptographic trusted-harness policy hook, valid only in an isolated embedding harness that does not execute model-controlled Python inside the hook's trust boundary. The checked-in Codex adapter does not expose that publication hook and the standalone CLI injects `None`; use the separately declared UI live route after fresh confirmation, or a portable signed API route. Group send remains a separate action and confirmation.

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
- desired terminal state: saved and reopened draft with an explicit assurance label by default; publication only when separately requested, freshly confirmed, and authoritatively read back to a terminal status in the same live session or a portable signed chain.

Read [references/handoff-contract.md](references/handoff-contract.md) when extracting or validating the Ardot handoff. If the current Ardot state cannot be read, stop and ask the user to open the final design or provide a current export. Never fall back to a stale local artifact without the user choosing it.

## Delivery route

Prefer the official WeChat server API. Use browser editing only as a declared fallback when API credentials or permissions are unavailable.

### 1. Freeze the reviewed revision

- Read the current Ardot root, not an upstream content file.
- Record file/design ID, root node ID, capture time, and `ardot-root-revision-v1`. Recompute the revision from the current root's full normalized visible-text order, complete component order, exact `transport_sections` source-node/style census, exact `body_asset_ids`, asset ID/SHA map, file ID, and root ID; two matching self-reported strings are not evidence.
- Capture current Ardot screenshot evidence for the article root. Closed, open/completed, and static-fallback state screenshots are mandatory before enabling any non-static component.
- Extract native text and asset references. Do not flatten the entire article into one long image.
- Freeze the complete chapter layer export and its `ardot-transport-revision-v1` hash. Re-read the current root through the active Ardot host immediately before compile and save a separate fresh export with a timezone-aware `captured_at` strictly later than freeze and different bytes/inode; never rename, copy, hard-link or otherwise reuse frozen evidence as live proof. In `portable-signed-audit` mode, require a real `host.receipt.attest` callable and its short-lived `ardot-host-live-read-receipt-v1`, Ed25519-signed with a host-only private key. Verify it only against the public key in a root-owned, non-symlink, group/other-nonwritable trust-store file; `ORG_WECHAT_HOST_RECEIPT_TRUST_STORE` may select that protected absolute path, while a raw environment public key is forbidden. It must bind the runtime digest/nonce, trusted bundle, actual provider/session/request and intended final HTML path. In `current-session-draft` mode, bind the exact fresh export path identity, device/inode, SHA-256 and bytes into `candidate-report.json`, while the current host trace supplies origin evidence. An unsigned JSON or model-written receipt can never upgrade either mode into portable audit. The ordinary article JSON and any HTML previously rendered from block templates are semantic/authoring inputs only; they cannot become a delivery payload.
- Feed only the host adapter's normalized current-root export into the deterministic exporter. The output directory must be new; the exporter refuses overwrite, symlink, non-regular, collision, stale capture, and non-terminal attribution inputs:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/export_ardot_handoff.py" \
  ARDOT_NORMALIZED_CURRENT_ROOT.json --output FREEZE_DIR
```

  Use `FREEZE_DIR/handoff.json`; `qa/readback-skeleton.json` is a capture checklist explicitly marked non-evidence and can never satisfy readback.
- Do not admit an Ardot section screenshot, QA image, review contact sheet, or section composite into the body. A complex surface is exported as a text-free 3x background; documentary photos and true-alpha cutouts remain independent layers, and every cutout keeps its approved asset ID/SHA.
- Resolve the fixed workflow attribution from the current root and include its node, exact text, and final reading-order position in the revision hash. Reject a hidden, rasterized, duplicated, changed, or non-terminal credit; do not trust self-reported Boolean fields without the current-root export.
- Run `python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_workflow_attribution.py" HANDOFF_JSON` against the hashed current-root node export before compiling or transmitting. A Markdown contract or manifest expected-field list is not evidence.

### 2. Preflight the target account and upload exact assets

- Show and bind the exact target account before any mutation. The official API preflight must successfully read both `draft/count` and `material/get_materialcount`; it must not infer upload, draft-write, or free-publish permission from a generic token call.
- Run the repository-local read-only preflight before `prepare-uploads`; a
  same-named MCP connector is not required for this API client:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 preflight-account \
  --target-account appid:EXACT_APPID \
  --output DELIVERY/account-preflight.json
```

  The output is create-once, redacted, calls only the two read endpoints, and
  records `mutations_attempted: 0`. It distinguishes missing credentials,
  account mismatch, API reachability, and read permission from the separate UI
  readback route. Passing it still proves no upload, draft write, or publication
  authority.
- Retrieve secrets from the configured secret boundary. Never place AppSecret, access tokens, authorization redirects, watermark detector keys, or raw watermark IDs in the handoff, logs, organization pack, or Git.
- The local API publisher consumes `WECHAT_ACCESS_TOKEN` plus `WECHAT_APP_ID` at execution. It does not implement AppSecret-to-token exchange; a separate secret/token provider must perform that step without writing credentials into any workflow artifact.
- Upload every body raster with `media/uploadimg`. Accept only matching PNG/JPEG extension, MIME, magic bytes, valid pixels, and strictly less than 1 MB. Record the returned `mmbiz.qpic.cn` URL against the exact frozen source SHA.
- Upload the cover as permanent `type=image` material. Accept matching BMP/PNG/JPEG/GIF bytes up to 10 MB, and bind the returned permanent `media_id` as `thumb_media_id`; do not confuse this with the 64 KB JPG `type=thumb` constraint.
- Persist one atomic `wechat-account-upload-map-v1` scoped to account, handoff SHA, transport revision, every body source SHA/URL, and cover SHA/media ID. Actual successful upload responses establish write capability; preflight booleans do not.
- `--output` is create-once: its parent must already exist, no path component may traverse a user-created symlink, and an existing map is a hard stop before any upload. The publisher creates `.<output-name>.upload-journal.jsonl` before the first mutation and appends a hash-chained event before/after every body or cover attempt. The journal binds the canonical publisher-store path and its persistent store identity; on resume, every prior committed event must still match one exact SQLite `complete` transaction. If a known failure interrupts the batch, rerun the exact same command, store, and output path: committed SHA/account/kind rows are reused and only known-failed rows may retry. A changed/missing store, missing committed row, or `pending` / `ambiguous` row always stops for operator reconciliation; changing the output path cannot authorize a replay. Never delete, rewrite, or hand-edit the journal/map to force continuation.
- Run only through the isolated runner:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 prepare-uploads HANDOFF_JSON \
  --target-account appid:EXACT_APPID --output DELIVERY/upload-map.json
```

### 3. Compile transport artifacts after upload

- `thumb_media_id` and the complete upload map are hard gates before final/current-session compilation. Final HTML directly consumes those account-hosted URLs. There is no valid post-compile URL-replacement step; changing a URL afterward changes the payload hash and invalidates the report.
- For `portable-signed-audit`, run `python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" HANDOFF_JSON --intended-html OUTPUT/wechat.html --live-root-export LIVE_ROOT_JSON --live-root-receipt LIVE_RECEIPT_JSON --require-live-root --upload-map DELIVERY/upload-map.json --require-upload-map`, then compile with `--live-root-receipt LIVE_RECEIPT_JSON --upload-map DELIVERY/upload-map.json`.
- For `current-session-live`, run the same validator without a receipt, with `--intended-html OUTPUT/wechat-candidate.html --session-draft --upload-map DELIVERY/upload-map.json --require-upload-map`, then compile:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" \
  --transport-fidelity HANDOFF_JSON --live-root-export LIVE_ROOT_JSON \
  --upload-map DELIVERY/upload-map.json --session-draft --output OUTPUT --check
```

  Require `candidate_valid=true`, `draft_write_eligible=false`, `portable_audit_verified=false`, the exact live-root binding, exact upload-map binding, and successful postflight for both payloads. The unsigned report carries no portable authority; the current host may act only while it owns the bound live trace.
- Compilation always emits dynamic and information-equivalent static payloads plus one selected payload. Missing, stale, mismatched, or untrusted mobile evidence selects static. A dynamic selection requires an exact candidate/readback hash, target account/draft, fresh real-PNG iOS and Android preview captures with distinct device sessions, and either a portable host signature or a fresh in-process `CurrentSessionMobileAuthority` response from an isolated trusted embedding harness. Serialized flags, session IDs, Booleans, and host-trace files cannot unlock dynamic output.
- Bootstrap dynamic evidence only after the static candidate has created the mapped draft. Compile `--session-draft --interaction-probe` from a newly captured live root into a separate output, then `save-draft` updates that existing media ID with the dynamic payload. This scope is `current-session-interaction-probe`: it may be reopened for sanitizer/mobile evidence, but it may never create a draft or pass publication preflight. After real iOS/Android evidence exists, either (a) have an isolated trusted embedding harness call the compiler programmatically with the exact mobile profile, readback and an in-process `current_session_mobile_authority`, or (b) use a `portable-signed` mobile profile verified against the protected host trust root. The checked-in standalone CLI intentionally exposes no current-session-authority flags, so it selects the static fallback for an unsigned profile. Update and reopen the same mapped draft; if any gate fails, restore the static payload there instead of creating a duplicate.
- Map every top-level chapter one-to-one from its frozen Ardot section node. Preserve native text order/style/geometry, exact independent asset hashes, text-free background crop, and interaction state. No manually chosen `padding`, color surface, role-width constant, screenshot splice, or freehand SVG may replace the frozen data.
- Remove JavaScript and external stylesheet dependencies.
- Keep a static equivalent for every non-static component. Never silently lose information when degrading an interaction.
- For any interaction, read [references/wechat-interaction-capability.md](references/wechat-interaction-capability.md). Enforce policy `wechat-svg-smil-self-v1` with the repository validator. Only no-ID self-trigger `<set>` / `<animateTransform begin="click">` and inline CSS horizontal swipe may enter a candidate; JavaScript, `<details>`, every transport `id`, cross-ID timing, fragment references, and unprobed SMIL are blocking.
- Bind each dynamic/static pair with the same `data-fallback-key` and normalized `data-fallback-hash`. A candidate without a complete static fallback is invalid.
- Immediately before upload/copy/paste, validate the exact compiled artifact again. Signed mode requires `compile-report.json.artifact_binding.wechat_html`, `artifact_binding.live_root_export`, and `artifact_binding.live_root_receipt`, then reruns the validator with `OUTPUT/wechat.html`, both live artifacts, and `--require-compile-report`. Session mode requires `candidate-report.json.artifact_binding.candidate_html`, the exact `artifact_binding.live_root_export`, a null receipt binding, and reruns with `OUTPUT/wechat-candidate.html`, `LIVE_ROOT_JSON`, `OUTPUT/candidate-report.json`, `--require-compile-report --session-draft`. Copying the directory, rewriting either report, or changing/substituting the HTML or live export invalidates the binding.
- Preserve eligible marked image bytes and their public evidence. Do not add the first watermark, re-embed, or overwrite an unmarked/marked asset in the publisher.

### 4. Create or update a draft

- Enforce official draft gates before the request: title at most 32 characters, author at most 16, digest at most 120, content strictly below 20,000 characters and 1 MB, no JavaScript, only upload-map body URLs, and a permanent `thumb_media_id` at most 128 characters.
- Compute the durable idempotency key from account, Ardot transport revision, and exact payload hash. Reuse/update the mapped draft; never replay an ambiguous non-idempotent mutation or create a duplicate after a crash.
- Save only a validated `current-session-draft` or `portable-signed-draft-candidate` compile report. The sole exception is a validated `current-session-interaction-probe`, which can update but never create the already-mapped draft. Reject authoring previews, diagnostic candidates, hand-written `ok=true`, changed HTML, stale live-root/upload bindings, or failed dual-payload postflight.
- Default command stops at the draft:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 save-draft HANDOFF_JSON OUTPUT/candidate-report.json \
  --target-account appid:EXACT_APPID
```

### 5. Read back and verify

- Immediately retrieve the saved draft from WeChat.
- Compare title, digest, text order, image count and URLs, cover, and expected component markers with the delivery manifest.
- Export the reopened saved draft's actual visible body text, then rerun `validate_workflow_attribution.py` with `--saved-draft-visible-text FILE --require-readback`. Require exactly one occurrence and require it to be terminal. Treat the `data-workflow-attribution` marker as a diagnostic only; WeChat may remove it.
- Verify the actual saved cover as well as `thumb_media_id`; missing cover evidence is a failed draft verification.
- Download each locally verified carrier from the actual returned `mmbiz.qpic.cn` body URL or saved cover derivative and run authenticated pixel detection. Bind the detector result to the downloaded byte SHA-256, byte length, format, dimensions, expected payload fingerprint, and asset ID; record no raw watermark ID. `payload_authenticated` means only that the HMAC payload survived—it is not a copyright/authorship verdict. HTML/image-count readback is not watermark evidence; required-mode delivery cannot advance to publication until every required carrier is `transport_verified`.
- Detect the complete hosted body/cover object. V1 does not promise recovery from a cropped screenshot, added borders, rotation, perspective, or a partial phone capture. If WeChat creates a geometrically cropped cover derivative, test that actual derivative and block required-mode publication when it fails.
- For policy-compliant SVG/SMIL or CSS swipe, run structure-signature readback and require an unexpired capability profile matching this target account, policy version, and both iOS and Android preview evidence. Readback alone is never mobile runtime proof.
- Capture `wechat-saved-draft-readback-v2` only from the real raw `draft/get` response or the declared editor DOM read. Bind request URL/method/status/headers/time/bytes, exact raw content bytes, target account/draft, title/digest/cover, every CDN download and pixel similarity, and one fresh `390 × chapter_height` WeChat screenshot compared with its Ardot reference. A source file, copied source path, plausible CDN string, screenshot-only reconstruction, or hand-written chapter JSON cannot satisfy this gate.
- For a current-session API draft, use this complete create-once chain. Every output parent must already exist outside `ORG_WECHAT_RUNTIME_ROOT` and the installed Skills root; every named output file/directory must still be absent. First retain the authoritative API response:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-raw DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output "$EXTERNAL_READBACK_ROOT/raw-draft-UNIQUE.json"
```

  In the same bound Browser/Computer Use session, reopen the exact saved `DRAFT_MEDIA_ID`, verify the visible account, and capture each frozen chapter as an actual `390 × chapter_height` PNG. The token-bearing navigation URL may exist inside the live browser session but must never be copied to a file, command, report, log, or bundle; persist only a credential-free `https://mp.weixin.qq.com/PATH` with no query or fragment. Then bind the actual PNG bytes, capture times, distinct event IDs, exact API reread, release/census/profile/session and one fresh nonce:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/ingest_wechat_readback_capture.py" \
  HANDOFF_JSON OUTPUT/candidate-report.json \
  "$EXTERNAL_READBACK_ROOT/raw-draft-UNIQUE.json" \
  --runtime-profile "$ORG_WECHAT_SESSION_ROOT/delivery-profile-UNIQUE.json" \
  --runtime-report "$ORG_WECHAT_SESSION_ROOT/delivery-preflight-report-UNIQUE.json" \
  --registry-census "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json" \
  --target-account appid:EXACT_APPID --draft-id DRAFT_MEDIA_ID \
  --article-revision 'sha256:EXACT_TRANSPORT_REVISION' \
  --host-session-id CURRENT_HOST_SESSION_ID \
  --capture-tool-id scripts/ingest_wechat_readback_capture.py \
  --observed-url https://mp.weixin.qq.com/cgi-bin/appmsg \
  --nonce FRESH_CURRENT_SESSION_NONCE_AT_LEAST_32_CHARS \
  --chapter-capture CHAPTER_ID "$EXTERNAL_CAPTURE_ROOT/chapter.png" RFC3339_CAPTURE_TIME DISTINCT_EVENT_ID \
  --output-dir "$EXTERNAL_READBACK_ROOT/ingested-capture-UNIQUE"

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-readback \
  HANDOFF_JSON OUTPUT/candidate-report.json DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output-dir "$EXTERNAL_READBACK_ROOT/readback-UNIQUE" \
  --capture-bundle "$EXTERNAL_READBACK_ROOT/ingested-capture-UNIQUE/capture-bundle.json"
```

  Repeat `--chapter-capture` once for every chapter. The ingested bundle and resulting scope must say `host_attested=false`, `portable=false`, and `publication_authority=false`; the publisher consumes its nonce across all output directories before any further provider read. It never accepts the portable screenshot-manifest schema as this bundle. A missing signer does not block draft capture/readback, but this route can never authorize `freepublish`.

- Keep the portable signed route independent. It uses the signed/final compile chain and a host screenshot manifest, never `--capture-bundle`:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-readback \
  HANDOFF_JSON OUTPUT/compile-report.json DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output-dir "$EXTERNAL_READBACK_ROOT/portable-readback-UNIQUE" \
  --screenshots DELIVERY/portable-signed-wechat-chapter-screenshots.json
```

  After either route, rerun transport validation with the exact compile report, live root, upload map, account, and readback. Session mode requires `session_readback_structural_match=true`, `current_session_publication_preflight_eligible=true`, and `portable_audit_verified=false`. Portable mode additionally requires both valid receipts.
- Run a complete watermark-carrier census. When there are no eligible carriers, record `not-applicable`; when any are eligible, every eligible carrier must authenticate after actual CDN download. A bare `watermark_transport_verified=true` is never evidence.
- If the sanitizer changes a marker, fallback hash, SMIL signature, image URL, or content order—or the mobile profile is absent, pending, failed, expired, or mismatched—update the same draft with its information-equivalent static fallback and read it back again.
- Do not call the handoff complete until the returned draft is coherent and all required content is present.

### 6. Stop at the requested terminal state

- Default result: a saved and reopened draft in the target account, with draft ID, revision hash, cover evidence, interaction policy/status, selected dynamic or fallback payload, verification report, a clear preview/open path, and an explicit assurance label. Say `portable signed audit verified` only when both host receipts pass; otherwise say `current-session draft structurally verified; portable_audit_verified=false`.
- Formal publication accepts either a passing portable signed chain or a `current-session-live` chain executed inside an isolated trusted embedding harness. Immediately before submit, call `draft/get` again and compare title, author, digest, content, and `thumb_media_id` with the exact compiled payload. A JSON file containing trusted-looking Booleans cannot authorize publication. The current-session challenge plus `CurrentSessionHostAuthority` policy hook is deliberately non-portable and non-cryptographic; it must be reported as `publication_authority_assurance=trusted-harness-policy-hook-not-independently-attested`, and ordinary repository Python must not claim the hook proves a real host or user event. Portable mode does **not** accept the hand-written confirmation schema: it requires a separately host-signed `wechat-host-publication-confirmation-receipt-v1` binding the account/revision/draft/payload/compile/readback facts, action, user intent, expiry and nonce, verified by the protected trust store. Ardot/readback receipts authenticate observations, not user permission. With the checked-in Codex adapter, use the declared UI live route or portable signed API route for publication.
- `freepublish/submit` means only “task accepted.” Poll `freepublish/get`: status `1` remains non-terminal; `0` is success only when `article_detail.item[].article_url` is present; `2–6` are terminal failures; timeout remains `unknown` and must not be reported as published. Report `portable_audit_verified=false` for the current-session route.
- Group send is separate from publication and always requires its own explicit confirmation. Never infer group-send permission from a request to import, save, or publish.

## Browser fallback

Use browser fallback only when the official API path is unavailable and the user still asks to continue.

- Confirm the visible logged-in account before entering content.
- Copy only from the validated frozen-layer artifact selected for this assurance mode: signed `wechat.html` or unsigned `wechat-candidate.html`. Never use an article-JSON authoring preview, previous clipboard, screenshot splice, or old experiment output.
- Import title, digest, rich body, images, and cover; verify the editor after paste.
- Confirm in the real body editor and after reopening the draft that the exact fixed attribution remains the final visible text.
- Save and reopen the draft to verify the actual cover. Do not report a complete import while the cover remains empty or only exists as a body image.
- Browser readback still requires `wechat-saved-draft-readback-v2` with the real DOM response, downloaded CDN objects, and chapter screenshots; dynamic eligibility still requires the matching iOS/Android capability profile.
- Browser publication is allowed only after the same fresh exact binding and explicit confirmation, and only when the current host can authoritatively read the visible terminal publication state and article URL. Never infer success from clicking **发表**. Group send still requires a separate confirmation.
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
