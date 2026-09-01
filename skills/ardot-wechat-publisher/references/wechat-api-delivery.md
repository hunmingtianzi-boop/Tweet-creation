# WeChat official API delivery

Read this reference only when using the official server-side delivery route.
Resolve the same-release shared runtime and an external create-once artifact
root through [runtime-location.md](runtime-location.md) before invoking the API
publisher.

## Primary operations

1. Obtain and cache a server-side access token outside this CLI. Direct-account mode may use AppID/AppSecret in a separate secret provider and requires the configured IP allowlist; a multi-organization publisher should use WeChat Open Platform authorization and `authorizer_access_token`. The repository `wechat_publisher.py` does not exchange AppSecret for a token: at execution it reads `WECHAT_ACCESS_TOKEN` and `WECHAT_APP_ID` (or explicitly renamed env selectors) only.
2. Prove account access with successful read-only `GET /cgi-bin/draft/count` and `GET /cgi-bin/material/get_materialcount`. These calls do not prove upload, draft-write, or publish permission.
3. Upload each body image with `POST /cgi-bin/media/uploadimg`. Use the returned WeChat URL in article HTML. The endpoint accepts only matching JPG/PNG bytes strictly below 1 MB.
4. Upload the cover with `POST /cgi-bin/material/add_material?type=image` and retain the permanent `media_id` for `thumb_media_id`. Permanent `type=image` accepts BMP/PNG/JPEG/GIF up to 10 MB; the separate `type=thumb` rule is 64 KB JPG and is not the ordinary news-cover route.
5. Compile final/current-session HTML from the completed account upload map. Never compile local URLs and replace them afterward.
6. Create a draft with `POST /cgi-bin/draft/add`, or update an existing mapped draft with `POST /cgi-bin/draft/update`.
7. Retrieve it with `POST /cgi-bin/draft/get`, retain the raw response/headers/time with publisher `capture-raw`, then use the selected readback route to download the returned CDN objects and validate the saved article. For current-session API drafts, `wechat.current-session-readback` opens that exact draft through Browser/Computer Use, captures actual 390 px chapter PNGs, and passes them through the create-once ingestor plus publisher `--capture-bundle`. Portable signed API readback keeps its independent `--screenshots` manifest route.
8. Only after an exact one-time publication confirmation, submit the draft with `POST /cgi-bin/freepublish/submit` and poll `POST /cgi-bin/freepublish/get` until a terminal result. Portable publication requires a distinct host-signed user-confirmation receipt in addition to the signed Ardot/readback evidence chain. Current-session API **publication** is available only to an isolated trusted embedding harness through an independent non-cryptographic policy hook; the checked-in Codex adapter and standalone CLI expose no such publication route even though they do expose the current-session draft-readback bundle route. A declared UI live publication route remains separate.

## Relevant official constraints

- Draft content supports HTML but strips JavaScript.
- Article HTML must contain fewer than 20,000 characters and be below 1 MB.
- Title is at most 32 characters, author at most 16, digest at most 120, and returned `media_id`/`thumb_media_id` at most 128 characters.
- External image URLs are filtered; body image URLs must come from the article-image upload endpoint.
- A news article requires a permanent cover `thumb_media_id`.
- The cover `media_id` belongs to the target account and current cover asset. Never reuse another account's material ID or substitute a body-image URL.
- Draft add/update and draft get use permission sets `11` or `100`.
- Publication uses permission set `7`; actual availability also depends on account type and certification shown in the target account's developer center.
- A successful publication submission returns a `publish_id`, not proof that publication finished. `publish_status=1` is still pending; `0` is success only with `article_detail.item[].article_url`; `2` is originality failure, `3` generic failure, `4` audit rejection, `5` all articles deleted, and `6` all articles blocked. A polling timeout is unknown, not success.
- Group send uses different endpoints and operational safeguards. It is never part of draft creation or ordinary publication.

## Draft payload gates

- Refuse draft add/update until the current cover upload has returned a non-empty `media_id` and the payload uses it as `thumb_media_id`.
- Upload article body images before compiling any payload; SVG `<image>` accepts only the exact upload-map `mmbiz.qpic.cn` URL under policy `wechat-svg-smil-self-v1`.
- Retrieve the saved draft and verify the cover, body-image URLs, interaction markers, fallback hashes, and SMIL structure signatures. An HTTP success response is not verification.
- Keep one mapped draft for candidate and fallback. If readback or the account/client capability profile fails, update that same draft with the static payload and verify again.

## Current-session readback versus publication authority

The checked-in Codex adapter exposes `wechat.current-session-readback`, not `wechat.current-session-authority`. After `save-draft`, its executable chain is:

1. `wechat_publisher.py capture-raw` creates one external raw `draft/get` file;
2. Browser/Computer Use reopens the exact bound account/draft and captures every chapter as actual `390 × chapter_height` PNG bytes;
3. `ingest_wechat_readback_capture.py` binds those create-once bytes to the verified installed release, census, profile/report, host session, target/revision, raw response SHA/request ID, sanitized observed URL, times/events, and a fresh nonce;
4. `wechat_publisher.py capture-readback --capture-bundle ...` revalidates all live bindings, consumes that nonce store-wide before further provider work, copies screenshots create-once, and emits a current-session-only readback scope.

The browser may use a token-bearing query internally to reach the editor, but no token/query/fragment is persisted; only the credential-free WeChat origin/path enters the bundle. Every raw/bundle/readback output must be a new path under an already existing external parent, with no symlink in its lexical ancestry. The bundle always declares `host_attested=false`, `portable=false`, and `publication_authority=false`. It rejects a portable screenshot manifest, duplicate nonce or chapter bytes/events, stale/mismatched runtime/session/account/draft/revision/raw bytes, and an Ardot reference image presented as a WeChat capture. A missing signer therefore does not block draft readback, but the bundle cannot authorize publication.

`CurrentSessionHostAuthority` remains an in-process, non-cryptographic trusted-harness **publication** policy interface, never a JSON schema or CLI flag. It does not authenticate an arbitrary Python object and must not be described as independent evidence. A conforming isolated host adapter may also implement live capture, but publication specifically requires:

- optionally, `capture_wechat_chapters(...)` returns chapter PNG bytes plus host capture event IDs from the active WeChat preview instead of the external ingestor;
- `verify_mobile_evidence(...)` binds genuine iOS and Android capture events to the exact profile/readback/host session;
- `authorize_publication(challenge)` freshly re-reads the exact Ardot root and account/draft, consumes the real user-confirmation event, and returns `CurrentSessionPublicationAuthorization` bound to account, article revision, draft media ID, draft payload SHA, compile-report SHA, readback SHA, live-root SHA, nonce and the fresh event.

Construct `WeChatPublisher(provider, store, current_session_authority=HOST_ADAPTER)` only inside an isolated harness-owned process that does not run model-controlled Python in the policy-hook boundary. The ordinary CLI constructs it with `None`, so current-session **publication** still fails closed even after `--capture-bundle` readback succeeds. This route remains `portable_audit_verified=false` and reports `publication_authority_assurance=trusted-harness-policy-hook-not-independently-attested`; a signer is required only to upgrade to portable evidence. Portable publication additionally requires its separate signed user-confirmation receipt. Group send remains a separate action.

## Publication input schemas

- Compile reports use `schema_version: 2`, source `ardot-current-root-layer-export-v1`, one exact `assurance_scope`, selected dynamic/static payload, upload-map binding, live-root/optional receipt bindings, dual postflight and optional interaction evidence binding.
- `wechat-publication-input-bindings-v2` contains exactly: schema/source/scope, target account, revision, draft media ID, and path/SHA bindings for handoff, compile report, upload map, readback, watermark census and live root; portable mode also binds both receipts. Static mode requires `mobile_profile: null`; dynamic mode binds the exact compiled mobile evidence.
- `wechat-explicit-publication-confirmation-v1` contains exactly: schema/source/action, target account, revision, draft media ID, compile-report SHA, one-time lowercase-hex nonce, `confirmed_at` and a maximum-ten-minute `expires_at`. It is only a challenge for the current in-process host callback; by itself it has no authority.
- Portable publication instead consumes `wechat-host-publication-confirmation-receipt-v1`: exact schema/source/signature algorithm/key ID/nonce, host provider/session/request/confirmation-event IDs, `action: freepublish`, `user_intent: explicit-publish-confirmation`, target account, article revision, draft media ID, draft payload SHA, compile-report SHA, readback SHA, `confirmed_at`, maximum-ten-minute `expires_at`, and Ed25519 signature. The protected trust store allowlist must include this source. Neither the Ardot live-read receipt nor saved-draft readback receipt substitutes for user consent.

The publisher reopens every bound file, re-runs transport/readback/mobile/watermark validation, verifies the durable API transaction ledger, and calls `draft/get` again. Booleans in either input are neither defined nor accepted.

## Idempotency

WeChat draft creation does not provide a caller idempotency key. Maintain a publisher-side mapping:

```text
(target_account_id, ardot_revision_hash, payload_sha256) -> draft_media_id
```

Before creating, consult the mapping and reopen a cached remote draft before reporting it saved. Store uploads by `(target_account_id, source_sha256, kind)` and publication jobs by `(account, revision, immutable draft payload SHA, compile-report SHA)`. Claim uploads atomically across processes. Use pending/complete/ambiguous rows: timeout, connection loss, HTTP 5xx, truncated/non-JSON responses, and transient server codes after a non-idempotent request are ambiguous and must be reconciled, never replayed automatically. Consume publication-confirmation nonces once. Record response hashes and verification status without logging access tokens.

## Authoritative documentation

- New draft: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_add.html
- Update draft: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_update.html
- Get draft: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_getdraft.html
- Upload article image: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_uploadimage.html
- Upload permanent material: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_addmaterial.html
- Submit publication: https://developers.weixin.qq.com/doc/service/api/public/api_freepublish_submit.html
- Get publication status: https://developers.weixin.qq.com/doc/service/api/public/api_freepublish_get.html
- Authorizer access token: https://developers.weixin.qq.com/doc/oplatform/developers/dev/AuthorizerAccessToken
