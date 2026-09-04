# 灵动公众号构图规范

这份规范解决一个具体失败模式：按内容区块直接套组件，导致每段都有背景、边框、圆角和固定内边距，最终像一列卡片而不是一篇会呼吸的文章。

## 硬门槛：先确认创作选项，再排版

任何文章在读取材料、生成资产或创建长文画板前，必须一次成组请用户/编辑确认 `production_preferences`：小组件数量 `0..4`、是否使用 SVG/交互、文章风格 route，以及是否生成背景底图；四项都不得默认代选。小组件数量决定从以下四类角色目录中选多少个 `selected_roles`：

1. `floating-spot`：进入或离开开放文本区的小插图。
2. `section-transition`：把视线带入下一章节的横向流动插图。
3. `inline-explainer`：解释一个具体对象、动作或流程的小图。
4. `closing-motif`：在 CTA 附近形成落点的收尾小图。

数量为零是正常选择；数量大于零时，每个已选角色使用一枚不同的当前文章专属生成资产。先运行：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_kit.py" article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/visual-kit-plan.json
```

按提示只为 `selected_roles` 逐张生图，运行 `python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" "$ORG_WECHAT_RUNTIME_ROOT/scripts/inspect_asset.py" FILE --role ROLE`，保存并注册。随后在 Ardot 创建同样数量的原生 Ornament 组件，把 file/node/name 证据写入 `article.visual_kit.assets`。数量为零时两个集合都为空。只有计划中的 `ready_for_layout` 为 `true`，才允许创建文章画板。

Codex Desktop 默认先加载同一发布的顶层 sibling `$SKILLS_ROOT/chatgpt-web-image-route/SKILL.md` 和 `codex-with-chatgpt`，只用内置 Browser 让 ChatGPT 生成并下载 provider-original。每个 slot 可在请求前直接选择真透明 native-alpha，或选择计划内 controlled-key 纯色底以便本地安全分离；受控纯色不需伪造一次 native-alpha 失败才能成为首试。原图不进 Ardot。native-alpha 经 `prepare_micro_cutout.py --require-native-alpha` 验真、规范化和紧裁切；controlled-key 经 `--key-color` 分离。不论 raw 路线，只有 `assets/derived/` 中的主体专用 RGBA8 成品和完整派生报告通过 robust Alpha、紧裁切、open-edge、matte/halo/debris 及三底像素验收后，才能检查、注册和组件化。本地 ImageGen、C2C doctor、页面预览、截图或仅切换为 RGBA mode 都不证明终态透明资产成立。

当 `micro_component_count > 0` 而没有图像生成能力时，停在这一步。不要用色块、边框或卡片代替缺失的小插图。数量为零时可继续使用纯 Ardot 原生构图；若 `generate_backgrounds: true` 但缺生图能力，仍必须停止。

## 小插图验收

接受：

- 从正文里的具体名词、动作、结构或过程提炼视觉；
- 透明背景，或能自然融入页面的开放/柔边构图；
- 在 390 px 手机画面中缩小后仍能辨认；
- 与组织路线、色彩和图像语言一致；
- 无文字，方便文案继续在 Ardot 中编辑。

“有 Alpha”不等于“已抠图”。通行资产必须是主体专用 8-bit RGBA：留白在 Ardot 中制造，PNG 只保留主体、自然阴影和开放笔触。原图的模型“透明”声明不可信；完成品必须绑定 raw/prompt/provider/处理器/配置/报告/输出 SHA。注册器会用 robust Alpha bbox 忽略微小飞点，拒绝超大透明画布、全画布 low-Alpha 残留、主体截边、脱离碎片、彩色/中性 halo、矩形/圆角/纹理化 matte，并持久化 cutout 证据。

拒绝：

- 矩形海报、完整场景大图、卡片背景或 UI 面板；
- 泛化几何装饰、随机渐变、漂浮光球、无内容关系的“氛围图”；
- 假透明棋盘格，或文件实际没有 Alpha 却声称透明；
- 烘焙中文、日期、数字、Logo、二维码和水印；
- 需要再套一个框才能使用的图。
- 小主体放在巨大透明画布中，或抠图边缘留有白底、黑底、色板与 halo。
- 将 ChatGPT 页面截图、预览 Canvas、剪贴板或远程 URL 当作原始下载；
- 对背景不均、主体碰边、复杂透明材质或真实照片强制自动抠图。

检查透明图时必须读取文件 Alpha 信息；不要只看预览中的棋盘格。

## 先把小图做成组件

在长文画板之前，为审核通过的资产建立原生 Ardot 组件：

```text
WeChat/Ornament/FloatingSpot/<Mode>
WeChat/Ornament/SectionTransition/<Mode>
WeChat/Ornament/InlineExplainer/<Mode>
WeChat/Ornament/ClosingMotif/<Mode>
```

组件要保留开放边缘和可调尺寸，不加默认底色、描边、阴影或圆角容器。Ardot node-properties 必须声明 `complete_descendant_census: true`，且 `visible_descendant_count` 与 `nodes` 数量完全一致。每个 image/illustration node 除记录已验收 cutout 的 `asset_id` 和 `asset_sha256` 外，还必须在 visual-review bundle 内保存 `rendered_asset_file` 及其 `rendered_asset_sha256`，实际像素哈希与已批准 cutout 不同即阻断。任何可见 closed-shape 单独或并集覆盖 raster layer 80% 以上，视为禁止的图片底板。文章里插入组件实例，而不是重复粘贴图片。

## 微组件不能变成横幅卡片

已选微型视觉进入正文后仍要保持“小”与“开放”，不能因为加了文案就被做成一张横向大图或带框海报。设已选数量为 `N`：

- 单个图片/插画层宽度不得超过 390 px 画板的 72%；整个组件实例不得超过 82%。Hero、真实证据照片和 Gallery 不属于这个上限。
- 布局证据至少覆盖 `min(3, N)` 个截图区段、不同水平偏移与构图关系。`N >= 2` 时还必须同时出现左偏/右偏和可见尺寸变化；`N = 0` 时微组件布局证据为空/`not-applicable`。
- 优先使用文字边缘切入、段间穿插、连续路径、章节桥接、CTA 落点，不把每个组件单独居中放进一个横向条带。
- 每个实际实例都要进入 Ardot instance inventory。相同角色可以复用，但不得只拿好看的样本验收而漏掉其他全宽或带框实例。

微组件含字时，默认没有文字容器。禁止边框、填充矩形、圆角 chip、badge、标签底板或任何包围文字的闭合 shape node。主短句使用 Ardot 原生可编辑文本，至少 22 px 且不低于所在截图正文的 1.35 倍；必须包含 `scale-contrast`，再配合 mixed weight、颜色对比、主动断行、基线偏移或矢量点缀中的至少一种。字形描边/偏移只能贴合字形，不能变成围住整段文字的框。

## 开放式构图优先

每个语义区块先按“无外框”设计，再判断是否真的需要容器：

| 内容职责 | 默认构图 | 禁止的默认做法 |
|---|---|---|
| Lead / 正文 | 开放文本、错位留白、边缘小插图 | 给每段加浅色圆角底 |
| 章节 | 浮动序号、插图转场、文字尺度变化 | 完整章节卡片 |
| 观点 | 大字停顿、偏置引号、单条色轨 | 引用框套框 |
| 角色/并列项 | 错落标签、连续版面、局部对齐 | 三张等宽卡片 |
| 步骤/时间线 | 一条连续路径或节奏线 | 每步一个独立方块 |
| 案例 | 分层过程、跨栏标题、图文穿插 | 外层大卡片再套三行小框 |
| CTA | 全宽收尾、小插图落点、单一动作 | 按钮海或报名卡片 |

只有内容确实需要独立比较、点击或明确边界时才使用卡片。`generate_backgrounds: false` 不等于无视觉底层；可用同一风格 route 的 Ardot 原生 surface、渐变和可编辑矢量层建立连续画布，仍需避免黑/白大色块跳变并保证文字对比。

## 量化检查

视觉交付前同时检查截图和 Ardot 层级：

- 闭合方框区块不超过正文区块的 20%。
- 不允许两个闭合方框连续出现。
- 至少出现三次非对称、越界或边缘切入的视觉时刻。
- `selected_roles` 数量与 `micro_component_count` 一致，每个已选角色由不同的文章专属 derivative 承担，并有原生 Ardot component node；数量为零时不伪造组件或布局证据。
- 所有实际微组件实例均由哈希绑定的 Ardot 节点属性快照覆盖；校验器从 instance/image bounds、文字 font size 与闭合 shape 节点计算 72%/82% 上限、左右错落、字号层级与无框结果，不接受手填比例或 `pass` 自证。
- 不能让每个语义区块都拥有自己的背景、边框或圆角容器。
- 长文中要交替出现开放文本、图片/插图、连续路径、全宽转场和安静留白。
- 用紧凑的字距、行距和段距提高信息密度，不通过增加边框或卡片填空；默认正文 15–17 px、行高 1.45–1.62、中文字距 -0.2–0 px、段距 8–14 px、章内主间隔 24–40 px。
- 普通正文区的内容纵向占用率应为 68%–90%，最大无意空洞不超过区块高度 20%；Hero、全宽转场和结尾可以有意留白，但必须在分镜中声明。

分段截图复核后，把 Hero、章节、证据、复杂区块与 CTA 五个不同 Ardot 节点写入独立 `visual-review.json`。文章 JSON 不允许通过自填数字或 `visual_reviewed: true` 绕过真实截图验收。

若截图第一眼看到的是“框”，而不是标题、插图、节奏或内容关系，视为未通过。若第一眼感到文字彼此漂散、段落之间缺乏关联，或需要连续空滑才能遇到下一条信息，也视为未通过。
