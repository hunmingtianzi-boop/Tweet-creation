# Ardot → 微信高保真传输契约

这一层专门阻止一类错误：首尾用 Ardot 整段截图，中间按感觉重写 HTML，交互再手画一份 SVG。这三种来源即使内容一致，也不是同一份设计。

## 单一母版

视觉定稿后，最终投递不再读取 `article.blocks` 来选模板、宽度、间距或色面。当前 Ardot article root 是唯一视觉母版；`article.json` 只留作内容语义与事实校验。

从当前 root 冻结 `ardot-current-root-layer-export-v1`，并在同一份哈希绑定的 `ardot-current-root-export` 中保存完整 `transport_sections` 与 `body_asset_ids`。两边必须逐章、逐实例、逐层全等；只改 section/source node、坐标、z-order、字体/渲染样式、底图、裁切、小组件 SHA 或交互状态都会使 root/transport revision 失效。临近编译还要通过当前 Ardot 宿主重新读取一次 root，生成另一份 live export；冻结文件不能冒充自己的 live 证明。

## 逐章图层

每个 chapter 必须一对一绑定唯一 `section_node_id`，chapter 使用 `article-root-390-v1` 坐标；章内图层使用 section-local 390px 坐标。首章必须从 `y=0` 开始，后章 `y` 必须精确等于前章 bottom，末章 bottom 必须精确等于 artboard height；仅比较高度总和不合格，因为重叠与空洞可能抵消。

每章至少冻结以下信息。背景 `z_index` 固定为 0，其他文字/装饰/交互图层使用唯一整数 `z_index` 保留 Ardot 层级；阅读顺序仍由 text node `order` 独立决定：

- `reference_screenshot`：同一 section node 的本地 `390 × chapter_height` Ardot 截图与 SHA，只能作证据，不能进正文。
- `background_layer`：必须是完整章节的 `1170 × (chapter_height × 3)` PNG，`export_scale: 3`。除 `contains_text: false` / `text_baked: false` / `text_node_count: 0` 外，还必须附带本地哈希绑定的 `ardot-background-only-node-export-v1`，由该 node export 证明 file/root/section/background node、资产 SHA 与 0 个文字后代。自报布尔值或文件名不算证据。
- `visible_text_nodes`：Ardot 原生可编辑文字，包含 source node、归一化文本 SHA、顺序、语义标签、几何，以及完整受支持 style。字体族只能选择 `system-sans-cn` / `system-serif-cn` 的明确微信原生映射；未知字体/样式不得静默替换。
- `decorations`：与底图独立的 `article-micro` 图层，保留真实 `source_node_id`、已验收 cutout asset ID/SHA、启动时选定的 0–4 类语义 role、几何与受支持 render style。`independent` 必须为 `true`，`contained_in_background` 必须为 `false`；选择 0 时数组为空。
- `photos`：显式数组，每张真实照片保留真实 source node、`role: documentary-evidence`、`source_id`、asset ID/SHA、独立几何、crop/object-position 与图层顺序；不得焚入 AI 底图或章节合成图。
- `interaction`：SVG 只能来自本地哈希绑定的 `ardot-interaction-state-export-v1`，其 file/root/section/source node、closed/open/fallback states 与 `svg_structure_sha256` 都必须与当前导出一致。`structure_sha256` 由校验器对实际 frozen SVG 结构重算，不接受自报。SVG 模式同时冻结 `fallback_key` / `fallback_semantic_sha256` / `fallback_asset`；否则明确选择信息等价的 `static-fallback`。编译 HTML 和草稿回读都从实际 SVG 字节重算同一签名。

真实照片作为事实证据保持独立图层，可以是矩形；它不得被误当作 AI 底图或透明小组件。

## 抠图与底图的边界

透明小组件只含主体、自然阴影和开放笔触。白底、黑底、色板、卡片、边框、整段版式与为排版预留的巨大透明画布都不属于组件。留白在 Ardot 中生成，不烘进 PNG。

`validate_micro_asset` 必须在资产登记、visual-kit ready、Ardot instance 回读和 final transport 四个节点重跑。它要求 8-bit RGBA 可确定解码，用 robust Alpha bbox 忽略微小飞点，阻断超大透明画布、截边、矩形/圆角/近实色 matte。Ardot node-property export 还必须证明 raster node 的 asset ID/SHA 与登记文件完全一致，且没有可见 closed-shape backplate。

## 编译命令

`article.json` 模板适配器只能显式用于作者调试：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" article.json \
  --org organizations/<organization-id> \
  --authoring-preview \
  --output output/<organization-id>/<slug>/authoring
```

它输出 `authoring-preview.html`、`delivery_eligible: false` 和稳定阻断码 `transport.source.article_json_renderer_forbidden`，不产生 `wechat.html`。

只有冻结图层输入可产生草稿候选或终态审计版。保证分两档：

- `current-session-draft`：不要求 signer，但必须在同一当前宿主轨迹中完成真实 Ardot reread、live-root 结构对比、`wechat-candidate.html` / `candidate-report.json` 精确绑定、微信草稿写入、重新打开和逐章 readback。未签名的 candidate/report 只证明结构对应，固定 `draft_write_eligible: false`、`delivery_eligible: false`、`finalization_verified: false` 和 `portable_audit_verified: false`。当前宿主可依据自己持有的实时轨迹执行可逆的草稿写入，但该权限不序列化进本地报告，也不能离开当前宿主轨迹独立审计。
- `portable-signed-audit`：保留两份 Ed25519 receipt、secure final `wechat.html` / `compile-report.json` 和完整 path/bytes/readback 链，用于可携带审计。

`current-session-draft` 命令：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --intended-html output/<organization-id>/<slug>/delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --require-live-root --session-draft
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json \
  --session-draft \
  --output output/<organization-id>/<slug>/delivery \
  --check
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --html output/<organization-id>/<slug>/delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --compile-report output/<organization-id>/<slug>/delivery/candidate-report.json \
  --require-compile-report --session-draft
```

`portable-signed-audit` 命令：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --intended-html output/<organization-id>/<slug>/delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --require-live-root
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --upload-map delivery/upload-map.json \
  --output output/<organization-id>/<slug>/delivery \
  --check
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --html output/<organization-id>/<slug>/delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --compile-report output/<organization-id>/<slug>/delivery/compile-report.json \
  --require-compile-report
```

发布级 Python API 也遵守同一边界：`compile_frozen_transport()` 和 `validate_transport_fidelity()` 会在函数内部再次验证 isolated runner，普通 `import` 后直接调用会在写出任何终态产物前失败。`compile_frozen_transport_candidate()` / `validate_transport_fidelity_diagnostic()` 是 `current-session-draft` 的结构编译/校验 API；它们只产生 `wechat-candidate.html` 和 `candidate-report.json`，只有当宿主轨迹独立显示真实 Ardot/微信操作时才能用于本次草稿。它们不产生 portable/finalization 声明。`article.json --authoring-preview` 仍是不可投递的另一条路径，不得与 session candidate 混淆。

`qa/live-current-root.json` must be a new host-owned Ardot capture, not the frozen evidence renamed or copied. Its timezone-aware `captured_at` must be strictly later, while its content/layer/source/style/asset revision remains identical. Both assurance modes require that fresh capture and the current host's visible reread trace. `portable-signed-audit` additionally needs `qa/live-current-root-receipt.json` with source `ardot-host-live-read-receipt-v1`; a real `host.receipt.attest` callable signs it with a host-only Ed25519 private key immediately after the real tool response. The repository reads the matching public key only from a protected root-owned trust store. Missing host integration blocks the portable assurance upgrade, not current-session draft creation. An unsigned local JSON must never be presented as an equivalent signed receipt.

编译器只按冻结坐标/样式/顺序映射图层，不再按 block type 选新模板。每个顶层章节写入 chapter/section node；每个文字、图片和互动 layer 使用当前 root 的真实 source node 作为 layer ID，asset ID 只表示复用的像素资源。postflight 除逐层 render signature 与实际图片字节外，还执行严格 DOM 子树语法。Session 候选报告绑定它的 exact live export 与 `wechat-candidate.html` 字节；签名模式的 `compile-report.json` 还终态绑定 `wechat.html` 路径身份、SHA-256、字节数、handoff SHA、revision 和原 Ed25519 live receipt。两种报告不可互换，仅重写本地 report 不能伪造宿主操作。

## 微信回读

保存并重新打开草稿后，从实际编辑器导出 `wechat-saved-draft-readback-v1`。顶层必须绑定 `target_account_ref`、`draft_id`和 `observed_at`；每章必须包含：

- chapter/section node 映射；
- 可见文字 node IDs 和整章归一化文本 SHA；
- 全部 hosted asset IDs、实际 HTTPS URL 和下载字节 SHA-256；
- 重新打开草稿后的 `390 × chapter_height` 截图路径与 SHA。
- 当前 `transport_revision_hash`，以及从草稿中实际保留的 SVG 导出文件重算的结构签名。hosted asset 同时提供本地下载文件，校验器自行重算 `downloaded_sha256`。

两档都要求在当前微信宿主中实际写入、重新打开草稿并从真实编辑器导出 readback。`current-session-draft` 使用当前宿主轨迹加 `--session-draft --require-readback` 结构验收，并要求 `session_readback_structural_match: true`。`portable-signed-audit` 紧接真实回读再签发 `wechat-host-saved-draft-receipt-v1`，绑定账号/草稿、runtime binding、live receipt、终态 HTML、compile report 与 readback 全部字节。仅在本地写入 mmbiz URL、下载文件或截图不是任一模式的微信回读证据。

`current-session-draft` 回读命令：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --compile-report delivery/candidate-report.json --require-compile-report \
  --expected-target-account 'exact-account-ref-from-delivery-preflight' \
  --readback saved-draft-readback.json --require-readback --session-draft
```

`portable-signed-audit` 回读命令：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --compile-report delivery/compile-report.json \
  --require-compile-report \
  --expected-target-account 'exact-account-ref-from-delivery-preflight' \
  --readback saved-draft-readback.json \
  --readback-receipt saved-draft-readback-receipt.json \
  --require-readback
```

少章、gap/overlap、换序、改文、换图、缺下载哈希、HTML 字节变化、缺 390 px 证据、交互签名不一致均阻断。`current-session-draft` 缺宿主操作轨迹或声称 `portable_audit_verified: true` 也阻断；`portable-signed-audit` 缺任一 receipt 则不能获得该保证。字体只允许冻结时已明确选择的微信原生白名单映射；不得在传输时临时换字体，更不得把文字焚进图片或为了“看起来像”再设计一套中间章节。两种模式均只停在草稿，正式发表/群发需用户单独明确确认。
