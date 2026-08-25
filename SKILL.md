---
name: org-wechat-studio
description: Research an organization, create or update its reusable organization pack, and produce brand-specific WeChat Official Account articles with Ardot-native design components, structured content, visual QA, WeChat-safe transport, and draft handoff. Use for any organization’s recruitment, event, project, educational, partnership, recap, or announcement article. Do not use for unrelated social posts or generic research with no WeChat deliverable.
---

# Organization WeChat Studio

Create organization-specific WeChat articles without reducing the organization to a logo and color swap. Separate stable publishing mechanics from the organization’s identity and the facts of the current article.

For the complete operator guide, commands, file locations, and migration example, read [references/使用说明.md](references/使用说明.md).

## Route the request

1. Identify the organization and article type.
2. Search for an organization pack in the user-provided location, the workspace `organizations/<organization-id>/`, then this skill’s bundled `organizations/` directory.
3. If a pack exists, validate it before authoring:

   ```bash
   python3 scripts/orgs.py validate path/to/organization-pack
   python3 scripts/orgs.py recommend path/to/organization-pack ARTICLE_TYPE
   ```

4. If no pack exists, perform organization onboarding before composing. Read [references/onboarding.md](references/onboarding.md) and [references/org-pack-schema.md](references/org-pack-schema.md). Initialize a destination only when the user has asked to create or save the workflow:

   ```bash
   python3 scripts/orgs.py init ORGANIZATION_ID --name "Organization name" --root organizations
   ```

5. For an article, read [references/article-schema.md](references/article-schema.md) and [references/ardot-workflow.md](references/ardot-workflow.md), then create an article JSON beside its source materials.
6. Build the deterministic Ardot assembly manifest before editing the design:

   ```bash
   python3 scripts/build_ardot_manifest.py article.json \
     --org path/to/organization-pack \
     --output output/article-slug/ardot-manifest.json
   ```

7. Use the manifest to assemble and visually review the native Ardot article. Generate WeChat transport files only after the Ardot design passes review.

## Organization model

- Infer identity from official evidence and representative past communication, not from organization category or logo alone.
- Model voice and visual character separately. Preserve the organization’s factual and institutional boundaries even when using a more expressive visual route.
- Use the five profile axes as evidence-backed signals, not labels: authority, technical depth, warmth, experimentation, and action orientation.
- Offer two or three plausible visual routes during first-time onboarding when the evidence does not establish one clear system. Record the selected route in the pack.
- Treat bundled packs marked `migrated-draft` or `provisional` as hypotheses requiring confirmation before external delivery.

## Evidence and assets

- Use official or user-provided sources for names, dates, metrics, people, partners, eligibility rules, and claims.
- Keep uncertain information visibly marked during drafting. `--check` must fail while placeholders or unsupported metric/quote claims remain.
- Preserve user-supplied logos and QR codes exactly. Never recreate a logo or create/replace a QR code with image generation.
- Prefer real photographs for real people, facilities, events, products, and projects. Treat generated subjects as illustrative unless grounded in supplied references.
- Prefer text-free generated imagery. Add Chinese copy, dates, metrics, partner names, and logos during deterministic layout.
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

- Choose the article route from the organization pack and current article type. Do not reuse a route merely because it worked for another organization.
- Build with semantic blocks such as hero, lead, section, text, statement, metrics, timeline, gallery, case, roles, quote, steps, image, CTA, references, and footer.
- Keep body copy readable on a solid or near-solid surface. Use strong backgrounds for covers, transitions, evidence summaries, calls to action, and endings.
- Vary long-article rhythm. Avoid repeating one card pattern throughout the article.
- Optimize for phone reading: short paragraphs, clear hierarchy, 15–17 px body text, generous line height, and visible swipe affordance.
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
- Before creating a WeChat draft, upload body images to the organization’s connected account and replace local paths with returned WeChat URLs. Upload the cover through the account’s supported cover-material flow.
- Default to draft creation only. Formal publication always requires a separate explicit confirmation.

## Quality gate

Treat any of the following as blocking for final delivery:

- failed organization-pack validation;
- unresolved placeholders;
- missing local assets;
- a metric without a source ID;
- a quote without attribution or source ID;
- mismatched organization IDs across registries;
- generated or unverified QR/logo assets;
- scripts, forms, or non-inline stylesheet dependencies in `wechat.html`;
- `compile-report.json` with `ok: false`.

Read [references/qa.md](references/qa.md) before a final draft handoff or when diagnosing a failed check.
