# Ardot 原生公众号工作流

Ardot 是视觉设计与可编辑组件的唯一源文件。文章 JSON 保存可迁移内容，组织包保存品牌与事实；微信 HTML 只在最终投递时生成，不参与视觉定稿。

## 固定分层

```text
organization pack  → 品牌、语气、路线、资产、Ardot 映射
article JSON       → 单篇内容、来源、区块顺序
visual kit         → 文章专属小组件、小插图与开放式构图锚点
Ardot              → 变量、组件、390 px 长文画板、视觉审核
WeChat adapter     → 图片上传、内联样式、草稿创建
```

任何时候都不要把一张长图当作可编辑源，也不要先设计 HTML 再反推 Ardot。

## 设计文件结构

- `00 Foundations`：语义变量、字体、间距、圆角与模式说明。
- `01 Components`：跨文章复用的原生组件与组织构图变体。
- `Example / <organization>`：经过视觉审核的 390 px 真实文章样稿。
- `Article / <date> / <slug>`：当期文章画板；一篇文章一个根 Frame。

组件命名使用 `WeChat/<Block>/<Variant>/<Mode>`，例如：

- `WeChat/Hero/ImageStage/Ocean`
- `WeChat/Section/IndexRail/<Mode>`
- `WeChat/Statement/EditorialPullout/Ocean`
- `WeChat/Steps/BuildProtocol/<Mode>`

`components.json` 记录内容职责，`ardot.json` 把“区块 + 变体”映射到真实 Ardot 组件名。

## 每次生成文章

1. 校验组织包与文章 JSON。
2. 先生成文章专属微型视觉套件计划：

   ```bash
   python3 scripts/build_visual_kit.py article.json \
     --org organizations/<organization-id> \
     --output output/<organization-id>/<slug>/visual-kit-plan.json
   ```

3. 逐张生成、检查并注册 `floating-spot`、`section-transition`、`inline-explainer`、`closing-motif`；至少三枚不同生成图。把 ID 写入 `article.visual_kit.assets`，并先在 Ardot 做成开放边缘的原生小组件。
4. 确认 `ready_for_layout: true` 后，生成装配清单：

   ```bash
   python3 scripts/build_ardot_manifest.py article.json \
     --org organizations/<organization-id> \
     --output output/<organization-id>/<slug>/ardot-manifest.json
   ```

5. 读取清单中的设计文件、变量模式、组件名称、资产路径、开放式构图模式和区块顺序。
6. 在 Ardot 中更新该组织的变量模式；不要复制另一组织的硬编码色值。
7. 先补齐缺失组件，再创建 390 px 文章根 Frame。所有内容默认无外框；插图从文字边缘切入、穿过转场或陪伴连续路径。
8. 真实照片、官方 Logo 和二维码使用登记资产；微型插画使用组件实例，不作为矩形卡片背景。
9. 每次创建顶层 Frame 前定位空白区域；每批编辑不超过 25 个操作。
10. 分段截图检查 Hero、章节、观点、步骤、案例和 CTA；超过 2000 px 的长文不要一次截图。
11. 修正溢出、断行、空洞、方框占比和组织气质偏差，并把实测结果写入 `article.layout_review`。
12. 只有 `visual_reviewed: true` 且量化门槛全部通过，才进入投递。

## 新公众号迁移

新组织初始化后，`ardot.json` 默认为 `not-linked`。首次迁移需要：

1. 完成组织调研并确认视觉路线。
2. 在现有组件系统中新建一个变量模式，或为完全独立的品牌建立新 Ardot 文件。
3. 为 Hero、章节、观点、步骤/流程、案例、CTA 至少各选择一个构图变体。
4. 把真实 Ardot 文件 URL、模式名、页面名和组件别名写入 `ardot.json`，将状态改为 `linked`。
5. 生成一篇真实样稿做视觉校准；确认后再批量生产。

迁移不是强制所有组织共用同一组件外观。语义职责可以共用，但 Hero、章节节奏、信息密度、边角语言和图片策略可以新增组织专属变体。

## 效果优先的视觉门槛

- Hero 必须形成一个明确的视觉时刻，并为标题断行留下真实空间。
- 没有完成文章专属微型视觉套件时，不得开始排版。
- 长文中至少有一个图片主导段和一个全宽色块/字体转场。
- 闭合方框不超过正文区块的 20%，且不允许连续出现两个。
- 卡片只用于可独立比较的信息；步骤优先用旅程线、协议表或连续流程。
- 每篇至少有三次不对称、越界或边缘切入的视觉时刻；每个区块默认无背景、无描边、无圆角容器。
- 组织差异至少体现在构图、留白、字体尺度、边角和图片策略中的三项，而不只是换色。
- 所有正文按 390 px 检查；正文通常为 15–17 px，行距留足手机阅读。

详细验收见 [organic-layout.md](organic-layout.md)。

## 微信投递

视觉定稿且 `article.layout_review` 通过后，才运行 `compile_wechat.py` 生成内部投递文件。适配层需要把 Ardot 审核后的组件语义映射为微信允许的内联样式，并将正文图片上传到目标公众号。默认只创建草稿；正式发布仍需单独确认。
