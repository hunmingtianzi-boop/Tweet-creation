# Ardot 原生表现型字体

“艺术字”在本工作流中指少量、有语义作用的表现型标题字，不是把长段正文做成花字，也不是让生图模型生成中文字图。Ardot 始终保留真实文本节点、文本样式和可回退的标准字体。

## 使用范围

每篇建议 2–4 处，且不得超过组织校准中的 `maximum_moments_per_article`。只用于：

- `hero-title`：封面主标题；
- `chapter-title`：章节开场；
- `statement`：短句观点；
- `key-phrase`：正文中的关键短语；
- `cta-title`：收尾行动句。

表现型路线至少覆盖两种语义角色和两种处理手法。正文、长引用、日期、名单、数据与关键投递信息保持标准可读字体。

## 可用手法

- `mixed-weight`：同一短句的粗细对比；
- `stacked-title`：有意识的多行堆叠和尺度反差；
- `baseline-shift`：少量字的基线偏移；
- `stroke-offset`：由原生文本派生的偏移描边；
- `outline-shadow`：可回到原始文本的轮廓/影子层；
- `hand-drawn-accent`：手绘线、圈注或底线作为独立矢量点缀；
- `compressed-display`：授权或系统字体的紧凑展示款；
- `vertical-accent`：仅在短标签中使用的竖排强调。

不得使用未授权字体；不得将关键文字只保留为轮廓、位图或图像切片；不得用 AI 生成中文书法、标题字或含字底图。

## 组织校准

在 `organization.visual.calibration.typography` 中记录：

```json
{
  "strategy": "expressive-native",
  "editable_text_required": true,
  "font_policy": "licensed-or-system-only",
  "body_copy_remains_standard": true,
  "approved_treatments": ["stacked-title", "mixed-weight", "stroke-offset"],
  "maximum_moments_per_article": 4
}
```

校准条至少对比 Hero 与章节标题，同时检查组织识别度、390 px 断行、字重层级、字体授权和标准回退。新组织必须从本轮材料推导字体性格，不得查看旧推文的标题字寻找参考。

## 文章证据

`article.typography.moments` 的每一项必须：

- 引用正文中的 `source_text`，不超过 40 个字符；
- 绑定已批准的 storyboard chapter、语义角色和处理手法；
- 声明 `editable_text: true` 与 `font_source: licensed-or-system`；
- 提供标准 `fallback_text_style`；
- 记录当前组织 Ardot 文件中的 `file_url`、唯一文本 `node_id`、文本 `style_id` 和精确 `name`。

`asset_id`、`src`、`image` 或 `raster_text` 等字图字段会直接阻断装配。

## 微信传输

Ardot 原生文本是唯一设计源。微信适配时优先使用安全内联文本样式，字体不可用时回退到 `fallback_text_style`。若平台无法表达某个装饰效果，可在批准后从 Ardot 原生文本派生局部图片，但必须保留可编辑源节点和可读的文本回退；派生图不能取代设计源，也不得由生图模型生成文字。
