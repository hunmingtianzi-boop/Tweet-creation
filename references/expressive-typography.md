# Ardot 原生表现型字体

“艺术字”在本工作流中指少量、有语义作用的表现型标题字，不是把长段正文做成花字，也不是让生图模型生成中文字图。Ardot 始终保留真实文本节点、文本样式和可回退的标准字体。

## 使用范围

每篇建议 2–4 处，且不得超过组织校准中的 `maximum_moments_per_article`。只用于：

- `hero-title`：封面主标题；
- `chapter-title`：章节开场；
- `statement`：短句观点；
- `key-phrase`：正文中的关键短语；
- `cta-title`：收尾行动句。

表现型路线至少一个有语义的文字时刻；不同角色和手法是建议，不为满足数量配额加入字效。正文、长引用、日期、名单、数据与关键投递信息保持标准可读字体。

## 可用构造手法

批准的 treatment 可以继续使用 `mixed-weight`、`stacked-title`、`baseline-shift`、`stroke-offset`、`outline-shadow`、`hand-drawn-accent`、`compressed-display`、`vertical-accent`。但 treatment 只是路线名，真正验收的是下面这些可观察、非字体替换的 construction technique：

- `intentional-line-break`、`scale-contrast`、`baseline-offset`、`rotation`；
- `color-contrast`、`mixed-weight`、`outline-layer`、`offset-layer`；
- `vector-accent`、`vertical-flow`。

每个批准 recipe 至少包含两种 technique；每个文章时刻也必须实际实现该 recipe 的全部 technique，并保留至少两个可编辑文字/点缀图层。只换字体、字重或字号但没有组合结构，不算艺术字。

不得使用未授权字体；不得将关键文字只保留为轮廓、位图或图像切片；不得用 AI 生成中文书法、标题字或含字底图。

## 微组件短句不是标签框

微组件中的一行短句可以使用字号层级，但不因此自动计入每篇 2–4 个艺术字时刻。它仍必须是 Ardot 原生文本：主短句至少 22 px、至少为所在截图正文的 1.35 倍，并使用 `scale-contrast` 加另一种非框体手法。禁止为了“突出”给文字增加描边矩形、填充底板、圆角 chip、badge 或包围文字的闭合 shape。

`outline-layer`、`offset-layer` 与 `stroke-offset` 只描述沿字形轮廓构造的可编辑层，不允许解释成文字外面的矩形边框。最终验收从 schema-v3 Ardot node-property export 中读取 `font_size_px`、text bounds 与闭合 shape bounds，而不是相信手填的“已放大/无框”。

## 组织校准

在 `organization.visual.calibration.typography` 中记录：

```json
{
  "strategy": "expressive-native",
  "editable_text_required": true,
  "font_policy": "licensed-or-system-only",
  "body_copy_remains_standard": true,
  "approved_treatments": ["stacked-title", "mixed-weight", "stroke-offset"],
  "approved_recipes": [
    {
      "id": "hero-stack",
      "treatment": "stacked-title",
      "techniques": ["intentional-line-break", "scale-contrast", "vector-accent"],
      "minimum_editable_layers": 3,
      "fallback_text_style": "Display/Hero/Fallback"
    },
    {
      "id": "chapter-mix",
      "treatment": "mixed-weight",
      "techniques": ["mixed-weight", "color-contrast"],
      "minimum_editable_layers": 2,
      "fallback_text_style": "Display/Chapter/Fallback"
    }
  ],
  "maximum_moments_per_article": 4
}
```

校准条至少对比 Hero 与章节标题，并批准所选路线的 recipe（至少一个），同时检查组织识别度、390 px 断行、图层结构、字体授权和标准回退。新组织必须从本轮材料推导字体性格，不得查看旧推文的标题字寻找参考。

## 文章证据

`article.typography.moments` 的每一项必须：

- 引用正文中的 `source_text`，不超过 40 个字符；
- 绑定已批准的 storyboard chapter、语义角色、`recipe_id` 和对应处理手法；
- 声明 `editable_text: true` 与 `font_source: licensed-or-system`；
- 提供标准 `fallback_text_style`；
- 写入 `construction.techniques`、`native_text_node_ids`、`accent_node_ids`、`line_count`；使用 `scale-contrast` 时还要写 `scale_ratio >= 1.15`；
- 记录当前组织 Ardot 文件中的 `file_url`、唯一文本 `node_id`、文本 `style_id` 和精确 `name`，且该 node ID 必须出现在 `construction.native_text_node_ids`。

示例：

```json
{
  "role": "hero-title",
  "storyboard_chapter": "opening",
  "source_text": "让智能体真正开始工作",
  "recipe_id": "hero-stack",
  "treatment": "stacked-title",
  "editable_text": true,
  "font_source": "licensed-or-system",
  "fallback_text_style": "Display/Hero/Fallback",
  "construction": {
    "techniques": ["intentional-line-break", "scale-contrast", "vector-accent"],
    "native_text_node_ids": ["41:1", "41:2"],
    "accent_node_ids": ["41:3"],
    "line_count": 2,
    "scale_ratio": 1.35
  },
  "ardot_text_style": {
    "file_url": "https://ardot.example/current-org",
    "node_id": "41:1",
    "style_id": "40:1",
    "name": "Type/Display/HeroStack"
  }
}
```

`asset_id`、`src`、`image` 或 `raster_text` 等字图字段会直接阻断装配。

## 微信传输

Ardot 原生文本与独立矢量点缀是唯一设计源。微信适配时优先使用安全内联文本样式，字体不可用时回退到 `fallback_text_style`。若平台无法表达某个装饰效果，可在批准后从 Ardot 原生结构派生局部图片，但必须保留可编辑源节点和可读的文本回退；派生图不能取代设计源，也不得由生图模型生成文字。
