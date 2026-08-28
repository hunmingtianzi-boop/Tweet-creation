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

- `article.visual_kit` 覆盖四类角色、四枚不同生成图；每枚通过 Alpha/尺寸/宽高比检查，并记录 Ardot 原生组件 file/node/name。
- 透明图经过 Alpha 文件检查；预览棋盘格不能当作透明证明。
- Inspect the native Ardot article and its high-impact component screenshots at 390 px before creating transport files.
- Body type remains readable and paragraphs are not dense walls of text.
- Expressive typography appears only in 2–4 approved high-impact moments, uses grounded article copy, licensed/system fonts, native editable Ardot text nodes, and a standard fallback; no generated or flattened Chinese title image replaces the source text.
- Default body typography is checked against the selected density mode; `compact-editorial` uses 15–17 px type, 1.45–1.62 line-height, -0.2–0 px Chinese tracking, 8–14 px paragraph spacing, and 24–40 px major intra-section gaps.
- Five screenshot-backed density samples record content occupancy and largest empty region; ordinary sections target 68%–90% occupancy and at most 20% accidental empty space.
- AI backgrounds, when used, belong to one recorded family with a master and companion variants; copy remains on near-solid safe zones and chapters do not switch to unrelated generated styles.
- Covers and transitions have intentional overlay space.
- Galleries show a visible next-card edge and a swipe cue.
- Closed boxes are at most 20% of content sections and never occur consecutively.
- At least three moments visibly break symmetry or enter from the text edge.
- Long articles vary section rhythm through open text, micro illustrations, continuous paths, image breaks, full-width transitions, and quiet whitespace.
- Every semantic block does not own a background, border, radius, or shadow.
- A normal article has 2–3 semantic interaction modules, not 2–3 child cards or SVG nodes. Two occupy actual early and middle storyboard chapters; three add a late chapter. Modules use distinct reader purposes and source blocks and do not appear as an adjacent component wall.
- A repeated-card group counts as one module. Every child transport instance still has unique grounded copy, fallback key, and `sha256:<64 hex>`; decorative motion, mandatory micro illustrations, and display type do not count.
- A 0–1 module exception records an allowed category, a specific reason, and explicit user/editor confirmation. Missing account capability evidence selects static delivery and does not itself justify skipping the authoring plan.
- A separate visual review v2 records five distinct local 390 px Ardot node exports, hashes, dimensions, capture metadata, density-to-screenshot bindings, and all fourteen required visual checks; article JSON cannot self-certify the design.
- Images have useful alt text and important subjects remain legible on a phone.
- No clipped text, overflow, accidental large empty region, or component instance with the wrong organization mode remains.
- `index.html` may be used only to debug the final transport adapter; it does not replace Ardot visual review.

## WeChat handoff

- `wechat.html` uses inline styles, with no `<script>`, `<style>`, form, iframe, or external stylesheet dependency.
- Dynamic candidates use policy `wechat-svg-smil-self-v1`: only no-ID inline SVG `<set>` / `<animateTransform>` with self `begin="click"`, plus inline CSS horizontal swipe. Reject `<details>`, `<summary>`, JavaScript, `on*`, `javascript:`, every transport `id`, `foo.click`, `<use>`, fragment references, `<foreignObject>`, and unprobed SMIL.
- Every transport instance and its static information-equivalent share a unique `data-fallback-key` and normalized `sha256:<64 hex>` content hash. Missing, duplicated, or mismatched hashes block the candidate.
- Every semantic module has current-revision native Ardot `closed`, `open`, and `fallback` state evidence. Its group component lists all covered instance IDs and semantic hashes in order; all three states have distinct nodes, local 390 px exports, and matching file hashes, and closed/open cannot be identical.
- Saved-draft readback matches per-component fallback hashes and SMIL signatures. Readback proves sanitizer survival only; it does not certify runtime behavior.
- Dynamic delivery requires an unexpired profile for the exact target account and policy version, with recorded iOS and Android WeChat versions and preview evidence. Missing, pending, failed, expired, or mismatched profiles force the static fallback in the same draft.
- All local body images are ready to upload and replace with WeChat-hosted URLs.
- SVG `<image>` references use only target-account WeChat `mmbiz.qpic.cn` URLs after upload.
- Cover material is handled separately from body images. The current target account's permanent-material `media_id` is used as `thumb_media_id`, and the saved draft visibly contains the expected cover.
- `compile-report.json` records organization, route, components, copied assets, warnings, and errors.
- Create a draft first. Do not perform formal publication without explicit confirmation.
