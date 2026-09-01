---
name: chatgpt-web-image-route
description: Generate article image sources through ChatGPT web under Codex control, download the original file, and produce or verify a true RGBA8 subject cutout before an organization WeChat workflow may register it. Use as the default Codex Desktop image route for org-wechat-studio; do not use for documentary photographs, logos, QR codes, layout, or WeChat publishing.
---

# ChatGPT Web Image Route

This is a narrow provider wrapper for `org-wechat-studio`. ChatGPT supplies the
source pixels; Codex owns the prompt scope, original download, deterministic
processing, evidence, visual inspection, and registration decision.

Read [the installed runtime location contract](references/runtime-location.md)
and [the image-generation contract](references/image-generation-contract.md)
before running a migration probe or generating the first asset in a session.
Resolve the same-release sibling `org-wechat-studio` as
`ORG_WECHAT_RUNTIME_ROOT`, keep the user's project as the working directory,
and invoke every shared script by its absolute path.

## Required dependencies

1. Load `codex-with-chatgpt` and follow its update, sandbox, login, single-tab,
   session-reuse, and in-app-browser rules. Its connector remains read-only and
   is not an image transport or proof of image generation.
2. Load `browser:control-in-app-browser`. Use the built-in browser for every
   ChatGPT action. Never use Computer Use, Chrome, screenshots, the clipboard,
   or a copied remote image URL as the download route.
3. Keep the ChatGPT tab visible and reusable. If login, CAPTCHA, 2FA, consent,
   quota, or image access blocks the route, preserve the tab and ask the user
   for only the one necessary action. Re-probe the same session afterward.

## Generate

- At the start of workflow/organization migration, execute the runtime report's
  `neutral-rgba-route-probe-v1` before reading source material. Use its exact
  prompt, host-side nonce/digest request metadata, provider route ID,
  create-once paths, and absolute `prepare_migration_probe.py` command. This
  isolated processor accepts only the fixed neutral probe scope and emits no
  article asset authority. At most one controlled-key fallback is allowed, and
  it requires the processor-created attempt-1 failure evidence. Login/CAPTCHA/download repair does not
  consume that fallback. Keep this neutral probe out of every organization registry,
  Ardot file, article prompt, and visual reference set.
- Follow C2C's one-chat rule; do not open a throwaway verification chat. The
  migration probe is deliberately a nonsemantic, single-gray open-stroke
  calibration mark with deep negative space and no organization, recognizable object, palette, material, or
  artistic cues. Keep using the one C2C-managed conversation, and explicitly
  exclude that calibration mark and grayscale test treatment from every
  official micro-asset prompt.
- Work from one approved visual-kit slot or background-family brief at a time.
  Do not paste the whole article, repository files, old visual references, or
  another organization pack into ChatGPT.
- Keep a single article's background family and micro assets in the same image
  conversation so palette and material language remain coherent.
- For an article micro asset, first request one isolated, text-free subject as
  a provider-original PNG with genuine transparent pixels. Do not trust a
  generated claim of transparency. Only if the downloaded original fails the
  native-Alpha or pixel gate may the same slot use its one controlled-key
  fallback. For an opaque background or cover, request an opaque raster and
  keep copy-safe areas text-free.
- Download the provider's original PNG through the page's real download action
  into a predetermined Git-ignored staging path. The filename, page preview,
  Canvas pixels, screenshots, clipboard data, and remote URL are untrusted.

## Accept

- Preserve the raw download and its SHA-256. Never overwrite a prior raw,
  derivative, or report path.
- For every formal article attempt, first create
  `org-wechat-provider-image-acquisition-v2`. Bind the verified installed-release
  registry census, the exact adapter bytes and adapter-declared
  `generation_route_id`, the same-session migration result, canonical request
  metadata, and the create-once Browser ingestion report whose target is the
  exact raw source. A v1 ledger or self-written provider/trace/callback field is
  diagnostic only and cannot unlock a formal asset.
- For a micro asset, run the repository's secure
  `scripts/prepare_micro_cutout.py` route. Attempt 1 must use
  `--require-native-alpha`: a genuine native-alpha PNG passes normalization and
  the exact pixel gate, while an RGB or all-opaque file fails without background
  removal. Only attempt 2 may use `--key-color`, and it is accepted only when
  that controlled background is safely removable.
- Then inspect the derivative visually and run `scripts/inspect_asset.py` for
  its exact role. Only a tightly cropped RGBA8 subject with real transparent
  pixels, no matte/halo/debris, and a complete derivation report satisfies
  `subject-cutout-rgba8-v1`.
- Current-session acceptance reruns the completed same-session migration,
  canonical request, create-once ingestion, exact raw bytes, and RGBA pixel
  chain. It is operationally accepted as operator/harness-trusted, with
  `host_attested=false` and `portable=false`; missing a callback or signer does
  not block this route. `live_provider_acquisition_authority(callback)` is only
  an optional trusted-harness veto policy: `True` leaves assurance unchanged,
  while `False` or an exception blocks. A plain Python callback never creates
  attestation or portability. The stronger standalone portable route still
  requires both protected Ed25519 receipts. See the local
  [provider-acquisition contract](references/provider-acquisition-authority.md).
- If the direct transparent original fails, regenerate once with the approved
  fallback key color. Do not force-cut a complex scene, a real photograph,
  glass/hair against a noisy background, or an output that touches the canvas
  edge. After the native-alpha attempt and its single controlled-key fallback
  both fail, stop and report the blocker instead of silently weakening the gate.

A migration probe passes operationally only when the current session evidence
binds the provider request, completed generation, observed original-download path, local PNG
MIME/bytes/SHA, secure derivation, and inspection of the exact RGBA8 derivative
on transparent/light/dark surfaces. This does not cryptographically attest the
Browser event. A profile, old report, or model-authored receipt cannot replace
the exact current chain. The probe is not an official asset.

Regular article startup does not repeat this quota-consuming probe. The first
official download still needs its own local SHA, derivation report, and final
pixel inspection as article-specific lineage. A successful C2C doctor check,
ChatGPT text reply, prompt submission, or page preview alone is never proof.
