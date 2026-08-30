# Ardot 截图验收

文章 JSON 不能通过一个 `visual_reviewed: true` 自我证明质量。交付前必须从实际 Ardot 文章根中截取至少五个不同节点：

- `hero`；
- `chapter`；
- `evidence`（照片、事实、案例或数据）；
- `complex-section`（步骤、角色、流程或复杂图文）；
- `cta`。

独立 review JSON 使用 `schema_version: 3`，需要 Ardot 文件、页面、文章根节点，以及 `capture.source: ardot-node-export`、导出时间和相同 article root。每张截图必须是本地 390 px PNG，并记录节点 ID、章节 ID、SHA-256、实际宽高；远程 URL、重复文件或哈希不符均失败。

当文章有 interaction modules 时，`ardot.article_node_id` 还必须等于 `interaction_plan.article_root_node_id`，`capture.revision_hash` 必须等于 `interaction_plan.ardot_revision_hash`，review 与交互 group components 也必须属于当前组织的同一 Ardot 文件。这防止把旧截图与新 revision 字段拼接成伪证据。

还要为这五个节点记录 `density.mode`、`measured_from: ardot-node-properties-and-screenshot`、测量时间与密度样本。每个样本用 `screenshot_sha256` 绑定对应截图，并包含 `major_gap_px` 与实测 `body_text_contrast_ratio >= 4.5`；字段见 [information-density.md](information-density.md)。

## 微组件节点证据

schema v3 新增 `micro_component_layout`，不接受手填 `image_width_ratio`、`horizontal_offset_ratio`、`font_size` 或 `enclosure: none`。先从当前 article root 导出两类本地 JSON：

1. `ardot-article-instance-inventory`：列出文章中所有由四类 visual-kit component definitions 产生的实际 `instance_node_id` 与 `source_component_node_id`。相同 role 可以出现多次，但 placements 必须完整覆盖 inventory，不能抽样。
2. `ardot-node-properties`：每个实例一份，包含 390 px article root、instance bounds，以及所有 image/illustration、text、closed-shape、vector-accent 子节点的 node ID、bounds、font size、fill alpha 与 stroke width。文件必须记录 SHA-256，并与对应 390 px 截图哈希绑定。

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
  "nodes": [
    {"node_id": "80:2", "kind": "illustration", "bounds": {"x": 24, "y": 120, "width": 116, "height": 96}},
    {"node_id": "80:3", "kind": "text", "role": "primary-copy", "font_size_px": 24, "emphasis_techniques": ["scale-contrast", "mixed-weight"], "bounds": {"x": 42, "y": 228, "width": 106, "height": 34}},
    {"node_id": "80:4", "kind": "vector-accent", "bounds": {"x": 30, "y": 222, "width": 6, "height": 42}}
  ]
}
```

可见的矩形、圆角矩形、椭圆底板、chip 或 badge 一律归一化为 `kind: closed-shape`，并写入 `fill_alpha` 与 `stroke_width_px`；缺报可见闭合节点等同伪造证据。沿字形的轮廓/偏移层和开放线条归入 `vector-accent`。

校验器从这些文件强制得到：图片层宽度 `<= 0.72`、整个实例宽度 `<= 0.82`；四类角色至少分布在三个截图区段，同时有左右偏移、三个不同偏移、三个构图关系和可见尺度变化。含字实例不得有任何可见 `closed-shape` 包围文字；`primary-copy` 必须是原生 text node，至少 22 px、至少为同截图 density 正文的 1.35 倍，并使用 `scale-contrast` 加另一种非框体强调手法。

以下检查必须全部为 `pass`：

`subject_relevance`, `style_coherence`, `no_clipped_ornaments`, `scale_variation`, `photo_illustration_harmony`, `no_generic_ai_decoration`, `no_unexplained_labels`, `editorial_rhythm`, `mobile_legibility`, `open_composition`, `information_density`, `background_family_coherence`, `background_surface_unity`, `reading_surface_contrast`, `expressive_typography`, `art_type_construction`, `no_baked_art_text`, `no_framed_micro_copy`, `no_full_width_micro_image`, `staggered_micro_composition`, `micro_copy_hierarchy`.

`background_surface_unity` 确认整篇没有黑/白大色块跳变，所有底图仍属于校准过的同一明暗面与材质家族。`reading_surface_contrast` 确认叠字后的实际截图中正文没有与底图重合、吞字或低于 4.5:1。`expressive_typography` 确认标题字有节制地出现在高影响位置，字重、断行、层级和组织性格匹配，不侵入正文阅读。`art_type_construction` 确认每个艺术字时刻确实组合了批准 recipe 的至少两种非字体手法和足够的可编辑图层，而不是只换字体。`no_baked_art_text` 确认标题仍是 Ardot 可编辑文本节点，不是 AI 生成字图、扁平图片或仅轮廓存档。

四个新增 micro checks 不是独立的人工通行证：只要 inventory、node export、截图哈希或派生几何/字号失败，整个 review 仍失败，即使 `checks` 中写了 `pass`。

```bash
python3 scripts/build_visual_review.py visual-review.json --article article.json
```

把 review 文件路径写入 `article.visual_review_file`。`compile_wechat.py --check` 会重新校验文章 ID、组织 ID、5 类节点证据、密度范围与全部视觉项；缺一项就不生成可交付结果。
