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
- `Calibration / <organization> / <route>`：只由本轮组织材料生成的五项校准条。
- `Article / <date> / <slug>`：当期文章画板；一篇文章一个根 Frame。

组件命名使用 `WeChat/<Block>/<Variant>/<Mode>`，例如：

- `WeChat/Hero/ImageStage/<Mode>`
- `WeChat/Section/IndexRail/<Mode>`
- `WeChat/Statement/EditorialPullout/<Mode>`
- `WeChat/Steps/BuildProtocol/<Mode>`

`components.json` 记录内容职责，`ardot.json` 把“区块 + 变体”映射到真实 Ardot 组件名。

## 每次生成文章

1. 校验组织包与文章 JSON。若组织/route 未做 Ardot 小样校准，先运行 `build_visual_directions.py` 并停在小样审核。
2. 完成 4–10 章叙事分镜，运行 `build_storyboard.py`。
3. 再生成文章专属微型视觉套件计划：

   ```bash
   python3 scripts/build_visual_kit.py article.json \
     --org organizations/<organization-id> \
     --output output/<organization-id>/<slug>/visual-kit-plan.json
   ```

4. 逐张生成、检查并注册四类视觉。四个角色必须使用四枚不同生成图；每张绑定正文原句、具体主体/动作、分镜章节与构图职责，并通过 `inspect_asset.py` 的 Alpha/尺寸/宽高比检查。
5. 先在 Ardot 中创建四个原生 Ornament 组件，把 file URL、component node ID 和 exact name 写回 `article.visual_kit.assets`。
6. 确认 `ready_for_layout: true` 后，生成装配清单：

   ```bash
   python3 scripts/build_ardot_manifest.py article.json \
     --org organizations/<organization-id> \
     --output output/<organization-id>/<slug>/ardot-manifest.json
   ```

7. 读取清单中的设计文件、变量模式、组件名称、资产路径、开放式构图模式和区块顺序。
8. 在 Ardot 中更新该组织的变量模式；不要复制另一组织的硬编码色值。
9. 创建 390 px 文章根 Frame。所有内容默认无外框；插图从文字边缘切入、穿过转场或陪伴连续路径。
10. 真实照片、官方 Logo 和二维码使用登记资产；微型插画使用组件实例，不作为矩形卡片背景。
11. 每次创建顶层 Frame 前定位空白区域；每批编辑不超过 25 个操作。
12. 分段截图检查 Hero、章节、观点、步骤、案例和 CTA；超过 2000 px 的长文不要一次截图。
13. 修正溢出、断行、空洞、方框化和组织气质偏差。
14. 为 Hero、章节、证据、复杂区块和 CTA 建立 v2 截图验收 JSON，绑定同一 article root、本地 390 px PNG、SHA-256、像素尺寸、章节、导出时间与密度样本，运行 `build_visual_review.py`。五类节点、密度样本与十二项检查全部通过才投递。

## 新公众号迁移

新组织初始化后，`ardot.json` 默认为 `not-linked`。首次迁移需要：

1. 完成组织调研并确认视觉路线。
2. 在空白组织页面中建立变量模式，或为完全独立的品牌建立新 Ardot 文件。可以复用语义 component IDs，但不要打开其他组织的 example/article 页面来选择外观。
3. 为 Hero、章节、观点、步骤/流程、案例、CTA 至少各选择一个构图变体。
4. 把真实 Ardot 文件 URL、模式名、页面名和组件别名写入 `ardot.json`，将状态改为 `linked`。
5. 先生成 2–3 组五项小样和同家族底图做视觉校准；确认后再制作第一篇全文。

迁移不是强制所有组织共用同一组件外观。语义职责可以共用，但 Hero、章节节奏、信息密度、边角语言和图片策略可以新增组织专属变体。

## 效果优先的视觉门槛

- Hero 必须形成一个明确的视觉时刻，并为标题断行留下真实空间。
- 没有完成文章专属微型视觉套件时，不得开始排版。
- 长文中至少有一个图片主导段和一个全宽色块/字体转场。
- 闭合方框不超过正文区块的 20%，且不允许连续出现两个。
- 卡片只用于可独立比较的信息；步骤优先用旅程线、协议表或连续流程。
- 每篇至少有三次不对称、越界或边缘切入的视觉时刻；每个区块默认无背景、无描边、无圆角容器。
- 组织差异至少体现在构图、留白、字体尺度、边角和图片策略中的三项，而不只是换色。
- 所有正文按 390 px 检查；默认 `compact-editorial` 为 15–17 px、1.45–1.62 行高、-0.2–0 px 中文字距、8–14 px 段距和 24–40 px 章内主间隔。正文不能松散漂浮，也不能挤成文字墙。

若使用 AI 底图，视觉校准阶段先确定一个 master 与 1–3 个 companion 变体。全文只改变裁切、透明度和局部构图，不逐章随机生图；真实照片仍是事实和活动证据的主视觉。

详细验收见 [organic-layout.md](organic-layout.md)。

## 微信投递

视觉定稿且 `article.visual_review_file` 通过后，才运行 `compile_wechat.py` 生成内部投递文件。适配层需要把 Ardot 审核后的组件语义映射为微信允许的内联样式，并将正文图片上传到目标公众号。默认只创建草稿；正式发布仍需单独确认。
