# ChatGPT web image generation contract

Resolve the same-release shared runtime and external create-once artifact root
through [runtime-location.md](runtime-location.md) before using any command.

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

This executable contract is currently bound to Codex Desktop. Before the
actions below, the clone-time check and current Codex session must declare the
external `codex-with-chatgpt` Skill/built checkout, exact-workspace connection,
single built-in Browser route, and current ChatGPT login. Another LLM/harness
cannot select this route in the current release.

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
4. Confirm only that the image composer and original-download action are
   reachable; do not consume image quota with a smoke or migration generation.
   No synthetic RGBA image may block source reading, pack creation, or Ardot work.
5. If ChatGPT requires login, CAPTCHA, 2FA, consent, subscription repair, or
   image entitlement, keep the same tab and request one user action. Continue
   only after the same session is re-read.

For article production, one digest-bound approval covers the storyboard,
interaction plan, and all user-selected visual-kit slot briefs. Do not request approval
again for each slot or for a processor-authorized controlled-key source option.
Only a substantive change to that digest or a real login/consent wall requires
new user input. Publication and group send remain separate fresh confirmations.

These actions are not needed in `bootstrap` or `delivery`. Do not store a
ChatGPT chat URL, pairing code, cookie, token, session storage value, or login
result in the repository runtime profile, organization pack, article JSON, or
public evidence.

## Runtime session binding

New clones, machines, sessions, and provider routes bind the verified release,
adapter, stable `generation_route_id`, and current provider session without
generating or inspecting a calibration image. `org-wechat-runtime-session-evidence-v1`
may close this current-session binding. It never blocks source reading and does
not claim host attestation or portability. The former
`neutral-rgba-route-probe-v1` path is optional legacy diagnostics only.

Provider/browser recovery still uses `provider-pending`,
`completed-await-download`, `provider-terminal-failed`, and
`browser-control-unavailable`. Resume an unknown request read-only before any
resubmission. These states are independent of per-asset image quality.

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
- a provider-original PNG using either genuine native transparency or one flat
  key color selected by the visual-kit plan and absent from the subject and
  organization palette;
- at most two real source attempts for a slot; every accepted route must still
  produce a final derivative that passes the same strict cutout gate.

The key background is an acquisition aid, not a publishable asset. Do not ask
for a checkerboard, white, black, gradient, textured, photographic, or blurred
background. Do not use a key color that appears materially in the subject.

## Original download

An accepted source begins with the ChatGPT page's visible original-download
action and a browser-observed download event. Predetermine a create-once path
under the article's Git-ignored staging area. The binding report's
nonce-specific migration directory is reserved for an explicitly requested
legacy diagnostic probe and never supplies an article source. Reject:

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

Before derivation, every formal article attempt must have an
`org-wechat-provider-image-acquisition-v2` record. It binds the verified
installed-release census, exact adapter bytes, adapter-declared route, the
same-session runtime binding, canonical request metadata, a create-once Browser
ingestion report, and its exact raw target SHA/bytes. No migration image is
required for this article record.

The command shape below shows the stronger portable invocation. It requires a
portable migration receipt plus provider receipt and supplies
`--portable-trust-store /PROTECTED/PUBLIC-KEYS.json`:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/prepare_micro_cutout.py" \
  RAW_PNG DERIVED_PNG \
  --role ROLE \
  --article-id ARTICLE_ID \
  --asset-slot-id ASSET_SLOT_ID \
  --prompt-sha256 sha256:PROMPT_SHA \
  --generation-route chatgpt-web-image-route-v1 \
  --acquisition-report ACQUISITION_V2.json \
  --portable-trust-store /PROTECTED/PUBLIC-KEYS.json \
  --require-native-alpha \
  --report DERIVATION_REPORT.json
```

For the normal Codex Desktop current-session route, the same CLI or Python API
may run without `--portable-trust-store` after the same-session runtime binding,
canonical request, create-once ingestion, exact raw-byte, and RGBA
pixel gates pass. The result is operationally accepted but fixed to
`host_attested=false` and `portable=false`. The compatibility function
`live_provider_acquisition_authority(callback)` is only an optional
trusted-harness veto policy. `True` leaves assurance unchanged; `False` or an
exception blocks. A plain Python callback, including `lambda challenge: True`,
cannot create a signature, host attestation, or portability claim. A JSON field
named `callback`, `authorized`, or `passed` likewise has no assurance effect.

Use `--require-native-alpha` for a true-alpha source. A deliberately generated,
uniform controlled-key source may instead use `--key-color '#KEYHEX'` on its
first article-specific attempt. The processor never guesses a background; the
selected route and exact key are explicit.

The acquisition ledger for either successful first route contains one accepted
attempt. If a real native-alpha source is rejected and the slot then uses its
controlled-key option, the two-attempt ledger contains the reproducible rejected
native source followed by the accepted key source. Do not invent that first
failure when controlled-key was selected from the outset.

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

After derivation of a real transparent article asset, run the inspection through
the locked secure runner:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/inspect_asset.py" \
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
fallback. Each actual attempt records its own prompt SHA; the acquisition and
derivation bind the accepted attempt's SHA. When a provider-original native-alpha
attempt is recorded as rejected, the validator must reopen the exact ingested
raw bytes and reproduce the stated Alpha/pixel failure; a self-reported failure
code is insufficient. A rejected controlled-key first source must not be
serialized as a fabricated reverse fallback ledger. If two source attempts fail, stop that visual-kit slot,
preserve both reports, and explain the exact blocker. Layout cannot begin while
any selected role lacks a valid derivative and native Ardot component.

## Live evidence boundary

Normal article startup can declare `bound_unprobed`; that state does not block
source reading or planning. There is no startup RGBA probe exception. Each official asset becomes
accepted only when its own evidence chain contains:

1. current ChatGPT tab request;
2. completed generation visible in that tab;
3. observed original-download event;
4. local raw PNG bytes, MIME/type, length, and SHA-256;
5. cutout derivative and derivation report when the role requires RGBA;
6. final pixel gate plus visual inspection.

For an article with `N` selected roles, each report uses the exact
`kit.<role>` slot. The layout-ready gate requires `N` distinct accepted raw SHA
values, provider request IDs, acquisition authority bindings, and derivative
SHA values. When `N` is zero, no image attempt or synthetic replacement is
created. A single provider original copied to another path or recropped for another role
is rejected even when every individual PNG passes Alpha inspection.

C2C update/doctor output, connector status, `workspace_info`, a ChatGPT text
reply, a page preview, or a model-authored JSON receipt
cannot replace this chain.

An article record with a complete current-session chain is operationally
accepted as operator/harness-trusted even when no callback or signer exists.
Incomplete chains are `structural-only` and cannot produce/register a formal
derivative or make `ready_for_layout` true. A configured callback denial or
exception blocks. A copied v1 ledger is always rejected for new formal assets.

## Future harness port contract — not executable in this release

Codex Desktop uses this wrapper plus `codex-with-chatgpt` and the built-in
Browser. The following is only a specification for a future reviewed release,
not an operator-selectable fallback: a new harness would need a native/API
generator bound to `image.generate.rgba`, an original local source, the exact
`subject-cutout-rgba8-v1` processor/inspection/lineage/registration gates, a
real stable `generation_route_id`, equivalent login/download evidence, full forward tests and
a new release lock. Until those are shipped, the route is unsupported even if
its tools have similar names. Provider substitution never changes the final
asset contract.
