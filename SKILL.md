---
name: org-wechat-studio
description: Research an organization, create or update its reusable organization pack, and produce brand-specific WeChat Official Account articles with Ardot-native design components, 2–3 semantic interaction modules by default, structured content, visual QA, static-safe WeChat transport, and draft handoff. Use for any organization’s recruitment, event, project, educational, partnership, recap, or announcement article. Do not use for unrelated social posts or generic research with no WeChat deliverable.
---

# Organization WeChat Studio

Create organization-specific WeChat articles without reducing the organization to a logo and color swap. Separate stable publishing mechanics from the organization’s identity and the facts of the current article.

For commands and file locations, read [references/使用说明.md](references/使用说明.md). For a new account, also read [references/organization-pack-migration.md](references/organization-pack-migration.md). The current hardening rationale is recorded in [references/source-zero-audit.md](references/source-zero-audit.md). Read [references/style-options.md](references/style-options.md) only when the user explicitly supplies a style reference or selects a reviewed style preset. Read [references/provenance-watermark.md](references/provenance-watermark.md) before registering a generated opaque background or fully generated raster cover.
On Codex Desktop, load [skills/chatgpt-web-image-route/SKILL.md](skills/chatgpt-web-image-route/SKILL.md) before the first generated asset. It composes `codex-with-chatgpt`, the built-in Browser, original-file download, and the local RGBA processor; the C2C connector itself remains a planning/read-only bridge and never counts as image evidence.
Before freezing any final HTML or publisher handoff, read [references/ardot-transport-fidelity.md](references/ardot-transport-fidelity.md).

## Mandatory runtime preflight

Before opening source material, creating an organization pack, generating an article asset, or touching Ardot/WeChat, read [references/runtime-preflight.md](references/runtime-preflight.md) and bind the current harness to the project skill hashes and semantic capabilities. At the beginning of every workflow/organization migration into a new harness, machine, adapter, provider route, or changed trusted bundle, run `migration` first. It consumes one isolated neutral RGBA route probe and must complete in the current host trace before any organization facts or visuals are read. Then use `full` when an exact current Ardot file/root already exists. For a new organization with no Ardot workspace, use `bootstrap`, verify `ardot.create`, create only the blank design/page, then immediately rerun the requested terminal phase (`full` by default, or `authoring` when explicitly scoped) with its canonical file/root. `bootstrap` does not require a WeChat target or login. Use `delivery` only for an existing reviewed Ardot article.

1. Enumerate the current runtime registry and map real callables to `image.generate.opaque`, `image.generate.rgba`, `chatgpt.session`, `image.inspect`, `ardot.create`, `ardot.read`, `ardot.write`, `ardot.export`, `browser.control` / `computer.use`, `wechat.draft`, and `secret.resolve`. Also detect optional `host.receipt.attest`: it upgrades delivery to `portable-signed-audit`, but its absence does not block `current-session-draft`. Codex Desktop uses local ImageGen only for opaque sources and defaults RGBA source acquisition to `chatgpt-web-image-route` + `codex-with-chatgpt` + the complete built-in Browser route. Another harness may bind a native RGBA API, but it must keep the same output contract. A generic shell or JavaScript executor does not prove any image or Browser capability.
2. Write a temporary, Git-ignored runtime profile with the current project `SKILL.md` and publisher Skill hashes, the current host session/provider IDs, credential-free Ardot/WeChat links, and intended tool bindings. The profile expresses intent, not truth. Never put tokens, cookies, AppSecret, watermark keys, raw watermark IDs, secret values, or self-authored `passed` evidence in it.
3. Run the binding check before sending either URL to an external tool:

   ```bash
   python3 -I -S scripts/secure_runner.py scripts/runtime_preflight.py output/runtime/runtime-profile.json \
     --phase full --binding-only \
     --output output/runtime/binding-report-UNIQUE.json
   ```

   The `-I -S` secure runner is mandatory for runtime preflight, final transport validation/compilation, and watermark verification. Never replace it with direct `python3 scripts/...`, `PYTHONPATH`, a user-site hook, or an unlocked dependency path. A new harness/Python/platform combination must first add reviewed distribution hashes to `runtime/python-dependency-lock.json` and update the trusted release digest.

   For a migration start, substitute `--phase migration`. Its minimal profile has no organization, Ardot, or WeChat links; it binds opaque generation, the selected RGBA route, and image inspection. Every phase that uses RGBA must declare the adapter's real stable `generation_route_id`; `migration` additionally declares `migration_probe_contract: neutral-rgba-route-probe-v1`. Complete the emitted host-owned migration route gate in the same C2C-managed conversation before moving to `bootstrap`, `authoring`, or `full`; do not create a setup-only task, throwaway chat, or isolation transition. For the no-workspace bootstrap case, substitute `--phase bootstrap`; its profile omits the Ardot workspace link and uses `ardot_bootstrap` bound to `ardot.create`.

4. Continue only when the binding report has `ok: true` and `binding_ready: true`. Its `phase_ready` is intentionally always false: a workspace process cannot authenticate its own tool claims. Do not rerun the script without `--binding-only` and mistake profile fields for live evidence.
5. Immediately execute the report's ordered `host_setup_actions` before reading source material. In `migration`, run the nonce/digest-bound neutral RGBA probe after the image routes are prepared and before any organization/Ardot/WeChat action. In `authoring`/`full`, prepare opaque generation and the selected RGBA route first without repeating that migration-only probe. For Codex Desktop, load the wrapper and C2C Skills, run the C2C update/sandbox/session checks, claim one visible built-in-browser ChatGPT tab, and stop once for login/CAPTCHA/2FA/consent if needed; Computer Use and external browsers are forbidden for ChatGPT. Then prepare Ardot and, for delivery-capable phases, WeChat. Resolve watermark references without displaying values. `bootstrap` prepares only `ardot.create`; `delivery` does not open ChatGPT or bind generation. Ardot MCP OAuth and Ardot web login remain separate checks. Never persist a ChatGPT conversation URL, pairing code, token-bearing redirect/editor URL, cookie, or session value.
6. After preparation, perform the actual current-session probes through host-owned calls that are visible in the host tool trace. `migration` is the only startup phase that consumes image quota: generate the report's exact neutral prompt, observe completion and the provider-original download, record local PNG MIME/bytes/SHA, run the secure cutout processor, inspect the exact RGBA8 derivative on transparent/light/dark surfaces, and keep all outputs under its nonce-specific Git-ignored runtime directory. The local pixel chain and current host route trace are both required; neither can impersonate the other. Never register, upload, watermark, or reuse the probe as an article asset or style reference. For ChatGPT-web, obey the C2C one-conversation rule and do not open a throwaway verification chat. The probe must remain a nonsemantic, single-gray open-stroke calibration mark with deep negative space and no organization, object, material, palette, or artistic cues; official prompts must explicitly exclude that mark and test treatment. For `authoring`/`full`, the emitted `enforce-migration-rgba-route-gate` is a host-workflow hard gate, not a claim that this local CLI can authenticate an earlier host trace. Then inspect a neutral local image and read the exact Ardot file **and root** without editing while confirming write/export callables in the same provider/session; for `bootstrap`, confirm only the selected create-design/page callable and use it only to establish the blank target before rerunning the requested terminal phase; only for phases that include delivery, resolve the target WeChat account without creating a draft; only for phases that author visuals, resolve required watermark secret references without returning values. Regular article startup does not consume a second smoke image: the first official ChatGPT generation still needs its own observed original download, local raw SHA-256, RGBA derivation report, and final pixel inspection as article lineage. C2C doctor/workspace output, a ChatGPT text reply, a page preview, an old migration report, or a model-authored receipt proves neither chain.
7. Do not continue unless every required selected-route probe succeeded in the current host trace. `needs_user_login`, an account/file/root identity mismatch, a stale trace, an unsafe URL, a missing required callable, an unresolved key, a different Skill SHA, or an installed stale publisher copy is blocking. A missing optional `host.receipt.attest` selects `current-session-draft` and blocks only the portable signed-audit claim. Never accept a user/LLM-authored profile, prior report, or rewritten timestamp as evidence.
8. Repeat the Ardot file/root probe before full assembly. The last-mile publisher independently performs the `delivery` binding gate and fresh host probes; startup readiness never authorizes a write or formal publication.

## Route the request

1. Identify the organization and article type.
2. Default to source-zero: use only an organization pack explicitly supplied for this organization or the workspace `organizations/<organization-id>/`. Never inspect bundled examples, another organization pack, prior article layouts, screenshots, PDFs, or Ardot files to infer the new visual direction. The only exception is an explicit user request to learn a named visual reference or select a reviewed repository preset. In that case use `explicit-style-grammar` for one or more chosen routes, copy only the nine abstract grammar tokens plus the fixed non-copy boundary, and preserve its canonical SHA-256. A route with `preset_id` must match the canonical grammar in `style-presets/<preset-id>.json`; recomputing a new SHA after changing its tokens does not authorize the change. A later organization reuses the preset JSON, not the original reference page.
3. If a pack exists, validate it before authoring:

   ```bash
   python3 scripts/orgs.py validate path/to/organization-pack
   python3 scripts/orgs.py recommend path/to/organization-pack ARTICLE_TYPE
   ```

4. If no pack exists, perform source-zero onboarding before composing. Read [references/onboarding.md](references/onboarding.md) and [references/org-pack-schema.md](references/org-pack-schema.md). Initialize a destination only when the user has asked to create or save the workflow:

   ```bash
   python3 scripts/orgs.py init ORGANIZATION_ID --name "Organization name" --root organizations
   ```

5. Before the first full article for an organization or route, read [references/visual-calibration.md](references/visual-calibration.md) and create two or three small Ardot calibration strips. A reviewed style preset may be offered as one route-level option only when explicitly selected; it never replaces source-zero as the default or skips current-organization calibration:

   ```bash
   python3 scripts/build_visual_directions.py path/to/organization-pack ARTICLE_TYPE \
     --output output/organization-id/visual-directions.json
   ```

   Show only a hero, chapter, real-photo treatment, micro visual, and density strip for each direction. If generated backgrounds are used, create one master plus 1–3 companions in the same family during calibration. Preserve each approved unmarked master, create a distinct provenance-watermarked final derivative before asset registration, and require authenticated local detection; never watermark a real photograph, logo, QR code, transparent micro component, SVG, or QA screenshot. Declare one family-wide `surface_mode`, a normalized copy-safe rectangle, the body text hex color, minimum contrast `4.5`, and maximum copy-zone luminance deviation `0.10`; register final opaque PNGs and rerun `orgs.py validate` so the actual composited pixels—not prompt prose—prove continuity and readability. For `expressive-native`, approve at least two named construction recipes; each recipe needs at least two non-font techniques and at least two editable text/accent layers. A font change alone is never an expressive treatment. Stop until these checks, one route, and its Ardot file/page/node are recorded under `organization.visual.calibration`. A provisional organization never proceeds to a full article.
6. For an article, read [references/article-schema.md](references/article-schema.md), [references/storyboard.md](references/storyboard.md), [references/interaction-composition.md](references/interaction-composition.md), [references/expressive-typography.md](references/expressive-typography.md), [references/ardot-workflow.md](references/ardot-workflow.md), and [references/organic-layout.md](references/organic-layout.md). Write and approve a 4–10 chapter narrative storyboard before generating visuals:

   ```bash
   python3 scripts/build_storyboard.py article.json \
     --output output/article-slug/storyboard-plan.json
   ```

7. Add an approved `interaction_plan`. The normal `dynamic-default` authoring mode contains 2–3 semantic interaction modules distributed across distinct chapters: two use `early` + `middle`; three use `early` + `middle` + `late`. Count one continuous reader task as one module even when it contains several transport instances: four department reveal cards are one module and four instances. Each instance binds current block copy to a unique fallback key and `sha256:<64 hex>`. Use `static-exception` only with a specific reason explicitly confirmed by the user or editor. Missing target-account runtime certification never cancels authoring; it selects the static equivalent at delivery.
8. Build the mandatory article-specific micro-illustration kit:

   ```bash
   python3 scripts/build_visual_kit.py article.json \
     --org path/to/organization-pack \
     --output output/article-slug/visual-kit-plan.json
   ```

   On Codex Desktop, use `chatgpt-web-image-route` by default. For each of `floating-spot`, `section-transition`, `inline-explainer`, and `closing-motif`, first ask ChatGPT for a provider-original PNG with genuine pixel transparency, download that original, and retain it under `assets/generated/`. Run the secure `scripts/prepare_micro_cutout.py` processor with `--require-native-alpha`; this route validates, normalizes, tightly crops, and zeroes transparent RGB but does not remove a background. Only when that original fails the strict native-Alpha or pixel gate may one second source be generated on the plan's controlled key color and processed with `--key-color`. Never use a screenshot, preview Canvas, clipboard image, or copied remote URL. Create a distinct file under `assets/derived/`, then run `python3 -I -S scripts/secure_runner.py scripts/inspect_asset.py DERIVED --role ROLE`. A provider claim of transparency is untrusted; only the downloaded pixels and complete derivation chain decide. Create four native Ardot components from the derivatives, then record each component `file_url`, `node_id`, exact `name`, asset ID, and derivative SHA in `article.visual_kit.assets`. Rerun the plan and do not continue while `ready_for_layout` is false.
   Every slot must quote one exact `source_text`, name a specific `concrete_subject`, visible `action`, storyboard chapter, placement, and composition job. Never prompt from a bulk dump of the article. Each generated asset must be registered with its visual role and the current `article_id`; generic decorations do not satisfy this gate.
9. After the four native micro components exist, build the deterministic Ardot assembly manifest:

   ```bash
   python3 scripts/build_ardot_manifest.py article.json \
     --org path/to/organization-pack \
     --output output/article-slug/ardot-manifest.json
   ```

10. Assemble the article chapter by chapter in Ardot. A chapter may reuse primitives, but must not become a mechanical stack of block components. Build every planned interaction module as one native group component with editable `closed`, `open`, and information-equivalent `fallback` states. After all content and any user-authored footer blocks, append one final native editable text node with the exact visible copy `感谢拓浙 AI 生态提供本篇内容生产工作流支持。`; this repository-usage attribution is not organization identity and must not be renamed, hidden, rasterized, styled as an image, or moved earlier.
11. Read [references/visual-review.md](references/visual-review.md). Export five distinct 390 px Ardot nodes (`hero`, `chapter`, `evidence`, `complex-section`, `cta`) from the same article root. Use visual review schema v3 with local PNG paths, SHA-256, pixel dimensions, capture timestamps, chapter IDs, density-to-screenshot hash binding, and measured micro-component placement evidence, then validate it:

   ```bash
   python3 scripts/build_visual_review.py visual-review.json --article article.json
   ```

   Set `article.visual_review_file` to that file. Generate WeChat transport only after this screenshot-backed review passes.

## Organization model

- Infer identity from current official/user-provided evidence, not from organization category or logo alone. Past copy may inform voice only when explicitly allowed; its layout and imagery never enter source-zero visual calibration. An explicitly selected style grammar can influence abstract material, color-motion, layering, and edge behavior only; organization identity, content, photographs, typography, components, and layout are re-derived from current evidence.
- Model voice and visual character separately. Preserve the organization’s factual and institutional boundaries even when using a more expressive visual route.
- Use the five profile axes as evidence-backed signals, not labels: authority, technical depth, warmth, experimentation, and action orientation.
- Offer two or three small visual calibration strips during first-time onboarding. Approve visual evidence, not route names or prompt prose.
- Treat any explicit pack marked `migrated-draft` or `provisional` as a hypothesis requiring source-zero onboarding and confirmation before full-article work.

## Evidence and assets

- Use official or user-provided sources for names, dates, metrics, people, partners, eligibility rules, and claims.
- Keep uncertain information visibly marked during drafting. `--check` must fail while placeholders or unsupported metric/quote claims remain.
- Preserve user-supplied logos and QR codes exactly. Never recreate a logo or create/replace a QR code with image generation.
- Register real photographs as `documentary-evidence` with a source ID when they prove people, facilities, events, products, or projects. Register AI backgrounds as `illustrative-atmosphere`; they provide continuity and never enter evidence galleries or impersonate a real scene.
- Eligible opaque `generated-illustrative` backgrounds and fully generated raster covers use the V1 hidden provenance watermark. Embed into a new derivative before registration, keep the source master in the Git-ignored private-input path, require `local_verified`, and bind the final pixel SHA plus public report hash into the asset registry. Every ready-producing gate must use the external key to reauthenticate current pixels and independently rerun the complete-frame 390px/JPEG-Q75 simulation; never trust a report's Boolean. Image/report/private-record outputs are create-once and never overwrite existing paths. The embedded payload and public manifest contain no organization, article, author, reader, account, OpenID, or recipient identity; the secret and raw watermark-ID mapping stay outside the repository.
- Do not use EXIF, PNG text chunks, filenames, least-significant bits, transparent RGB, or SVG metadata as the watermark. Do not mark official/user-supplied assets, photographs, `documentary-evidence`, logos, QR codes, transparent `article-micro` images, SVG/SMIL, or visual-review evidence. An excluded carrier is `not_eligible`, not a failed watermark.
- A V1 authenticated result proves only that a compact payload HMAC is valid under the supplied key. It is not independent authorship/copyright proof and does not promise recovery from cropping, borders, rotation, perspective, or partial screenshots. Detect the complete WeChat-hosted body/cover object; prepare final cover geometry before embedding.
- Prefer text-free generated imagery. Add Chinese copy, dates, metrics, partner names, and logos during deterministic layout.
- Every article requires four distinct article-specific generated micro derivatives before layout, one per role. Reusing identity files, old decorations, raw source downloads, or documentary photos never satisfies this gate.
- Reject generated assets that are rectangular, framed, generic, text-bearing, or only appear transparent because a checkerboard was baked into the pixels. An RGB source, an all-opaque RGBA conversion, and a ChatGPT transparency claim are never sufficient. Bind the original source, prompt, generation route, processor/config, derivation report, derivative SHA, and final Alpha inspection before registration.
- Search the organization asset registry before generating a generic visual:

  ```bash
  python3 scripts/orgs.py search path/to/organization-pack "QUERY"
  ```
- Before creating assets for a new account or article type, generate a route-specific asset plan. It distinguishes reusable assets, missing real photographs, allowed generated illustrations, and identity files that must come from the user:

  ```bash
  python3 scripts/orgs.py asset-plan path/to/organization-pack ARTICLE_TYPE --output asset-plan.json
  ```

- Save approved files in the pack’s `assets/official`, `assets/photos`, `assets/generated`, or `assets/derived` directory, then register them:

  ```bash
  python3 scripts/orgs.py register-asset path/to/organization-pack \
    --id visual.hero-example --kind background --title "Hero background" \
    --location assets/generated/hero-example.png \
    --origin generated-illustrative --style STYLE_ID --use ARTICLE_TYPE
  ```

## Composition

- Choose the article route from the organization pack and current article type. Do not reuse a route merely because it worked for another organization. If the chosen route carries `style_grammar`, verify `explicit-style-grammar` provenance and the grammar SHA; routes without it remain source-zero even in the same pack.
- Build with semantic blocks such as hero, lead, section, text, statement, metrics, timeline, gallery, case, roles, quote, steps, image, CTA, references, and footer.
- Default a normal article to 2–3 semantic interaction modules. A module is one reader task and one static-equivalent region; its child SVGs or swipe triggers are transport instances, not extra modules. Do not count decorative motion, the four mandatory micro illustrations, or expressive typography toward this budget.
- Default every block to an open composition with no enclosing background, border, radius, or shadow. Add a container only when the content truly needs comparison, interaction, or a hard boundary.
- Do not begin the article root until the four micro-visual roles exist as native Ardot components. Use them beside text, across transitions, along a continuous path, and near the ending—not as rectangular panel backgrounds.
- Every micro raster is a subject-only, tightly cropped 8-bit RGBA cutout. It may contain the subject's natural shadow or open effect, but never a white/black/colored matte, background plane, text, frame, or layout whitespace. Registration must pass the robust Alpha/cutout gate; the Ardot image node must retain that exact asset ID and SHA, with no visible backplate or section screenshot substituted for it.
- A micro component is a partial-width editorial accent, not a miniature poster or a full-row raster panel. Keep each raster/illustration layer at or below 72% of the 390 px row and the whole component at or below 82%. Across the four mandatory roles, use both left and right offsets, at least three distinct offsets, at least three composition relations, visible scale variation, and placements in at least three screenshot sections.
- When a micro component includes copy, leave the copy open: no enclosing border, filled rectangle, chip, badge, rounded label, or closed shape node. Keep the text native and editable. Its primary phrase must be at least 22 px and 1.35× the local body size, using `scale-contrast` plus at least one non-frame technique such as mixed weight, color contrast, deliberate line break, baseline offset, or a vector accent. Outline/offset layers may shape glyphs; they must never become a box around the words.
- Keep body copy readable on a solid or near-solid surface. Use strong backgrounds for covers, transitions, evidence summaries, calls to action, and endings.
- Use 2–4 approved expressive typography moments for hero, chapter, statement, key phrase, or CTA roles when the organization chooses `expressive-native`. Each moment must reference an approved recipe and implement at least two of its non-font construction techniques—such as deliberate line breaks, scale contrast, baseline offset, native outline/offset layers, color contrast, or vector accents—with unique native text/accent node evidence. Keep every moment licensed, editable, and supplied with a standard fallback. Never count a font swap as art type or bake Chinese display copy into generated images.
- Keep closed boxes at or below 20% of content sections, never place two boxed sections consecutively, and include at least three asymmetric or edge-breaking visual moments.
- Judge openness, rhythm, clipping, scale variation, photo/illustration harmony, mobile legibility, and subject relevance from real Ardot screenshots. Never let article JSON self-certify its own visual quality.
- Vary long-article rhythm through open text, generated micro illustrations, continuous paths, full-width transitions, image breaks, and quiet whitespace. Never solve missing visual rhythm by adding cards.
- Optimize for phone reading with an explicit density mode. Default to `compact-editorial`: 15–17 px body text, 1.45–1.62 body line-height, -0.2–0 px Chinese letter spacing, 8–14 px paragraph spacing, and 24–40 px major intra-section gaps. Do not use “generous whitespace” as an excuse for low information density.
- Before full layout, register one AI background master plus 1–3 same-family companions with a shared family ID and explicit variants. The whole family uses one light/dark surface mode; its normalized copy-safe zone must be near-solid and maintain at least 4.5:1 contrast with the declared body text color. Run `orgs.py validate` after the final PNGs are registered. Never mix black/white chapter surfaces, rely on colors that merge with copy, or generate unrelated backgrounds chapter by chapter.
- Record selected organization ID, route ID, component IDs, source IDs, and unresolved warnings in the compile report.

## Authoring and delivery

- Treat the structured article JSON as the portable semantic/content source only. After visual approval it cannot drive final layout or delivery rendering.
- Treat the current Ardot root as the sole visual source of truth. Build native frames and reusable components using the same semantic component IDs as the article JSON. Never make HTML, a flattened long image, or a manually redrawn SVG the editable or delivery design source.
- Preserve the fixed workflow attribution `感谢拓浙 AI 生态提供本篇内容生产工作流支持。` as the final visible native editable text in Ardot and as the final visible section in transport. Freeze it in handoff schema v5 and verify normalized terminal text after draft save; a transport `data-*` marker alone is insufficient because WeChat may sanitize it.
- Read `ardot.json`, apply the organization variable mode, fetch components by exact name, create missing route-specific variants, and assemble one 390 px article root in block order.
- Capture and inspect Hero, section, statement, process/case, CTA, and other high-impact sections before handoff. Iterate on composition in Ardot; do not polish the hidden transport renderer as a substitute for visual authoring.
- After visual approval, export one immutable `ardot-current-root-layer-export-v1` from the same root. Chapter geometry uses `article-root-390-v1`: the first starts at `y=0`, every next chapter starts exactly at the prior bottom, and the last bottom equals the artboard height. The hash-bound current-root export must also carry the exact `transport_sections` layer census and `body_asset_ids`; every background, cutout, photo, text and interaction uses its real source node, unique z-order, supported render style and asset/text hash. Native text declares an approved WeChat system font family rather than accepting a silent font replacement. Export each text-free background as the complete `1170 x (chapter_height * 3)` layer, keep photos and approved cutouts independent, bind every SVG to an actual Ardot state export plus fallback, and include one hash-bound `390 x chapter_height` reference screenshot per chapter.
- Immediately before either draft path, read the same root again through the active Ardot-capable host and save it as a separate fresh current-root export. It needs a timezone-aware `captured_at` strictly later than the frozen export and different bytes/inode; renaming, copying or hard-linking frozen evidence is forbidden. Choose exactly one assurance mode:

  - `current-session-draft`: when `host.receipt.attest` is unavailable, the same current host trace must show the exact Ardot file/root reread, candidate compilation, real WeChat draft write, reopen, and chapter-by-chapter readback. Compile only `wechat-candidate.html` plus `candidate-report.json`; require `candidate_valid: true`, `draft_write_eligible: false`, `portable_audit_verified: false`, `delivery_eligible: false`, and `finalization_verified: false`. The unsigned report is only a structural binding; the reversible write is a current-host action policy owned by the visible tool trace, never a portable artifact entitlement. This mode cannot be presented as portable audit or publication proof.
  - `portable-signed-audit`: a real `host.receipt.attest` callable signs both the Ardot live read and saved-draft readback with a host-only Ed25519 private key. The repository reads the public key only from a protected root-owned trust store. This mode retains the terminal `wechat.html` / `compile-report.json` artifact chain and portable verification.

  For `current-session-draft`, run:

  ```bash
  python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
    --intended-html output/article-slug/wechat-candidate.html \
    --live-root-export qa/live-current-root.json \
    --require-live-root --session-draft
  python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py --transport-fidelity handoff.json \
    --live-root-export qa/live-current-root.json \
    --session-draft --output output/article-slug --check
  python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
    --html output/article-slug/wechat-candidate.html \
    --live-root-export qa/live-current-root.json \
    --compile-report output/article-slug/candidate-report.json \
    --require-compile-report --session-draft
  ```

  For `portable-signed-audit`, run:

  ```bash
  python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
    --intended-html output/article-slug/wechat.html \
    --live-root-export qa/live-current-root.json \
    --live-root-receipt qa/live-current-root-receipt.json \
    --require-live-root
  python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py --transport-fidelity handoff.json \
    --live-root-export qa/live-current-root.json \
    --live-root-receipt qa/live-current-root-receipt.json \
    --output output/article-slug --check
  python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
    --html output/article-slug/wechat.html \
    --live-root-export qa/live-current-root.json \
    --live-root-receipt qa/live-current-root-receipt.json \
    --compile-report output/article-slug/compile-report.json \
    --require-compile-report
  ```

- `compile_wechat.py article.json --authoring-preview --org ...` is a non-delivery diagnostic only. It emits `authoring-preview.html`, never `wechat.html`, and is not the `--session-draft` path; the publisher must reject it as a draft payload.
- `index.html`, `wechat-candidate.html`, and final `wechat.html` are transport/debug artifacts, not the design source. Both draft paths must contain one chapter section per frozen Ardot section node and one native text marker per frozen text node. The session path binds the exact fresh live export, candidate HTML bytes and `candidate-report.json` structurally and must be revalidated in the same host immediately before paste. The signed path additionally terminally binds the intended path, path identity, device/inode, SHA-256, byte length, handoff SHA and transport revision in `compile-report.json` with the original live receipt.
- Freeze handoff schema v5 with both the hash-bound `ardot-current-root-export` and full transport layer export, then run `validate_workflow_attribution.py` and the selected transport gate. After saving and reopening the WeChat draft, export actual visible body text plus `wechat-saved-draft-readback-v1`. In current-session mode rerun the validator with the candidate HTML/report, live export, `--readback ... --require-readback --session-draft`, and require `session_readback_structural_match: true`; the active host trace must independently show the real account/draft reopen. In portable mode the host also issues `wechat-host-saved-draft-receipt-v1` and the validator uses both receipts. Neither mode permits formal publication without separate explicit confirmation.
- The final adapter must carry every approved cutout as an independent, true-alpha, partial-width layer at its Ardot-derived geometry. It must not silently drop the visual kit, bake it into a background/composite, or send it through a generic full-width image/card renderer.
- The authoring layer normally hands 2–3 approved interaction modules to the last-mile publisher under policy `wechat-svg-smil-self-v1`. The only dynamic candidates are no-ID self-trigger `<set>` / `<animateTransform begin="click">` SVG and inline CSS horizontal swipe. JavaScript, `<details>`, transport IDs, cross-ID timing, fragment references, and unprobed SMIL are forbidden. Every transport instance requires a unique semantic-hash-matched static fallback.
- Before creating a WeChat draft, upload body images to the organization’s connected account and replace local paths with returned WeChat URLs. Upload the cover through the account’s supported cover-material flow.
- For every locally verified marked carrier, download the actual WeChat-hosted body image or cover derivative after draft save and run authenticated detection. Only `transport_verified` proves that the mark survived WeChat; HTML structure and URL readback are insufficient. In required mode, unresolved `transport_lost` blocks publication.
- A dynamic candidate remains disabled until saved-draft structure readback and an unexpired target-account iOS/Android capability profile both pass. Structure preservation alone is not runtime proof; otherwise update the same draft with the static fallback.
- Default to draft creation only. Formal publication always requires a separate explicit confirmation.

## Quality gate

Treat any of the following as blocking for final delivery:

- missing, stale, unsafe, self-reported-only, or failing runtime preflight for the active phase; a workflow/organization migration that skipped its current nonce/digest-bound neutral RGBA route probe; a binding-only report presented as phase readiness; a different project or provider-wrapper Skill SHA; local ImageGen presented as an RGBA route; C2C doctor/workspace output, a local derivation report alone, or a model-authored download receipt presented as host-route proof; a generic executor presented as ImageGen/Browser/Computer Use; an untrusted Ardot/WeChat URL; or a target file/account mismatch;
- failed organization-pack validation;
- missing valid visual-reference provenance: for source-zero, allowed visual input source IDs, all excluded legacy-visual categories, and isolation review time; for `explicit-style-grammar`, registered style source IDs, abstract-only scope, review time, all six non-copy constraints, at least one selected route, or a matching canonical grammar SHA-256;
- reference text, photographs, logos, specific layout, component geometry, artwork, or unsupported reference-shaped fields entering a route grammar, prompt, visual kit, or Ardot manifest;
- unresolved placeholders;
- missing local assets;
- missing or incomplete `article.visual_kit`, fewer than four distinct derived micro assets, any missing visual role, absent original-download evidence, missing source/prompt/route/processor/config/report lineage, RGB or all-opaque pseudo-RGBA, non-RGBA8/undecodable Alpha, low-Alpha residue, chromatic/neutral halo, detached debris, oversized transparent canvas, clipped subject, rectangular/rounded/solid/textured matte, stale cutout SHA/evidence, or missing native Ardot component node evidence;
- article layout started before the micro illustrations were made into Ardot components;
- more than 20% boxed content sections, two consecutive boxes, or every block owning a background/border/radius container;
- missing organization/route calibration benchmark or provisional organization status;
- missing generated background family, master, 1–3 companions, normalized copy-safe zone, one declared surface mode, 4.5:1 body-text contrast, near-solid copy surface, pixel-checked tonal continuity, or mismatched family metadata;
- an eligible newly registered generated background/cover that lacks a distinct unmarked source hash, marked pixel hash, fresh external-key authentication, independently verified 390px/JPEG-Q75 simulation, finite PSNR of at least 42 dB, strict public report, external-key identifier, or matching report hash; a missing/weak/bare-passphrase key; an existing output path; a private-record path outside its configured Git-external private root; a public manifest containing a raw watermark ID or any organization/reader identity; or any attempt to watermark a real photograph, Logo, QR code, transparent micro component, SVG, or QA evidence;
- missing organization typography calibration; or, for `expressive-native`, fewer than two approved recipes, a recipe/moment with fewer than two non-font construction techniques or editable layers, a font-swap-only moment, fewer than two grounded article moments, unapproved treatments, unlicensed fonts, missing/duplicate Ardot text/accent-node evidence, or baked text assets;
- missing or incomplete narrative storyboard;
- missing `interaction_plan`; a normal article outside the 2–3 semantic-module budget; child instances, decoration, micro illustrations, or display type used to pad the count; repeated chapter/placement bands; ungrounded instance copy; duplicate fallback keys or semantic hashes; or a static exception without a specific user/editor-confirmed reason;
- a visual-kit item without grounded source copy, a specific subject/action, or a chapter/composition role;
- missing or failing screenshot-backed schema-v3 `visual_review_file` before final transport;
- missing, changed, hidden, rasterized, duplicated, or non-terminal workflow attribution in Ardot, compiled transport, handoff v5, or saved-draft normalized text;
- missing/failing `ardot-current-root-layer-export-v1`; missing fresh live-root reread; in `portable-signed-audit`, a missing/invalid short-lived host-signed receipt; in `current-session-draft`, a missing current-host reread/write/reopen trace, a candidate report that does not bind the exact live export and candidate HTML, any claim with `portable_audit_verified` other than false, or an attempt to publish/group-send; a frozen export reused, renamed, copied or hard-linked as live evidence; a non-later or timezone-less live capture time; discontinuous/overlapping chapter y geometry; current-root visible component/section/layer/source/style/body-asset census mismatch; an unsupported or silently substituted font/crop/rotation/mask; duplicate/missing interaction state node IDs or tree hashes; any final renderer driven by article JSON; mixed screenshot/template/freehand-SVG sources; unsigned nested DOM or extra attributes; a final/candidate HTML artifact binding mismatch; a QA/contact/section-composite body image; a background without exact 3x geometry or zero-text node evidence; a decoration not independently bound to its approved cutout and source node; a supplied rather than recomputed SVG structure signature; detached readback without the bound compile artifact; a non-`mmbiz.qpic.cn` hosted asset; or missing chapter-level revision/asset/SVG/screenshot readback;
- missing measured evidence for all four micro-component roles; an image wider than 72% of the row; a component wider than 82%; fewer than three screenshot sections, three distinct offsets, three composition relations, both left/right offsets, or visible scale variation; framed copy; or copy-bearing micro components without native text nodes, 22 px / 1.35× primary scale contrast, and a second non-frame emphasis technique;
- missing `information_density` / `background_family_coherence` / `background_surface_unity` / `reading_surface_contrast` / `expressive_typography` / `art_type_construction` / `no_baked_art_text` screenshot checks, unhashed/non-390 px Ardot exports, fewer than five density samples, measured body-text contrast below 4.5, `compact-editorial` major gaps outside 24–40 px, body line-height outside the selected mode, or an accidental empty region larger than 20% of a sampled section;
- a metric without a source ID;
- a quote without attribution or source ID;
- mismatched organization IDs across registries;
- generated or unverified QR/logo assets;
- scripts, forms, or non-inline stylesheet dependencies in `wechat.html`;
- JavaScript, `<details>`, any transport `id`, cross-ID SMIL timing, SVG fragment references, non-WeChat SVG image URLs, or an interaction outside `wechat-svg-smil-self-v1`;
- selecting a dynamic payload when any transport instance lacks matching `data-fallback-key` / `sha256:<64 hex>`, or when a module lacks current-revision closed/open/fallback Ardot evidence covering every instance ID and semantic hash, saved-draft signature readback, or a current capability profile for the exact target account; absence of runtime certification forces the static equivalent rather than blocking static delivery;
- a draft payload without a current target-account cover `thumb_media_id`, or a saved draft whose cover cannot be verified;
- `compile-report.json` with `ok: false`.

Detailed density bands and AI-background continuity rules are in [references/information-density.md](references/information-density.md).

Read [references/qa.md](references/qa.md) before a final draft handoff or when diagnosing a failed check.
