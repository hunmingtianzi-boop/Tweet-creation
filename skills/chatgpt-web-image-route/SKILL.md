---
name: chatgpt-web-image-route
description: On Codex Desktop only, generate article image sources through ChatGPT web under Codex control, download the original file, and optionally produce or verify an RGBA8 subject cutout for an organization WeChat workflow. Use as the default Codex Desktop image route for org-wechat-studio; do not use from another harness or for documentary photographs, logos, QR codes, layout, or WeChat publishing.
---

# ChatGPT Web Image Route

This is a narrow provider wrapper for `org-wechat-studio`. ChatGPT supplies the
source pixels; Codex owns the prompt scope, original download, deterministic
processing, evidence, visual inspection, and registration decision.

This executable route supports Codex Desktop only. Before opening ChatGPT,
state that `codex-with-chatgpt`, its built checkout, the exact current-workspace
connection, the built-in Browser route, and the current ChatGPT login are hard
requirements. The repository release does not install or pair
`codex-with-chatgpt`. If the Skill/checkout is absent, C2C doctor is not green,
the connector belongs to another checkout, or login/CAPTCHA/2FA is unresolved,
stop before generating or reading organization material. A saved conversation,
another browser, or another LLM/harness is not a substitute.

Read [the installed runtime location contract](references/runtime-location.md)
and [the image-generation contract](references/image-generation-contract.md)
before generating the first asset in a session.
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

- Do not generate a synthetic RGBA migration/calibration image. Source reading,
  planning, and authoring may begin after the provider session and runtime route
  are bound. The first real article image supplies any needed quality evidence.
- Follow C2C's one-chat rule; do not open a throwaway verification chat.
- Work from one approved visual-kit slot or background-family brief at a time.
  Do not paste the whole article, repository files, old visual references, or
  another organization pack into ChatGPT.
- The storyboard, interaction plan, and user-selected slot briefs share one
  digest-bound article approval. Generate exactly the confirmed number of slots
  continuously; never ask for a new confirmation per slot. A planned controlled-key
  source needs no separate confirmation. Only a substantive subject/style/scope change or a real
  login/CAPTCHA/2FA/consent wall interrupts for user input.
- Keep a single article's background family and micro assets in the same image
  conversation so palette and material language remain coherent.
- For an article micro asset, request one isolated, text-free subject as a
  provider-original PNG. Choose native transparency or the slot's uniform
  controlled-key source according to the subject and provider behavior. Do not
  trust a generated claim of transparency. For an opaque background or cover, request an opaque raster and
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
  `generation_route_id`, the same-session runtime binding, canonical request
  metadata, and the create-once Browser ingestion report whose target is the
  exact raw source. A v1 ledger or self-written provider/trace/callback field is
  diagnostic only and cannot unlock a formal asset.
- Store a distinct `prompt_sha256` on every actual source attempt and bind it
  into that attempt's canonical request metadata and ingestion report. The
  acquisition top-level and cutout derivation prompt SHA must equal the
  accepted attempt. A direct controlled-key first source is a one-attempt
  accepted ledger; it does not need a fictional native failure. When a native
  attempt is actually recorded as rejected before a controlled-key retry, the
  validator reopens that raw file and recomputes its allowed pixel failure;
  `failure_code` is never trusted alone.
- Track provider/browser recovery separately from source attempts. For a
  pending or unknown request, reread the same C2C session/request before doing
  anything else and never submit a duplicate. Browser transport recovery and
  login do not spend an attempt. Only an explicit provider-terminal failure may
  resubmit the exact bound prompt with a new request ID.
- For a micro asset, run the repository's secure
  `scripts/prepare_micro_cutout.py` route. A native-alpha source uses
  `--require-native-alpha`; a deliberately uniform controlled-key source may use
  `--key-color` as its first real-asset attempt. The latter is accepted only when
  that background is safely removable. Both routes converge on the same strict
  final derivative gate.
- Then inspect the derivative visually and run `scripts/inspect_asset.py` for
  its exact role. Only a tightly cropped RGBA8 subject with real transparent
  pixels, no matte/halo/debris, and a complete derivation report satisfies
  `subject-cutout-rgba8-v1`.
- Current-session acceptance reruns the same-session runtime binding,
  canonical request, create-once ingestion, exact raw bytes, and RGBA pixel
  chain. It is operationally accepted as operator/harness-trusted, with
  `host_attested=false` and `portable=false`; missing a callback or signer does
  not block this route. `live_provider_acquisition_authority(callback)` is only
  an optional trusted-harness veto policy: `True` leaves assurance unchanged,
  while `False` or an exception blocks. A plain Python callback never creates
  attestation or portability. The stronger standalone portable route still
  requires both protected Ed25519 receipts. See the local
  [provider-acquisition contract](references/provider-acquisition-authority.md).
- If the selected source route fails, regenerate once using the other approved
  source option when it is suitable. A two-attempt v2 ledger represents only a
  reproducibly rejected native-alpha source followed by an accepted controlled-key
  source; never invent a reverse controlled-key failure ledger. Do not force-cut a complex scene, a real photograph,
  glass/hair against a noisy background, or an output that touches the canvas
  edge. After two real source attempts fail, stop and report the blocker instead
  of silently weakening the final gate.

There is no quota-consuming RGBA startup or migration gate. The first official
download still keeps its own local SHA and, when used as a transparent micro
asset, its derivation report and final pixel inspection as article-specific
quality evidence. A successful C2C doctor check,
ChatGPT text reply, prompt submission, or page preview alone is never proof.
