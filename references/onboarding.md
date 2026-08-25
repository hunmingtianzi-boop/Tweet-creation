# Organization onboarding

Use onboarding when the requested organization has no validated organization pack or when its identity has materially changed.

## Minimum evidence

Collect the best available subset of:

- official website, official account profile, charter, or organization introduction;
- five to ten representative past articles, including more than one content type;
- canonical logo and any published brand guide;
- representative event, team, project, venue, or product photographs;
- current programs, teams, audience segments, and calls to action;
- user-supplied corrections and preferences.

Prefer official sources. Historical articles reveal editorial habits but do not override a newer official identity. Record every source in `sources.json`; do not paste large source documents into the organization pack.

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

## First article as calibration

Create the first real article as a 390 px native Ardot board and use it to test:

- whether the voice sounds like the organization rather than a generic campaign;
- whether verified facts remain distinguishable from promotional interpretation;
- whether the visual route survives a complete mobile article, not only a cover;
- whether supplied photos, logos, and QR codes integrate cleanly;
- whether the component recommendations suit the article’s actual information.

After review, update the organization pack instead of accumulating one-off prompt rules.

Record the approved Ardot file, variable mode, page names, and component aliases in `ardot.json`. Preserve the first article as an editable example page for later migration checks.
