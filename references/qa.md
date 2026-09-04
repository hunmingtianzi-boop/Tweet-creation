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

- `production_preferences.micro_component_count` 可选 `0..4`；`article.visual_kit.selected_roles` 从四类角色目录中选取同样数量并与资产一一对应。数量大于零时，每枚不同派生图都必须通过 RGBA8/robust Alpha/紧裁切/无 matte/尺寸/宽高比检查，并记录 Ardot 原生组件 file/node/name 与准确 asset SHA；数量为零时不用色块或旧素材伪造小组件。
- 当前 release 只支持 Codex Desktop；透明小组件的默认源图来自当前会话中的 `chatgpt-web-image-route` + `codex-with-chatgpt` + 内置 Browser，不使用 Computer Use、外部浏览器、截图、Canvas、剪贴板或远程 URL 代替原图下载。其他 harness 的 provider 映射只是未来移植验收条件，不是本版本可选路线。
- 每枚微组件有完整 `org-wechat-micro-cutout-derivation-v1` 链：raw 下载、prompt/provider route、处理器/配置、报告与 derivative SHA 均一致。Ardot 和 transport 只引用 `assets/derived/` 的终态 SHA，raw 不可见。
- 透明图经过可确定解码的像素检查；预览棋盘格不能当作透明证明。小组件 PNG 只含主体，不含白/黑/色底板或用于留白的巨大透明画布。
- 每个 slot 可在生成前选择 native-alpha 原图或可安全分离的计划内 controlled-key 原图；两者都不是终稿通行证。最终透明 derivative 仍不得存在全画布 low-Alpha 色污、脱离碎片、中性/彩色/key-color halo 或纹理化不规则底板；受控 key 背景不均、主体碰边或复杂透明材质无法安全分离时，必须换源或重生成，不放宽终稿门槛。
- Inspect the native Ardot article and its high-impact component screenshots at 390 px before creating transport files.
- Body type remains readable and paragraphs are not dense walls of text.
- Expressive typography appears only in 2–4 approved high-impact moments, uses grounded article copy, licensed/system fonts, native editable Ardot text nodes, and a standard fallback; no generated or flattened Chinese title image replaces the source text.
- Default body typography is checked against the selected density mode; `compact-editorial` uses 15–17 px type, 1.45–1.62 line-height, -0.2–0 px Chinese tracking, 8–14 px paragraph spacing, and 24–40 px major intra-section gaps.
- Five screenshot-backed density samples record content occupancy and largest empty region; ordinary sections target 68%–90% occupancy and at most 20% accidental empty space.
- `generate_backgrounds: true` 时，AI 底图属于同一个已登记 family，含 master 和 companion 变体；文字位于近纯色安全区，不逐章切换无关风格。`generate_backgrounds: false` 时使用 Ardot 原生 surface/渐变/可编辑矢量层，不要为满足旧门槛生成伪底图；两种模式都必须验证全文明暗连续与正文对比度。
- Every eligible opaque generated background/cover is a distinct marked derivative with authenticated `local_verified` evidence, matching source/final SHA-256 values and public report hash. Registration and every ready-producing validation rerun external-key pixel authentication plus the complete-frame 390px/JPEG-Q75 simulation; self-reported JSON cannot pass. The unmarked master is preserved in a Git-ignored private-input directory; public evidence contains no raw watermark ID or personal/account identity.
- Photographs, `documentary-evidence`, official/user-supplied images, logos, QR codes, transparent micro assets, SVG/SMIL, and QA screenshots remain byte-unaltered by the V1 watermark stage.
- Covers and transitions have intentional overlay space.
- Galleries show a visible next-card edge and a swipe cue.
- Closed boxes are at most 20% of content sections and never occur consecutively.
- At least three moments visibly break symmetry or enter from the text edge.
- Every actual visual-kit instance appears in a hashed Ardot instance inventory and node-property export; repeated roles are all covered, not sampled. Every node-properties export declares `complete_descendant_census: true`, its `visible_descendant_count` equals the full `nodes` length, and every image/illustration carries a bundle-local `rendered_asset_file` whose actual/declared SHA-256 both equal the approved cutout SHA.
- A micro illustration layer occupies at most 72% of the 390 px row and the complete micro component at most 82%. For selected count `N`, placements span at least `min(3, N)` reviewed sections, distinct horizontal offsets, and composition relations. At `N >= 2`, they also use both text edges and visible scale variation; at `N = 0`, micro-layout evidence is empty/not applicable.
- Copy-bearing micro components contain native text nodes and no enclosing closed shape. Primary copy is at least 22 px and 1.35× its screenshot-bound body text, with scale contrast plus another non-frame technique; glyph outlines never become a rectangular text frame.
- Long articles vary section rhythm through open text, micro illustrations, continuous paths, image breaks, full-width transitions, and quiet whitespace.
- Every semantic block does not own a background, border, radius, or shadow.
- `production_preferences.use_svg: true` 时使用 `dynamic-default` 并规划 2–3 个 semantic interaction modules，而不是 2–3 张子卡或 SVG 节点；2 个占据实际 early + middle 章节，3 个再增加 late。`use_svg: false` 时使用 `static-selected`、`target_module_count: 0` 和空 modules，不再要求重复的静态例外理由。
- 动态模式下，重复卡组只算一个 module。每个子 transport instance 仍使用唯一、有原文依据的 fallback key 和 `sha256:<64 hex>`；装饰动效、已选微插图和表现型字体不计数。目标账号能力证据缺失仍会在投递层选择静态 payload，不改写已确认的创作偏好。
- A separate visual review v3 records five distinct local 390 px Ardot node exports, hashes, dimensions, capture metadata, density-to-screenshot bindings, a complete micro-component instance inventory, hashed node-property exports, and every required visual check; article JSON cannot self-certify the design.
- Images have useful alt text and important subjects remain legible on a phone.
- No clipped text, overflow, accidental large empty region, or component instance with the wrong organization mode remains.
- `index.html` may be used only to debug the final transport adapter; it does not replace Ardot visual review.

## WeChat handoff

- Handoff schema v5 binds `tuozhe-ai-ecosystem-workflow-v1` and a complete `ardot-current-root-layer-export-v1`. `ardot-root-revision-v1` includes exact `transport_sections`, `body_asset_ids`, and the complete unique visible `component_order`; its node IDs must equal all transported section/layer source nodes exactly once. `ardot-transport-revision-v1` must be that root's exact projection. Every older bundle must be refrozen rather than grandfathered.
- Only a frozen layer export may produce either `wechat-candidate.html` for `current-session-draft` or final `wechat.html` for `portable-signed-audit`. Article-JSON template output is `authoring-preview.html`, declares `delivery_eligible: false`, and is forbidden as a draft payload.
- In `current-session-draft`, `candidate-report.json` must bind the exact fresh live export and candidate HTML, report `candidate_valid: true`, `draft_write_eligible: false` and `portable_audit_verified: false`, and be revalidated with `--session-draft` immediately before the same host writes the draft. The reversible write is authorized only as a current-host action policy backed by that host's visible trace; unsigned local artifacts never carry the entitlement. In `portable-signed-audit`, `compile-report.json.artifact_binding.wechat_html` matches the exact final path identity/SHA/bytes/revision and `artifact_binding.live_root_receipt` matches the Ed25519 receipt. Candidate and final reports are not interchangeable.
- Every top-level transport section maps one unique Ardot chapter/section node. Chapter `y` values form a continuous non-overlapping cover from 0 to artboard bottom; height sums alone are insufficient. QA/contact/section-composite screenshots are evidence-only and never body assets. Each chapter's rendered background layer—whether a generated-family asset or an Ardot-native surface/gradient/editable-vector composition—is exported as a text-free PNG at exactly `1170 × (chapter_height × 3)`; native text nodes and approved cutouts remain independent source-node layers with exact hashes.
- A separately captured fresh current-root read from the active Ardot host matches the frozen file/root, text, section geometry, complete layer/style/source-node census and body asset set. It has a timezone-aware `captured_at` strictly later than freeze and different bytes/inode. Both modes require the real current-host reread trace. A real `host.receipt.attest` callable is optional for current-session draft work and required only to upgrade to `portable-signed-audit`; then it issues a maximum-ten-minute `ardot-host-live-read-receipt-v1` signed with a host-only Ed25519 key. Missing host integration blocks the portable claim, while reused/copied evidence, a model-written receipt, or a missing live host trace blocks both modes.
- Native text style uses one explicit supported WeChat system family (`system-sans-cn` or `system-serif-cn`) and the full allowlisted style record. Unsupported fonts, extra unrendered properties, crop, rotation, blend or mask never silently degrade.
- `scripts/validate_workflow_attribution.py` derives the node facts from a hash-bound current-root export before delivery. After save, rerun it with `--saved-draft-visible-text FILE --require-readback`; the actual reopened draft contains the credit exactly once as its final normalized visible text. A surviving `data-*` marker alone is not evidence.
- `wechat.html` uses one exact transport root and inline styles, with no `<script>`, `<style>`, form, iframe, external stylesheet, unsigned nested DOM, extra layer attributes, repeated known image, or root-external content.
- Static `wechat.html` contains one independently hash-bound `data-transport-role="article-micro"` image for every frozen cutout instance; each uses its Ardot-derived partial-width geometry no larger than 72%, and has no border, radius, filled copy frame, backplate, or generic full-width image container.
- Reopened-draft readback is chapter-by-chapter: target account/draft/observation time, section mapping, native text-node order/hash, actual `mmbiz.qpic.cn` hosted asset IDs/URLs plus downloaded SHA-256, and one hash-bound 390 px screenshot per chapter. Current-session validation requires the candidate HTML/report, original live export, `--require-readback --session-draft`, `session_readback_structural_match: true`, and a host trace showing the real write/reopen. Portable validation additionally requires both receipts and the final compile report. A detached or locally fabricated readback, whole-article word count, or surviving marker cannot replace either evidence chain.
- Dynamic candidates use policy `wechat-svg-smil-self-v1`: only no-ID inline SVG `<set>` / `<animateTransform>` with self `begin="click"`, plus inline CSS horizontal swipe. Reject `<details>`, `<summary>`, JavaScript, `on*`, `javascript:`, every transport `id`, `foo.click`, `<use>`, fragment references, `<foreignObject>`, and unprobed SMIL.
- Every transport instance and its static information-equivalent share a unique `data-fallback-key` and normalized `sha256:<64 hex>` content hash. Missing, duplicated, or mismatched hashes block the candidate.
- Every semantic module has current-revision native Ardot `closed`, `open`, and `fallback` state evidence. Its group component lists all covered instance IDs and semantic hashes in order; all three states have distinct nodes, local 390 px exports, and matching file hashes, and closed/open cannot be identical.
- Saved-draft readback matches per-component fallback hashes and SMIL signatures. Readback proves sanitizer survival only; it does not certify runtime behavior.
- Dynamic delivery requires an unexpired profile for the exact target account and policy version, with recorded iOS and Android WeChat versions and preview evidence. Missing, pending, failed, expired, or mismatched profiles force the static fallback in the same draft.
- All local body images are ready to upload and replace with WeChat-hosted URLs.
- Every locally verified carrier is downloaded from the saved draft's actual WeChat CDN/cover URL and detected again. Required-mode delivery remains blocked until it is `transport_verified`; HTML readback alone does not satisfy this check.
- SVG `<image>` references use only target-account WeChat `mmbiz.qpic.cn` URLs after upload.
- Cover material is handled separately from body images. The current target account's permanent-material `media_id` is used as `thumb_media_id`, and the saved draft visibly contains the expected cover.
- `candidate-report.json` records the current-session structural binding and can never claim portable audit; `compile-report.json` records the signed frozen source/revision, live-root preflight, copied assets, final HTML artifact binding, warnings, and errors.
- Create a draft first. Do not perform formal publication without explicit confirmation.
