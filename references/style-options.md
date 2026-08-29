# 可选视觉语法

默认视觉策略仍是 `source-zero`：只从当前组织与当前材料完成校准，不查看旧推文、旧 Ardot、旧截图/PDF 或其他组织视觉包。

只有用户明确要求学习某个视觉风格，或明确选择仓库中的已审核 preset 时，才允许在一个候选 route 上使用 `explicit-style-grammar`。这不是全局换肤；未选中的 route 继续按 source-zero 生成。

## 两种使用方式

### 第一次从参考案例抽象

1. 将用户明确授权的参考登记到本组织 `sources.json`，kind 建议为 `visual-style-reference`。
2. 只提取抽象关系：色彩运动、饱和度、材质、光感、图层次序、边缘能量、文字安全区、照片职责和底图职责。
3. 禁止把参考中的文字、照片、Logo、具体版式、组件几何或 artwork 写入 grammar。
4. 若要沉淀为可复用 preset，先把审核后的 canonical grammar 写入 `style-presets/<preset-id>.json`，再将同一 grammar 放到被选择的 `visual.routes[].style_grammar`。带 `preset_id` 的 route 必须与仓库 canonical SHA 一致；只修改 token 后重新计算自有 SHA 仍会失败。
5. 仍要使用当前组织资料重做视觉校准条；参考风格不能替代组织校准。

### 后续复用仓库 preset

后续组织不得重新打开最初的参考文章。把 `style-presets/<preset-id>.json` 本身登记为本轮 style source，只复制其中的 `grammar` 到一个候选 route，并保留 canonical SHA-256。组织色、物件、字体、照片与 Ardot 组件都必须从当前组织重新派生。

当前可选项：

- `prismatic-paper-editorial` / 绚烂纸本：暖纸底、青蓝与粉色透明洗染、干刷矢量、轻纸纤维和连续阅读面。文件见 [../style-presets/prismatic-paper-editorial.json](../style-presets/prismatic-paper-editorial.json)。它不是默认风格。

## Organization pack 契约

选择 preset 时，`organization.provenance` 必须包含：

```json
{
  "visual_reference_policy": "explicit-style-grammar",
  "style_reference_source_ids": ["source.style-preset.prismatic-paper-editorial"],
  "style_reference_scope": "abstract-visual-grammar-only",
  "reference_reviewed_at": "2026-08-29T21:00:00+08:00",
  "style_reference_non_copy_constraints": [
    "text",
    "photographs",
    "logos",
    "specific-layout",
    "component-geometry",
    "artwork"
  ]
}
```

`style_reference_source_ids` 同时要出现在 `provenance.source_ids`，并能解析到 `sources.json`。每个 selected route 的 `style_grammar` 为：

```json
{
  "preset_id": "prismatic-paper-editorial",
  "label": "绚烂纸本",
  "tokens": {
    "color_motion": "...",
    "saturation": "...",
    "material": "...",
    "lighting": "...",
    "layering": "...",
    "edge_energy": "...",
    "copy_safe_zone": "...",
    "photo_responsibility": "...",
    "background_responsibility": "..."
  },
  "non_copy_constraints": [
    "text",
    "photographs",
    "logos",
    "specific-layout",
    "component-geometry",
    "artwork"
  ],
  "sha256": "<canonical SHA-256>"
}
```

SHA-256 只覆盖规范化后的 `tokens + non_copy_constraints`；`preset_id` 和 `label` 是展示元数据，不改变 grammar 身份。只要提供 `preset_id`，校验器就会读取 `style-presets/<preset-id>.json` 并要求 route SHA 等于仓库 canonical SHA；未知 preset 会失败。生成 visual directions、asset plan、visual kit 和 Ardot manifest 时会继续透传 policy、preset 与 SHA。篡改 token、重新签名篡改 token、塞入参考文案字段、URL、明确的复制/复刻指令或缺少非复制项都会失败。

## 绚烂纸本的校准门槛

- 全文只使用一个 light surface family；禁止黑封面、白正文或逐章随机换色。
- 暖纸阅读面占比至少 62%，正文对比度至少 4.5:1；洗染经过正文时必须淡出，不能用白色矩形补救。
- Ardot 图层顺序固定为纸面、冷洗染、暖洗染、笔触、颗粒、原生文本、真实照片、交互。
- 真实照片独占人物、活动、场地、项目和成果证据职责；AI 或矢量底图只负责氛围与连续性。
- 每个章节最多一处 4–8 个汉字的原生可编辑艺术字；笔刷/描边是独立矢量层，关键信息保留标准文本 fallback。
- 交互的 closed/open/fallback 三态使用同一家族 seed 与同一背景坐标，不因展开而换肤。
- 禁止复制参考案例的具体图形、照片、艺术字排布、导航/航海物件、卡片几何或章节顺序。

批准 preset 仍需完成当前组织的五类校准条、同一家族 master/companions 像素验收和 Ardot 截图证据。风格名或提示词不能自证通过。
