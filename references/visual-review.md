# Ardot 截图验收

文章 JSON 不能通过一个 `visual_reviewed: true` 自我证明质量。交付前必须从实际 Ardot 文章根中截取至少五个不同节点：

- `hero`；
- `chapter`；
- `evidence`（照片、事实、案例或数据）；
- `complex-section`（步骤、角色、流程或复杂图文）；
- `cta`。

独立 review JSON 使用 `schema_version: 2`，需要 Ardot 文件、页面、文章根节点，以及 `capture.source: ardot-node-export`、导出时间和相同 article root。每张截图必须是本地 390 px PNG，并记录节点 ID、章节 ID、SHA-256、实际宽高；远程 URL、重复文件或哈希不符均失败。

还要为这五个节点记录 `density.mode`、`measured_from: ardot-node-properties-and-screenshot`、测量时间与密度样本。每个样本用 `screenshot_sha256` 绑定对应截图，并包含 `major_gap_px`；字段见 [information-density.md](information-density.md)。以下检查必须全部为 `pass`：

`subject_relevance`, `style_coherence`, `no_clipped_ornaments`, `scale_variation`, `photo_illustration_harmony`, `no_generic_ai_decoration`, `no_unexplained_labels`, `editorial_rhythm`, `mobile_legibility`, `open_composition`, `information_density`, `background_family_coherence`, `expressive_typography`, `no_baked_art_text`.

`expressive_typography` 确认标题字有节制地出现在高影响位置，字重、断行、层级和组织性格匹配，不侵入正文阅读。`no_baked_art_text` 确认标题仍是 Ardot 可编辑文本节点，不是 AI 生成字图、扁平图片或仅轮廓存档。

```bash
python3 scripts/build_visual_review.py visual-review.json --article article.json
```

把 review 文件路径写入 `article.visual_review_file`。`compile_wechat.py --check` 会重新校验文章 ID、组织 ID、5 类节点证据、密度范围与全部视觉项；缺一项就不生成可交付结果。
