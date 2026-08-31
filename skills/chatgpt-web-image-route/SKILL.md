---
name: chatgpt-web-image-route
description: Generate article image sources through ChatGPT web under Codex control, download the original file, and produce or verify a true RGBA8 subject cutout before an organization WeChat workflow may register it. Use as the default Codex Desktop image route for org-wechat-studio; do not use for documentary photographs, logos, QR codes, layout, or WeChat publishing.
---

# ChatGPT Web Image Route

This is a narrow provider wrapper for `org-wechat-studio`. ChatGPT supplies the
source pixels; Codex owns the prompt scope, original download, deterministic
processing, evidence, visual inspection, and registration decision.

Read [references/image-generation-contract.md](references/image-generation-contract.md)
before generating the first asset in a session.

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

- Work from one approved visual-kit slot or background-family brief at a time.
  Do not paste the whole article, repository files, old visual references, or
  another organization pack into ChatGPT.
- Keep a single article's background family and micro assets in the same image
  conversation so palette and material language remain coherent.
- For an article micro asset, request one isolated, text-free subject on the
  controlled key background named by the visual-kit plan. Do not trust a
  generated claim of transparency. For an opaque background or cover, request
  an opaque raster and keep copy-safe areas text-free.
- Download the provider's original PNG through the page's real download action
  into a predetermined Git-ignored staging path. The filename, page preview,
  Canvas pixels, screenshots, clipboard data, and remote URL are untrusted.

## Accept

- Preserve the raw download and its SHA-256. Never overwrite a prior raw,
  derivative, or report path.
- For a micro asset, run the repository's secure
  `scripts/prepare_micro_cutout.py` route. A native-alpha PNG still passes
  through normalization and the exact pixel gate; an opaque file is accepted
  only when the controlled key background is safely removable.
- Then inspect the derivative visually and run `scripts/inspect_asset.py` for
  its exact role. Only a tightly cropped RGBA8 subject with real transparent
  pixels, no matte/halo/debris, and a complete derivation report satisfies
  `subject-cutout-rgba8-v1`.
- A failed source is regenerated with a different approved key color. Do not
  force-cut a complex scene, a real photograph, glass/hair against a noisy
  background, or an output that touches the canvas edge. After two failed
  source attempts for one slot, stop and report the blocker instead of silently
  weakening the gate.

The first official download plus local SHA, derivation report, and final pixel
inspection is the live route proof. A successful C2C doctor check, ChatGPT text
reply, prompt submission, or page preview alone is never proof.
