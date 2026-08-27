# Organization onboarding

Use onboarding when the requested organization has no validated organization pack or when its identity has materially changed.

## Minimum evidence

Collect the best available subset of:

- official website, official account profile, charter, or organization introduction;
- current official descriptions, raw copy, program documents, and user-approved text evidence from more than one content type;
- canonical logo and any published brand guide;
- representative event, team, project, venue, or product photographs;
- current programs, teams, audience segments, and calls to action;
- user-supplied corrections and preferences.

Prefer current official or user-provided sources. Past article text may inform voice only when the user explicitly permits it; never open its screenshots, layout, PDF preview, or Ardot source for visual calibration. Record every allowed source in `sources.json`; do not paste large source documents into the organization pack.

Before visual work, complete the source-zero provenance fields: `visual_reference_policy: source-zero`, the current `visual_input_source_ids`, all four excluded legacy-visual kinds, and `isolation_reviewed_at`. Full-article work remains blocked without them.

## Research output

Summarize evidence into four separate decisions:

1. **Identity:** purpose, audiences, content pillars, differentiators, and institutional constraints.
2. **Voice:** tone traits, sentence rhythm, headline behavior, preferred vocabulary, and expressions to avoid.
3. **Visual system:** tokens, motifs, photography behavior, generated-image boundaries, and unsuitable visual clichés.
4. **Editorial system:** recurring article types, evidence requirements, recommended semantic blocks, and calls to action.

Score the following axes from 0 to 100 and add short evidence notes in the research working notes:

- `authority`: informal peer group → institutional authority;
- `technical`: general-interest communication → specialist depth;
- `warmth`: restrained/objective → personal/community-oriented;
- `experimental`: conventional/stable → visually experimental;
- `action`: awareness/record → recruitment, registration, or conversion.

Do not infer the axes from organization category alone.

## Visual-route selection

Propose two or three routes when the evidence permits multiple interpretations. Each route needs:

- an ID and plain-language label;
- intended article types;
- layout family;
- dominant image or illustration style;
- motifs and explicit avoid rules;
- a short explanation tied to evidence.

Choose a default only after user confirmation or when the organization already has a clear, consistently used system. Otherwise mark the pack `provisional`.

## Calibration strip, then first article

First compare two or three five-part Ardot calibration strips and record the approved route, background family, plus benchmark file/page/node under `organization.visual.calibration`. Only then create the first real article as a 390 px native Ardot board and use it to test:

- whether the voice sounds like the organization rather than a generic campaign;
- whether verified facts remain distinguishable from promotional interpretation;
- whether the visual route survives a complete mobile article, not only a cover;
- whether supplied photos, logos, and QR codes integrate cleanly;
- whether the component recommendations suit the article’s actual information.
- whether an article-specific visual kit was generated before layout and turned into four reusable ornament roles;
- whether the article reads as an open editorial composition rather than a stack of rounded cards.

After review, update the organization pack instead of accumulating one-off prompt rules.

Preserve the approved strip inside the new organization's Ardot file. Do not expose the first article as a cross-organization visual example. Use a separate screenshot-backed `visual_review_file` for each article; do not self-report layout quality inside the article JSON.
