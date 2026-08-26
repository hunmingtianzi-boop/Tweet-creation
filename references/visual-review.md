# Ardot 截图验收

文章 JSON 不能通过一个 `visual_reviewed: true` 自我证明质量。交付前必须从实际 Ardot 文章根中截取至少五个不同节点：

- `hero`；
- `chapter`；
- `evidence`（照片、事实、案例或数据）；
- `complex-section`（步骤、角色、流程或复杂图文）；
- `cta`。

独立 review JSON 需要 Ardot 文件、页面、文章根节点，每张截图的节点 ID 和本地文件/可查 URL。还要为这五个节点记录 `density.mode` 与密度样本，字段见 [information-density.md](information-density.md)。以下检查必须全部为 `pass`：

`subject_relevance`, `style_coherence`, `no_clipped_ornaments`, `scale_variation`, `photo_illustration_harmony`, `no_generic_ai_decoration`, `no_unexplained_labels`, `editorial_rhythm`, `mobile_legibility`, `open_composition`, `information_density`, `background_family_coherence`.

```bash
python3 scripts/build_visual_review.py visual-review.json --article article.json
```

把 review 文件路径写入 `article.visual_review_file`。`compile_wechat.py --check` 会重新校验文章 ID、组织 ID、5 类节点证据、密度范围与全部视觉项；缺一项就不生成可交付结果。
