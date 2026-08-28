# WeChat official API delivery

Read this reference only when using the official server-side delivery route.

## Primary operations

1. Obtain and cache a server-side access token. Direct-account mode uses AppID/AppSecret and requires the configured IP allowlist. A multi-organization publisher should use WeChat Open Platform authorization and `authorizer_access_token`.
2. Upload each body image with `POST /cgi-bin/media/uploadimg`. Use the returned WeChat URL in article HTML. The endpoint accepts JPG/PNG below 1 MB.
3. Upload the cover with `POST /cgi-bin/material/add_material?type=image` and retain the permanent `media_id` for `thumb_media_id`.
4. Create a draft with `POST /cgi-bin/draft/add`, or update an existing mapped draft with `POST /cgi-bin/draft/update`.
5. Retrieve it with `POST /cgi-bin/draft/get` and validate the returned article.
6. Only after explicit publication confirmation, submit the draft with `POST /cgi-bin/freepublish/submit` and poll `POST /cgi-bin/freepublish/get` until success or failure.

## Relevant official constraints

- Draft content supports HTML but strips JavaScript.
- Article HTML must contain fewer than 20,000 characters and be below 1 MB.
- External image URLs are filtered; body image URLs must come from the article-image upload endpoint.
- A news article requires a permanent cover `thumb_media_id`.
- The cover `media_id` belongs to the target account and current cover asset. Never reuse another account's material ID or substitute a body-image URL.
- Draft add/update and draft get use permission sets `11` or `100`.
- Publication uses permission set `7`; actual availability also depends on account type and certification shown in the target account's developer center.
- A successful publication submission returns a task ID, not proof that publication finished.
- Group send uses different endpoints and operational safeguards. It is never part of draft creation or ordinary publication.

## Draft payload gates

- Refuse draft add/update until the current cover upload has returned a non-empty `media_id` and the payload uses it as `thumb_media_id`.
- Upload article body images before compiling a dynamic SVG that embeds an image; SVG `<image>` accepts only the returned `mmbiz.qpic.cn` URL under policy `wechat-svg-smil-self-v1`.
- Retrieve the saved draft and verify the cover, body-image URLs, interaction markers, fallback hashes, and SMIL structure signatures. An HTTP success response is not verification.
- Keep one mapped draft for candidate and fallback. If readback or the account/client capability profile fails, update that same draft with the static payload and verify again.

## Idempotency

WeChat draft creation does not provide a caller idempotency key. Maintain a publisher-side mapping:

```text
(target_account_id, ardot_revision_hash) -> draft_media_id
```

Before creating, consult the mapping. On a retry, fetch and update the mapped draft when it still exists. Record the response and verification status without logging access tokens.

## Authoritative documentation

- New draft: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_add.html
- Update draft: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_update.html
- Get draft: https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_getdraft.html
- Upload article image: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_uploadimage.html
- Upload permanent material: https://developers.weixin.qq.com/doc/service/api/material/permanent/api_addmaterial.html
- Submit publication: https://developers.weixin.qq.com/doc/service/api/public/api_freepublish_submit.html
- Get publication status: https://developers.weixin.qq.com/doc/service/api/public/api_freepublish_get.html
- Authorizer access token: https://developers.weixin.qq.com/doc/oplatform/developers/dev/AuthorizerAccessToken
