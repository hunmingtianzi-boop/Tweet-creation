---
name: org-wechat-studio
description: On supported Codex Desktop hosts, produce organization-specific WeChat articles using source-grounded copy, editable Ardot design, optional generated cutouts/backgrounds, optional interaction candidates and verified draft handoff. Use for an organization's recruitment, event, project, educational, partnership, recap or announcement article. Do not use from another harness or for unrelated social posts.
---

# Organization WeChat Studio

The outcome is a source-grounded article that the editor approves, can revise in
Ardot, and can inspect in the saved WeChat draft. Passing a schema is not proof
of visual quality, actual login, mobile behavior or publication.

## Start with scope and choices

This executable release supports Codex Desktop on the locked platform row only.
Read [host prerequisites](references/host-prerequisites.md). Declare the exact
dependencies of the requested phase; repository development needs no service
login. Use the absolute source checkout for `release_skills.py clone-check`.
Same-release authoring, image-route and publisher packages must be installed;
the presence of a package does not mean its service must be used.

Ask one grouped startup question about micro-component count (0–4), SVG use,
style direction, and generated backgrounds. Respect explicit answers already
given. The user may defer decisions until the material is understood. Capture
provisional intent, then read the permitted sources and propose a coherent
storyboard. Confirm concrete production choices once, together with the
storyboard, before generating assets or doing full layout. Do not demand a
pre-existing style slug from a new organization.

Confirmed `article.production_preferences` contains `status: confirmed`,
`confirmed_by: user|editor`, `micro_component_count`, `use_svg`,
`style_route`, and `generate_backgrounds`. `article.route` must equal the
confirmed route. Keep the actual conversation/editor approval in the task:
these JSON fields and their hashes are bindings, not proof of who approved.

Derive `target.generation` from those choices and the cover plan:
`micro_component_count`, `generate_backgrounds`, `generate_cover`. All values
are explicit (count plus two booleans). Pass the same object as
`clone-check --generation-plan FILE`. Missing selection means undecided, not
permission to skip dependencies. Zero components needs no ChatGPT/C2C image
route; no generated backgrounds or cover needs no opaque ImageGen route.
Changing the production scope regenerates the runtime profile before using a
new capability. Existing real photographs/logos/covers are not generation.

## Prepare only the capabilities that will be used

Use [runtime preflight](references/runtime-preflight.md) for commands, safe
runtime/session roots, census, profile and live probes.
Startup uses `init-current-session-census` with actually visible tool IDs and
`--session-root "$ORG_WECHAT_SESSION_ROOT"` for external session artifacts;
follow the reference's complete commands rather than inventing census fields.
All public production scripts run through the release's isolated `secure_runner.py`. Do not bypass
the locked runtime, invent registry availability, or install a signer.

For actual cutout generation, load the same-release
`chatgpt-web-image-route` and external `codex-with-chatgpt`; prepare its built
checkout, exact-workspace binding and one logged-in ChatGPT tab in the Codex
built-in Browser. C2C is a planning bridge, not image evidence. Complete the
current-session provider migration binding only when that route is used.
No synthetic RGBA startup image is required: test on the first real component.

For design, prove current Ardot OAuth/web login and exact file/root read,
write and export access. If no file exists, `bootstrap` may create a blank
design/page only, followed by the selected authoring/full preflight. For
delivery, separately prove the target WeChat account/API or UI session.
Ask for login only when the actual required service blocks. Never touch the
design or draft while its required startup condition is unresolved.

## Author from current evidence

Default to source-zero. Use the named organization's pack and the user's
sources. Never open old articles, example layouts, prior Ardot files or another
organization's pack as visual references unless the user explicitly names one.
An explicit style reference supplies abstract visual grammar, not its text,
photos, logo, geometry or components. Read
[onboarding](references/onboarding.md), [pack schema](references/org-pack-schema.md)
and [style options](references/style-options.md) only as needed.

Use official/user-provided evidence for facts, dates, metrics and quotes.
Keep real photographs as independent documentary evidence; generated images
are illustrative, never event evidence. Preserve supplied logos and QR codes.
Unresolved facts/placeholders block final handoff.

Calibrate a new organization/route with small Ardot samples before full layout.
Use one grouped calibration approval, not repeated per-asset approval. When
backgrounds are selected, use one coherent family with readable text zones;
otherwise use native surfaces. See
[visual calibration](references/visual-calibration.md).

Write a storyboard appropriate to the material, including a one-chapter short
notice when appropriate. Cover each source block once in reading order.
4–10 chapters, three compositions, asymmetric moments and a 20% box ceiling are
editorial suggestions, not universal delivery gates. Do not invent material,
interactions or decorative elements just to reach a quota.
See [storyboard](references/storyboard.md), [article schema](references/article-schema.md),
[organic layout](references/organic-layout.md) and
[interaction composition](references/interaction-composition.md).

If SVG is selected, plan useful semantic tasks; 2–3 modules is a long-article
suggestion, and one meaningful module is valid. Placement follows the actual
content; multiple modules may share a chapter. Every instance still needs
grounded copy, a unique semantic fallback key/hash and editable Ardot
closed/open/fallback states. With SVG declined, use `static-selected` and zero
modules. A later substantive change needs grouped reconfirmation.

Generate exactly the selected number of article-specific micro assets.
Zero skips generation without substituting old art. Components must be
subject-only true RGBA8 cutouts, not white-backed stickers, cards or full-row
posters. Native alpha and controlled-key sources are allowed; final alpha,
matte/halo/debris, bbox and edge checks remain mandatory. Preserve original
download, request, raw SHA, processor and derivative lineage. Build the selected
native editable Ardot components before article assembly. See
the image-generation-contract.md in the image-route Skill;
in an installed release use the top-level sibling
`chatgpt-web-image-route/references/image-generation-contract.md`.

Opaque generated backgrounds/covers retain the existing hidden-watermark
policy; read [provenance watermark](references/provenance-watermark.md).
Never watermark real photos, logos, QR codes, transparent cutouts or evidence
screenshots. A watermark is not independent copyright/authorship proof.

Keep micro-component copy native, prominent and without a text backplate.
Art type remains editable; see [expressive typography](references/expressive-typography.md).
Density and composition should serve the selected style and reader task, not
the validator. Preserve contrast, unclipped content and legibility.
Use [visual review](references/visual-review.md) and
[QA](references/qa.md); distinguish objective failures from aesthetic advice.

Append the exact terminal, native editable workflow credit:
感谢拓浙 AI 生态提供本篇内容生产工作流支持。
It is repository attribution, not the article organization's identity.

## Freeze and deliver

Ardot is the sole visual master. Do not rewrite the middle of an article from
`article.blocks` or mix chapter screenshots with a new HTML template.
Use [transport fidelity](references/ardot-transport-fidelity.md) and
[audit repair integration](references/audit-repair-integration.md) for the
implemented adapter, responsive review and dynamic draft path.

The raw-capture adapter accepts resolved current Ardot node responses plus
semantic bindings. It derives geometry, text, styles and state tree hashes;
unsupported transforms, incomplete trees or missing nodes require a reread or
an Ardot revision, not invented normalized facts.
Freeze with `export_ardot_handoff.py RAW_CAPTURE --bindings BINDINGS --output DIR`.
Exported assets must be downloaded originals from their exact nodes.

The handoff freezes production intent and transport together. Revalidate
component count, SVG choice, backgrounds and route at final compile and again
before draft mutation. After human Ardot edits, refreeze; if the selected scope
changed, reconfirm first. A hash does not replace editorial approval.

The responsive transport uses container-relative typography. It remains a
candidate until the saved draft retains the exact styles and real 320/390/430px
measurements pass. Do not claim generic WeChat compatibility from a local
browser test. Never silently switch to fixed-pixel typography or a flattened
long image when a client rejects container sizing.

Missing signer does not block reversible draft work. For dynamic components:
first save the static-equivalent draft, then update that same draft with the
interaction probe, reopen and inspect it on iOS and Android. With real grouped
editor review, the explicit `--accept-editor-mobile-review` option on compile
and save supports current-session draft delivery, labeled
`current-session-editor-reviewed`, not host-attested or portable.
The stronger live-authority/signed paths remain separate. Structural SVG
preservation alone is not interaction proof; keep pending drafts clearly
marked if the device review is not complete.

The default terminal action is saving and reopening the draft. Formal
publication/group send still needs separate exact user authorization and the
publisher's live gate. Do not serialize publication permission into an
unsigned report.

## Evidence and recovery

Keep code/unit-test, local-browser, real-Ardot, saved-draft and mobile results
separate. Mock tests check contracts, not platform availability.
Identical screenshot pixels are allowed; verify capture provenance separately.
Visual comparison uses local as well as global differences, never just a
whole-image color average.

Use [usage](references/使用说明.md) for CLI details and
[breakpoint recovery](references/end-to-end-breakpoint-matrix.md) for recovery.
Retain create-once assets and transaction journals. Resume confirmed completed
steps; never retry an ambiguous external write without reconciling its outcome.
For capability/compatibility failures, report the exact failed stage and safe
continuation. Do not manufacture evidence or add another irrelevant login gate.
