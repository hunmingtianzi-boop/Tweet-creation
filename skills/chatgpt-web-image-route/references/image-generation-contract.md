# ChatGPT web image generation contract

Contract ID: `chatgpt-web-image-route-v1`

Output contracts:

- `opaque-raster-v1` for generated background masters and raster covers;
- `subject-cutout-rgba8-v1` for article-specific micro illustrations.

This contract separates generation from acceptance. ChatGPT may create useful
pixels, but its UI label, file extension, or claim of a transparent background
does not establish Alpha quality. Codex accepts an asset only after a real
original download, local byte inspection, deterministic processing when
needed, and the repository quality gate.

## Startup contract

Run these actions before source-material reading in `migration`, `authoring`, or `full`:

1. Load `org-wechat-studio`, this wrapper, `codex-with-chatgpt`, and
   `browser:control-in-app-browser` from the current skill registry.
2. Follow the C2C daily `update-check` and `sandbox-allow` rules. Run its doctor
   and session checks when the C2C connection is being used or repaired.
3. Claim or open one visible in-app-browser ChatGPT tab and keep it for the
   session. Navigate through the saved chat or Project conversation selected by
   `c2c session`; `https://chatgpt.com/` is only the credential-free login entry
   or the C2C-approved new-chat entry in long-chat mode. Do not persist the
   resolved conversation URL, and do not use Computer Use or an external browser.
4. In normal `authoring`/`full`, confirm only that the image composer and
   original-download action are reachable; do not consume image quota with a
   smoke generation. In `migration`, execute the binding report's one neutral
   `neutral-rgba-route-probe-v1` after these preparations and before any source,
   pack, Ardot, or WeChat action.
5. If ChatGPT requires login, CAPTCHA, 2FA, consent, subscription repair, or
   image entitlement, keep the same tab and request one user action. Continue
   only after the same session is re-read.

These actions are not needed in `bootstrap` or `delivery`. Do not store a
ChatGPT chat URL, pairing code, cookie, token, session storage value, or login
result in the repository runtime profile, organization pack, article JSON, or
public evidence.

## Migration self-test

Every workflow/organization migration into a new harness, machine, adapter,
provider route, or changed trusted bundle begins with runtime phase `migration`.
Its profile has no organization, Ardot, or WeChat links. It binds opaque image
generation, the selected RGBA route, and image inspection. The RGBA capability
must match both `migration_probe_contract: neutral-rgba-route-probe-v1` and the
adapter's actual stable `generation_route_id`.

The binding report emits an exact direct-transparency prompt, one controlled-key
fallback prompt, both prompt SHAs, per-attempt processor commands, and a
nonce-specific directory under `output/runtime/migration-probes/`. Attempt 1
requires a provider-original PNG with genuine native Alpha and runs the
processor with `--require-native-alpha`; it cannot silently remove a background.
Attempt 2 is allowed only when attempt 1 reaches the native-Alpha/cutout/pixel
gate and fails, and it alone may use `--key-color`. Login, CAPTCHA, 2FA,
consent, generation interruption, or download repair resumes the same attempt
and never spends the fallback.

The nonce and binding digest stay out of the image prompt. The host records them
in a canonical `org-wechat-migration-rgba-request-v1` metadata envelope that
also binds the route, attempt, acquisition mode, and prompt SHA. Its SHA must be
associated with the same current provider request, completed generation, and
original-download event. This avoids visual/semantic prompt pollution while
still preventing an old raw file or report from satisfying the current run.

Passing requires two independent layers:

- `local_pixel_chain_verified`: downloaded PNG bytes, prompt SHA, secure
  processor/config/report chain, true RGBA8, tight Alpha bounds, and the final
  pixel gate;
- `host_route_verified`: the current provider request, completed generation,
  same current Browser/provider session, visible provider-original download
  event, local PNG magic/MIME/byte length/SHA/time, and host inspection of the
  exact derivative on transparent, light, and dark surfaces.

Neither layer implies the other. A profile field, local report, copied file,
old host trace, model-authored receipt, C2C status, screenshot, preview Canvas,
clipboard image, or remote URL cannot make the migration ready. The repository
report remains `phase_ready: false`; only the current host trace can close the
external action. Probe paths are create-once, Git-ignored, bound to the current
nonce/digest, and forbidden from organization `assets.json`, article assets,
watermarking, Ardot, transport, or later style/prompt references.

For the ChatGPT-web route, obey the exact `conversation.mode` returned by C2C.
In `long-chat` mode there is exactly one managed ChatGPT conversation per
workspace, reused across Codex tasks. In `project` mode there is exactly one
ChatGPT Project per workspace; the current Codex conversation reuses its own
saved chat, while a new Codex conversation starts a new chat from that Project
collection and never reuses another task's chat URL. Neither mode permits a
throwaway verification chat. The exact migration prompt therefore uses only
one nonsemantic, uniform mid-gray open-stroke
calibration mark with deep negative space: no organization, recognizable object, palette, material, lighting,
or artistic style. Continue in the same C2C-managed conversation, but every
official image prompt must explicitly exclude the calibration mark and
its grayscale test treatment. The probe remains route QA, never a design input.

## Prompt scope

Each request uses one approved slot from `visual-kit-plan.json`, including only:

- organization name and the selected route's palette/material language;
- one exact grounded `source_text`;
- one `concrete_subject`, visible `action`, role, aspect ratio, and placement;
- the source-zero or approved abstract style-grammar boundary;
- explicit exclusions for text, logos, QR codes, frames, cards, panels, and
  documentary claims.

Never send a bulk article dump, prior article layout, old Ardot frame, reference
screenshot, another organization pack, access credential, private watermark
record, or source document to the image chat.

For an opaque background family, keep the master and companions in one image
conversation and request one surface mode plus a text-free, near-solid copy-safe
zone. The normal background-family and hidden-watermark gates still apply.

For an article micro source, request:

- one isolated subject with no layout whitespace or scene;
- the exact role aspect ratio and visible action;
- no text, letters, digits, mark, signature, logo, or QR code;
- no card, paper sheet, UI panel, border, pedestal, ground plane, or backdrop
  shadow;
- a safety margin around the subject, with no substantive pixel touching an
  edge;
- a provider-original PNG with genuine native transparency as the required
  first attempt;
- only after that original fails the strict native-Alpha or pixel gate, one flat
  fallback key color selected by the visual-kit plan and absent from the subject
  and organization palette.

The key background is an acquisition aid, not a publishable asset. Do not ask
for a checkerboard, white, black, gradient, textured, photographic, or blurred
background. Do not use a key color that appears materially in the subject.

## Original download

An accepted source begins with the ChatGPT page's visible original-download
action and a browser-observed download event. Predetermine a create-once path
under the article's Git-ignored staging area, or the binding report's
nonce-specific migration directory for the neutral probe. Reject:

- a screenshot or cropped page capture;
- a Canvas extraction or preview thumbnail;
- clipboard pixels;
- a copied `blob:` / `data:` / remote image URL;
- HTML, SVG, JPEG renamed as PNG, or a text response;
- an existing, symlinked, glob-selected, or path-traversing destination.

Record the prompt SHA-256, route ID, raw MIME/type evidence, byte length,
download time, and raw SHA-256. The provider filename is informational only.
The raw file is retained even when a derivative is required.

## RGBA derivation and acceptance

Run the create-once cutout processor through the repository secure runner:

```bash
python3 -I -S scripts/secure_runner.py scripts/prepare_micro_cutout.py \
  RAW_PNG DERIVED_PNG \
  --role ROLE \
  --article-id ARTICLE_ID \
  --asset-slot-id ASSET_SLOT_ID \
  --prompt-sha256 sha256:PROMPT_SHA \
  --generation-route chatgpt-web-image-route-v1 \
  --require-native-alpha \
  --report DERIVATION_REPORT.json
```

This is the mandatory first attempt. It rejects RGB and all-opaque RGBA without
trying to infer a background. Only after that route fails may the single
controlled-key fallback replace `--require-native-alpha` with
`--key-color '#KEYHEX'`.

Use the actual CLI help as the final authority if optional color-probe flags
are present. The processor may:

- normalize and tightly crop a native-alpha input that already satisfies the
  cutout contract; or
- remove only a sufficiently uniform, border-connected controlled key
  background, decontaminate key spill, clear detached noise, add a minimal
  transparent safety margin, and emit a metadata-free RGBA8 PNG.

It must fail closed when the background is not safely keyable, the subject
touches an edge, material transparency cannot be separated, or the resulting
shape still resembles a matte/card. It may not process documentary photos,
logos, QR codes, or arbitrary complex scenes.

After derivation, including for a migration probe, run the inspection through
the locked secure runner:

```bash
python3 -I -S scripts/secure_runner.py scripts/inspect_asset.py \
  DERIVED_PNG --role ROLE
```

Also inspect the exact derivative on transparent, light, and dark surfaces.
Only register it when all of these are true:

- the file is deterministically decodable 8-bit RGBA;
- it has meaningful transparent and substantive subject pixels;
- transparent RGB is zeroed;
- the robust subject bounds are tightly cropped with a small open margin;
- no edge is clipped;
- no white, black, key-colored, neutral, or chromatic halo remains;
- no rectangular/rounded/solid/textured matte or detached debris remains;
- the role dimensions and aspect ratio pass;
- source, prompt, processor/config, derivative, inspection, and report hashes
  form one complete `org-wechat-micro-cutout-derivation-v1` chain.

The organization registry stores the raw source under `assets/generated/` and
the accepted cutout under `assets/derived/`. Ardot and transport reference only
the derivative asset ID and SHA. Transparent article micros are excluded from
the opaque-background provenance watermark.

## Failure and retry

One failed cutout never authorizes a weaker threshold or a manual white-card
fallback. When the provider-original native-alpha attempt fails, regenerate
once on the approved controlled key color that remains outside the subject
palette. If that second source also fails, stop that visual-kit slot, preserve
both reports, and explain the exact blocker. Layout cannot begin while any
mandatory role lacks a valid derivative and native Ardot component.

## Live evidence boundary

Normal article startup can declare only `bound_unprobed`. The migration phase
is the single startup exception: its neutral probe proves only that the route
worked in the current migration host trace. It never becomes an article asset
or replaces the first official asset's lineage. Each official asset becomes
accepted only when its own evidence chain contains:

1. current ChatGPT tab request;
2. completed generation visible in that tab;
3. observed original-download event;
4. local raw PNG bytes, MIME/type, length, and SHA-256;
5. cutout derivative and derivation report when the role requires RGBA;
6. final pixel gate plus visual inspection.

C2C update/doctor output, connector status, `workspace_info`, a ChatGPT text
reply, a page preview, a prior migration probe, or a model-authored JSON receipt
cannot replace this chain.

## Harness portability

Codex Desktop uses this wrapper plus `codex-with-chatgpt` and the built-in
browser by default. Another harness may bind a native/API generator directly to
`image.generate.rgba` and omit both ChatGPT skills, provided it still returns an
original local source and passes the exact `subject-cutout-rgba8-v1` processor,
inspection, lineage, and registration gates. Its adapter must expose its real
stable `generation_route_id` and the same `neutral-rgba-route-probe-v1` migration
contract; invented generic route names are forbidden. Provider substitution
never changes the final asset contract.
