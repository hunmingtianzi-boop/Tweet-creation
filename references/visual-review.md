# Ardot 截图验收

文章 JSON 不能通过一个 `visual_reviewed: true` 自我证明质量。交付前必须从实际 Ardot 文章根采集截图。五章及以上至少覆盖下面五类；少于五章的短文逐章覆盖即可，不新增虚构章节：

- `hero`；
- `chapter`；
- `evidence`（照片、事实、案例或数据）；
- `complex-section`（步骤、角色、流程或复杂图文）；
- `cta`。

独立 review JSON 使用 `schema_version: 3`，需要 Ardot 文件、页面、文章根节点，以及 `capture.source: ardot-node-export`、导出时间和相同 article root。每张截图必须是本地 390 px PNG，并记录节点 ID、章节 ID、SHA-256、实际宽高；远程 URL、重复文件或哈希不符均失败。

`capture` 还必须指向当前 article `qa/` 内的完整 `ardot-article-node-census` 和 `ardot-host-export-receipt-v1`，两者的文件 SHA 必须匹配。Census 绑定当前 revision/root/390 px，完整覆盖本次所有截图 section，并使 `visible_descendant_count` 与全部 nodes 数量一致。Receipt 绑定 provider/session/request/tool、census SHA 和全部截图 SHA。当前作者层只允许如实声明 `assurance_level: current-session-host-trace` 与 `host_enforced: false`；它不依赖当前 Codex Desktop 未提供的 filesystem lease，也不得伪称是宿主签名证据。需要 portable host-enforced assurance 时由 runtime/delivery 另行验签。

当文章有 interaction modules 时，`ardot.article_node_id` 还必须等于 `interaction_plan.article_root_node_id`，`capture.revision_hash` 必须等于 `interaction_plan.ardot_revision_hash`，review 与交互 group components 也必须属于当前组织的同一 Ardot 文件。这防止把旧截图与新 revision 字段拼接成伪证据。

还要为这些节点记录 `density.mode`、`measured_from: ardot-node-properties-and-screenshot`、测量时间与密度样本。每个样本用 `screenshot_sha256` 绑定对应截图，并包含 `major_gap_px` 与实测 `body_text_contrast_ratio >= 4.5`；字段见 [information-density.md](information-density.md)。

## 微组件节点证据

schema v3 以 `production_preferences.micro_component_count` 和 `article.visual_kit.selected_roles` 决定 `micro_component_layout` 的范围。数量 `N > 0` 时，不接受手填 `image_width_ratio`、`horizontal_offset_ratio`、`font_size` 或 `enclosure: none`，必须从当前 article root 导出两类本地 JSON：

1. `ardot-article-instance-inventory`：列出文章中所有由已选 visual-kit component definitions 产生的实际 `instance_node_id` 与 `source_component_node_id`。相同 role 可以出现多次，但 placements 必须完整覆盖 inventory，不能抽样。
2. `ardot-node-properties`：每个实例一份，包含 390 px article root、instance bounds，以及所有可见 image/illustration、text、closed-shape、vector-accent 子节点的 node ID、bounds、font size、fill alpha 与 stroke width。顶层必须声明 `complete_descendant_census: true`，且 `visible_descendant_count` 必须等于 `nodes` 长度；未知节点类型、漏报节点和 closed-shape 缺少可见性字段均失败。每个 image/illustration node 还必须记录已批准 cutout 的 `asset_id`、`asset_sha256`、`rendered_asset_file` 与 `rendered_asset_sha256`；rendered 文件必须留在该 node-properties 所在 visual-review bundle 内，实际 SHA 必须与已批准 cutout 完全一致。任何可见 closed-shape 单独或合并覆盖 image/illustration 80% 以上均视为禁止 backplate。文件必须记录 SHA-256，并与对应 390 px 截图哈希绑定。

`N = 0` 时，`micro_component_layout` 可缺省或提供空 placements/inventory，不得为了凑证据插入通用装饰、旧稿资产或色块。

`horizontal_offset_ratio` 由校验器按 `(instance_center_x / 390) - 0.5` 计算；图片与组件宽度也由 bounds 除以 390 得到。`closed-shape` 只用于真实闭合容器；字形轮廓或偏移层使用 `vector-accent`，不得伪报为开放点缀。

```json
{
  "micro_component_layout": {
    "measured_from": "ardot-node-properties-and-screenshot",
    "measured_at": "2026-08-30T10:00:00+08:00",
    "inventory_file": "qa/micro-component-inventory.json",
    "inventory_sha256": "<sha256 of the inventory file>",
    "placements": [
      {
        "id": "opening-floating-spot-1",
        "role": "floating-spot",
        "source_component_node_id": "20:1",
        "instance_node_id": "80:1",
        "screenshot_node_id": "30:1",
        "screenshot_sha256": "<sha256 of the 390 px screenshot>",
        "node_properties_file": "qa/micro-1-nodes.json",
        "node_properties_sha256": "<sha256 of the node export>",
        "composition_relation": "text-edge-entry"
      }
    ]
  }
}
```

Inventory 与逐实例文件的最小规范：

```json
{
  "schema_version": 1,
  "source": "ardot-article-instance-inventory",
  "article_root_node_id": "30:0",
  "article_width_px": 390,
  "instances": [
    {"instance_node_id": "80:1", "source_component_node_id": "20:1"}
  ]
}
```

```json
{
  "schema_version": 1,
  "source": "ardot-node-properties",
  "article_root_node_id": "30:0",
  "article_width_px": 390,
  "instance": {
    "node_id": "80:1",
    "source_component_node_id": "20:1",
    "bounds": {"x": 24, "y": 120, "width": 148, "height": 170}
  },
  "complete_descendant_census": true,
  "visible_descendant_count": 3,
  "nodes": [
    {"node_id": "80:2", "kind": "illustration", "asset_id": "spot.opening", "asset_sha256": "<approved cutout sha256>", "rendered_asset_file": "micro-1-rendered.png", "rendered_asset_sha256": "<same approved cutout sha256>", "bounds": {"x": 24, "y": 120, "width": 116, "height": 96}},
    {"node_id": "80:3", "kind": "text", "role": "primary-copy", "font_size_px": 24, "emphasis_techniques": ["scale-contrast", "mixed-weight"], "bounds": {"x": 42, "y": 228, "width": 106, "height": 34}},
    {"node_id": "80:4", "kind": "vector-accent", "is_closed": false, "bounds": {"x": 30, "y": 222, "width": 6, "height": 42}}
  ]
}
```

可见的矩形、圆角矩形、椭圆底板、chip 或 badge 一律归一化为 `kind: closed-shape`，并写入数值型 `fill_alpha` 与 `stroke_width_px`；缺报可见闭合节点等同伪造证据。沿字形的轮廓/偏移层和开放线条归入 `vector-accent`，并显式写入 `is_closed: false`。

校验器从这些文件强制得到：图片层宽度 `<= 0.72`、整个实例宽度 `<= 0.82`；已选数量 `N` 的布局证据至少分布在 `min(3, N)` 个截图区段，并有同样数量的不同偏移与构图关系。`N >= 2` 时还需同时有左右偏移和可见尺度变化。含字实例不得有任何可见 `closed-shape` 包围文字；`primary-copy` 必须是原生 text node，至少 22 px、至少为同截图 density 正文的 1.35 倍，并使用 `scale-contrast` 加另一种非框体强调手法。

以下检查必须全部为 `pass`：

`subject_relevance`, `style_coherence`, `no_clipped_ornaments`, `scale_variation`, `photo_illustration_harmony`, `no_generic_ai_decoration`, `no_unexplained_labels`, `editorial_rhythm`, `mobile_legibility`, `open_composition`, `information_density`, `background_surface_unity`, `reading_surface_contrast`, `expressive_typography`, `art_type_construction`, `no_baked_art_text`。`generate_backgrounds: true` 时另需 `background_family_coherence`；`N > 0` 时另需 `no_framed_micro_copy`, `no_full_width_micro_image`, `staggered_micro_composition`, `micro_copy_hierarchy`。

`background_surface_unity` 确认整篇没有黑/白大色块跳变。`generate_backgrounds: true` 时，底图必须属于校准过的同一明暗面与材质家族；`false` 时，验收同一 route 的 Ardot 原生 surfaces/渐变/可编辑矢量层的连续性。`reading_surface_contrast` 确认叠字后的实际截图中正文没有与底层重合、吞字或低于 4.5:1。`expressive_typography` 确认标题字有节制地出现在高影响位置，字重、断行、层级和组织性格匹配，不侵入正文阅读。`art_type_construction` 确认每个艺术字时刻确实组合了批准 recipe 的至少两种非字体手法和足够的可编辑图层，而不是只换字体。`no_baked_art_text` 确认标题仍是 Ardot 可编辑文本节点，不是 AI 生成字图、扁平图片或仅轮廓存档。

`N > 0` 时的 micro checks 不是独立的人工通行证：只要 inventory、node export、截图哈希或派生几何/字号失败，整个 review 仍失败，即使 `checks` 中写了 `pass`。

不再接受字符串 `"pass"`。每个主观项是证据对象：`status: pass`、当前 `evidence_node_ids`、精确对应的 `screenshot_sha256s`、`reviewer.kind/id` 和带时区 `reviewed_at`。字号、行高、字距、段距、major gap、占用率、最大空洞和对比度从 census 节点重算；全篇无框/错落和艺术字也从全量 node census 而非手填 ratio 验收。

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_review.py" visual-review.json --article article.json
```

把 review 文件路径写入 `article.visual_review_file`。作者层门禁会重新校验文章 ID、组织 ID、与篇幅匹配的节点证据、实际密度测量与适用视觉项（密度建议范围不作硬阻断）。通过后还必须冻结 handoff v5 完整 current-root/layer export，并在编译前通过当前宿主真实重读 live root。无 signer 时使用带 `--session-draft` 的 gate/compiler，只生成精确绑定的 `wechat-candidate.html` / `candidate-report.json`，并在同一宿主中完成微信写入、重开和逐章 readback；其 `portable_audit_verified` 必须为 false。有 Ed25519 attestor 时才可进入 `portable-signed-audit`，使用两份 receipt 和终态 `wechat.html` / `compile-report.json` 链。视觉验收本身不授权正式发表或群发。
