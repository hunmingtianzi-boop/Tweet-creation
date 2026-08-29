---
name: org-wechat-studio
description: Research an organization, create or update its reusable organization pack, and produce brand-specific WeChat Official Account articles with Ardot-native design components, 2–3 semantic interaction modules by default, structured content, visual QA, static-safe WeChat transport, and draft handoff. Use for any organization’s recruitment, event, project, educational, partnership, recap, or announcement article. Do not use for unrelated social posts or generic research with no WeChat deliverable.
---

# Organization WeChat Studio

Create organization-specific WeChat articles without reducing the organization to a logo and color swap. Separate stable publishing mechanics from the organization’s identity and the facts of the current article.

For commands and file locations, read [references/使用说明.md](references/使用说明.md). For a new account, also read [references/organization-pack-migration.md](references/organization-pack-migration.md). The current hardening rationale is recorded in [references/source-zero-audit.md](references/source-zero-audit.md). Read [references/style-options.md](references/style-options.md) only when the user explicitly supplies a style reference or selects a reviewed style preset.

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

   Show only a hero, chapter, real-photo treatment, micro visual, and density strip for each direction. If generated backgrounds are used, create one master plus 1–3 companions in the same family during calibration. Declare one family-wide `surface_mode`, a normalized copy-safe rectangle, the body text hex color, minimum contrast `4.5`, and maximum copy-zone luminance deviation `0.10`; register final opaque PNGs and rerun `orgs.py validate` so the actual composited pixels—not prompt prose—prove continuity and readability. For `expressive-native`, approve at least two named construction recipes; each recipe needs at least two non-font techniques and at least two editable text/accent layers. A font change alone is never an expressive treatment. Stop until these checks, one route, and its Ardot file/page/node are recorded under `organization.visual.calibration`. A provisional organization never proceeds to a full article.
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

   Generate, inspect, save, and register one distinct asset for each of `floating-spot`, `section-transition`, `inline-explainer`, and `closing-motif`. Run `python3 scripts/inspect_asset.py FILE --role ROLE` for every asset. Create four native Ardot components, then record each component `file_url`, `node_id`, and exact `name` in `article.visual_kit.assets`. Rerun the plan and do not continue while `ready_for_layout` is false.
   Every slot must quote one exact `source_text`, name a specific `concrete_subject`, visible `action`, storyboard chapter, placement, and composition job. Never prompt from a bulk dump of the article. Each generated asset must be registered with its visual role and the current `article_id`; generic decorations do not satisfy this gate.
9. After the four native micro components exist, build the deterministic Ardot assembly manifest:

   ```bash
   python3 scripts/build_ardot_manifest.py article.json \
     --org path/to/organization-pack \
     --output output/article-slug/ardot-manifest.json
   ```

10. Assemble the article chapter by chapter in Ardot. A chapter may reuse primitives, but must not become a mechanical stack of block components. Build every planned interaction module as one native group component with editable `closed`, `open`, and information-equivalent `fallback` states.
11. Read [references/visual-review.md](references/visual-review.md). Export five distinct 390 px Ardot nodes (`hero`, `chapter`, `evidence`, `complex-section`, `cta`) from the same article root. Use visual review schema v2 with local PNG paths, SHA-256, pixel dimensions, capture timestamps, chapter IDs, and density-to-screenshot hash binding, then validate it:

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
- Prefer text-free generated imagery. Add Chinese copy, dates, metrics, partner names, and logos during deterministic layout.
- Every article requires four distinct article-specific generated micro assets before layout, one per role. Reusing identity files, old decorations, or documentary photos never satisfies this gate.
- Reject generated assets that are rectangular, framed, generic, text-bearing, or only appear transparent because a checkerboard was baked into the pixels. Verify actual Alpha when transparency is required.
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
- Keep body copy readable on a solid or near-solid surface. Use strong backgrounds for covers, transitions, evidence summaries, calls to action, and endings.
- Use 2–4 approved expressive typography moments for hero, chapter, statement, key phrase, or CTA roles when the organization chooses `expressive-native`. Each moment must reference an approved recipe and implement at least two of its non-font construction techniques—such as deliberate line breaks, scale contrast, baseline offset, native outline/offset layers, color contrast, or vector accents—with unique native text/accent node evidence. Keep every moment licensed, editable, and supplied with a standard fallback. Never count a font swap as art type or bake Chinese display copy into generated images.
- Keep closed boxes at or below 20% of content sections, never place two boxed sections consecutively, and include at least three asymmetric or edge-breaking visual moments.
- Judge openness, rhythm, clipping, scale variation, photo/illustration harmony, mobile legibility, and subject relevance from real Ardot screenshots. Never let article JSON self-certify its own visual quality.
- Vary long-article rhythm through open text, generated micro illustrations, continuous paths, full-width transitions, image breaks, and quiet whitespace. Never solve missing visual rhythm by adding cards.
- Optimize for phone reading with an explicit density mode. Default to `compact-editorial`: 15–17 px body text, 1.45–1.62 body line-height, -0.2–0 px Chinese letter spacing, 8–14 px paragraph spacing, and 24–40 px major intra-section gaps. Do not use “generous whitespace” as an excuse for low information density.
- Before full layout, register one AI background master plus 1–3 same-family companions with a shared family ID and explicit variants. The whole family uses one light/dark surface mode; its normalized copy-safe zone must be near-solid and maintain at least 4.5:1 contrast with the declared body text color. Run `orgs.py validate` after the final PNGs are registered. Never mix black/white chapter surfaces, rely on colors that merge with copy, or generate unrelated backgrounds chapter by chapter.
- Record selected organization ID, route ID, component IDs, source IDs, and unresolved warnings in the compile report.

## Authoring and delivery

- Treat the structured article JSON as the portable content source.
- Treat Ardot as the visual source of truth. Build native frames and reusable components using the same semantic component IDs as the article JSON. Never make HTML or a flattened long image the editable design source.
- Read `ardot.json`, apply the organization variable mode, fetch components by exact name, create missing route-specific variants, and assemble one 390 px article root in block order.
- Capture and inspect Hero, section, statement, process/case, CTA, and other high-impact sections before handoff. Iterate on composition in Ardot; do not polish the hidden transport renderer as a substitute for visual authoring.
- After visual approval, run the hidden final adapter when a WeChat draft or portable handoff is required:

  ```bash
  python3 scripts/compile_wechat.py article.json --org path/to/organization-pack --output output/article-slug --check
  ```

- `index.html` and `wechat.html` are transport/debug artifacts, not the design source.
- The authoring layer normally hands 2–3 approved interaction modules to the last-mile publisher under policy `wechat-svg-smil-self-v1`. The only dynamic candidates are no-ID self-trigger `<set>` / `<animateTransform begin="click">` SVG and inline CSS horizontal swipe. JavaScript, `<details>`, transport IDs, cross-ID timing, fragment references, and unprobed SMIL are forbidden. Every transport instance requires a unique semantic-hash-matched static fallback.
- Before creating a WeChat draft, upload body images to the organization’s connected account and replace local paths with returned WeChat URLs. Upload the cover through the account’s supported cover-material flow.
- A dynamic candidate remains disabled until saved-draft structure readback and an unexpired target-account iOS/Android capability profile both pass. Structure preservation alone is not runtime proof; otherwise update the same draft with the static fallback.
- Default to draft creation only. Formal publication always requires a separate explicit confirmation.

## Quality gate

Treat any of the following as blocking for final delivery:

- failed organization-pack validation;
- missing valid visual-reference provenance: for source-zero, allowed visual input source IDs, all excluded legacy-visual categories, and isolation review time; for `explicit-style-grammar`, registered style source IDs, abstract-only scope, review time, all six non-copy constraints, at least one selected route, or a matching canonical grammar SHA-256;
- reference text, photographs, logos, specific layout, component geometry, artwork, or unsupported reference-shaped fields entering a route grammar, prompt, visual kit, or Ardot manifest;
- unresolved placeholders;
- missing local assets;
- missing or incomplete `article.visual_kit`, fewer than four distinct generated micro assets, any missing visual role, failed pixel Alpha/aspect check, or missing native Ardot component node evidence;
- article layout started before the micro illustrations were made into Ardot components;
- more than 20% boxed content sections, two consecutive boxes, or every block owning a background/border/radius container;
- missing organization/route calibration benchmark or provisional organization status;
- missing generated background family, master, 1–3 companions, normalized copy-safe zone, one declared surface mode, 4.5:1 body-text contrast, near-solid copy surface, pixel-checked tonal continuity, or mismatched family metadata;
- missing organization typography calibration; or, for `expressive-native`, fewer than two approved recipes, a recipe/moment with fewer than two non-font construction techniques or editable layers, a font-swap-only moment, fewer than two grounded article moments, unapproved treatments, unlicensed fonts, missing/duplicate Ardot text/accent-node evidence, or baked text assets;
- missing or incomplete narrative storyboard;
- missing `interaction_plan`; a normal article outside the 2–3 semantic-module budget; child instances, decoration, micro illustrations, or display type used to pad the count; repeated chapter/placement bands; ungrounded instance copy; duplicate fallback keys or semantic hashes; or a static exception without a specific user/editor-confirmed reason;
- a visual-kit item without grounded source copy, a specific subject/action, or a chapter/composition role;
- missing or failing screenshot-backed `visual_review_file` before final transport;
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
