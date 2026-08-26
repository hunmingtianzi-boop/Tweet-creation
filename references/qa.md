# QA and delivery

## Content

- Organization name, event name, dates, locations, roles, partners, and calls to action match supplied evidence.
- Metrics and attributed quotes resolve to registered source IDs.
- Promotional interpretation is not presented as verified fact.
- No draft markers remain.
- Headline, lead, and CTA serve the current audience and article goal.

## Brand

- Selected route belongs to the organization pack and fits the article type.
- Logo is canonical and not recolored, redrawn, or generated.
- Real-event and real-person claims use supplied photographs or are clearly illustrative.
- Generated imagery contains no baked Chinese copy, fake partner marks, QR codes, or unsupported product details.
- The result could not plausibly belong to a different organization after only changing the logo.

## Mobile layout

- `article.visual_kit` 覆盖四类角色，至少三枚不同生成图，并已做成 Ardot 原生小组件。
- 透明图经过 Alpha 文件检查；预览棋盘格不能当作透明证明。
- Inspect the native Ardot article and its high-impact component screenshots at 390 px before creating transport files.
- Body type remains readable and paragraphs are not dense walls of text.
- Covers and transitions have intentional overlay space.
- Galleries show a visible next-card edge and a swipe cue.
- Closed boxes are at most 20% of content sections and never occur consecutively.
- At least three moments visibly break symmetry or enter from the text edge.
- Long articles vary section rhythm through open text, micro illustrations, continuous paths, image breaks, full-width transitions, and quiet whitespace.
- Every semantic block does not own a background, border, radius, or shadow.
- The measured counts are recorded in `article.layout_review` with `visual_reviewed: true`; unreviewed layouts cannot enter final transport.
- Images have useful alt text and important subjects remain legible on a phone.
- No clipped text, overflow, accidental large empty region, or component instance with the wrong organization mode remains.
- `index.html` may be used only to debug the final transport adapter; it does not replace Ardot visual review.

## WeChat handoff

- `wechat.html` uses inline styles, with no `<script>`, `<style>`, form, iframe, or external stylesheet dependency.
- All local body images are ready to upload and replace with WeChat-hosted URLs.
- Cover material is handled separately from body images.
- `compile-report.json` records organization, route, components, copied assets, warnings, and errors.
- Create a draft first. Do not perform formal publication without explicit confirmation.
