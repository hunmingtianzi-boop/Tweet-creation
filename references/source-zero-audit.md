# Source-zero 泛化审计与改进清单

本审计只读取通用工作流文件，以及最新 source-zero 案例的 JSON、报告和文件头信息；没有打开、查看或对照任何旧推文截图、长图、PDF 预览或 Ardot 画面，也没有把案例外观作为视觉参考。

## 案例暴露的可验证缺口

最新 source-zero 案例已经在说明文字中声明“不继承既有推文”，也确实登记了四类微组件、master/companion 底图、`compact-editorial` 密度和分段截图。但旧版脚本仍会放行以下状态：

- `provenance.notes` 只有自然语言声明，没有机器可读的 source-zero 策略、允许输入清单、禁用输入类别和隔离复核时间；
- background family 只有 ID 与一句策略，master/companion 资产没有 family ID、variant 和 copy-safe zone 绑定；
- 资产登记没有区分真实照片的“纪录证据”职责与 AI 底图的“氛围连续性”职责；
- 四个角色虽然实际用了四张图，质量门槛却只要求三张不同资产；
- 微组件文件没有 Alpha 像素报告，无法区分真实透明、全不透明 RGBA 和烘焙棋盘格；
- `article.visual_kit.status: approved` 没有对应的 Ardot 原生组件 node/name 证据；
- 截图验收只有路径与 node ID，没有文件哈希、390 px 实际尺寸、导出时间和 article root 绑定；
- 密度数字没有与截图哈希绑定，也没有 `major_gap_px`，因此 JSON 可以自填数字通过；
- README、校准说明和测试仍把历史文章/组织包当作效果基准或绿色夹具，会让下一次迁移在开始前就接触旧视觉。
- 标题字只有字号/字重的泛化建议，没有表现型字体的语义配额、授权边界、Ardot 可编辑 node/style 证据和禁止烘焙字图门槛。

## 已实现的改进

- [x] 默认 source-zero：新组织包记录 `visual_reference_policy`、本轮视觉输入 source IDs、四类禁用旧视觉输入与隔离复核时间。
- [x] 入口隔离：不自动读取内置组织包、examples、旧 Ardot、截图或历史文章设计；历史文字若获准只能作为 voice/fact 来源，不能进入视觉校准。
- [x] 照片/AI 职责：纪录照片使用 `documentary-evidence` 与 `source_id`；AI 底图使用 `illustrative-atmosphere`，不能进入 gallery 证据位。
- [x] 连续底图：批准校准必须登记一个 generated-family、一个 master、1–3 个 companion、copy-safe zone，并在资产层绑定 family/variant。
- [x] 四类微组件：四个角色必须由四枚当前文章专属资产分别承担，并绑定正文原句、章节、主体、动作、构图职责和 Ardot 原生组件。
- [x] Alpha 验收：`inspect_asset.py` 解码 PNG Alpha，检查真实透明像素、可见像素、尺寸、角色宽高比与 SHA-256。
- [x] compact-editorial：除字号、行高、字距、段距外，新增 24–40 px `major_gap_px` 门槛，并继续约束内容占用率和最大无意空洞。
- [x] Ardot 证据：visual review v2 要求本地 390 px node export、文件哈希、真实像素尺寸、导出时间、article root 绑定和 density-to-screenshot 哈希绑定。
- [x] 测试隔离：测试完全使用运行时生成的组织包、文章、RGBA 微组件和 390 px 截图，不读取任何历史推文设计。
- [x] 跨公众号迁移：新增独立迁移说明，明确哪些语义可以迁移、哪些视觉必须重建以及组织包通过门槛。
- [x] 表现型字体：组织校准先批准策略与原生处理；单篇限定 2–4 个语义时刻，必须绑定正文、授权/系统字体、标准回退与唯一 Ardot 文本 node/style；禁止 AI 字图和扁平标题。

## 仍需人工判断的部分

像素脚本能证明 Alpha、尺寸和证据文件未被替换，结构校验能证明字体计划有 Ardot node/style 证据，但它们不能判断主体是否真的贴合文章、字效是否真的有表现力、照片裁切是否尊重人物、版面是否灵动。这些仍必须在真实 Ardot 390 px node screenshots 上完成十四项视觉检查；脚本负责让“有证据”不可被布尔值代替。
