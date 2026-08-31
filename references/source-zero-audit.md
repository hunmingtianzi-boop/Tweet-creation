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
- 最新正向测试进一步暴露：仅校验 family ID 会让黑/白大色块、明暗跳变与正文吞字通过；仅校验 treatment/font/node 则会让“只换字体”的死板标题冒充艺术字。两者都会把本应在校准阶段解决的问题拖到全文后的人工微调。
- 生成底图只有普通 SHA 时，能证明仓库内文件未变，但不能在微信转码后提供来源线索；若临近编译或发布才加水印，又会破坏 Ardot revision 与资产哈希的同一性。

## 最新 source-zero 传输回归（只作结构证据）

本轮只检查交付清单、HTML DOM、资产编码与哈希，没有打开旧推文设计，也没有把案例画面作为视觉参考。回归证据显示，旧传输层会把同一篇文章拆成三套视觉来源：首尾使用整段章节截图，中间按照内容重新编写普通文档流与纯色背景，互动 SVG 再依据文案手工重绘。即使文字大致一致，这也不是 Ardot 的原样传输。

- 章节截图把底图、装饰、照片和文字焊成一张图，失去原生文字、独立照片和 cutout 图层；
- 中间 HTML 自行决定 `padding`、`margin`、宽度、色面和字体回退，无法证明它对应 Ardot 当前 root 的章节几何与层级；
- SVG 只复述组件内容，没有绑定 Ardot state export、结构哈希和原始节点状态；
- 源 cutout 即使具有 Alpha，交付副本仍可能被转成索引图或被章节截图压平，正文中也没有 `article-micro` 的独立资产标记；
- 交付文件缺少逐章 section node、文字 node、资产 ID/SHA 与保存后草稿截图的回读闭环。
- 早期互动 MVP 曾生成名为 `wechat.html` 的实验片段与剪贴板导入助手，形成绕过当前 Ardot root 的旁路。

对应改进清单已经落实为硬门槛：

- [x] `article.json` 只保留语义职责；旧模板编译器只能输出 `authoring-preview.html`，并固定标记 `delivery_eligible: false`。
- [x] 最终稿只接受 `ardot-current-root-layer-export-v1`，其 revision 同时绑定章节顺序、几何、文字样式、无字底图、独立照片/cutout、交互状态与降级决策。
- [x] 每章使用唯一 section node 和 article-root 390 px 坐标，逐章 y/bottom 连续无 gap/overlap 并精确覆盖 artboard；背景必须是完整 `1170 × (chapter_height × 3)` 无字层并绑定 background-only node export；可见文字必须保持 Ardot 原生可编辑节点。
- [x] 真实照片保持 `documentary-evidence` 独立图层；微组件重新执行 RGBA8、最大连通主体紧裁切、无白/黑/彩色 matte、无半透明 halo、无背板、完整可见后代清单与实际 rendered-layer asset SHA 门禁。
- [x] SVG 只能使用哈希绑定的 Ardot state export；`closed/open/fallback` 各自绑定不同的 node ID 与 tree SHA，否则明确使用语义等价静态降级，禁止凭内容另画一份。
- [x] 当前 root export 额外绑定完整 section/layer/source-node/style/body-asset census，`component_order` 与全部可见运输节点 exact-once 覆盖；最终编译前必须通过 Ardot 宿主生成一份独立 fresh root reread，并由 harness 用宿主私有 Ed25519 私钥从真实工具响应签发最长十分钟的 receipt；仓库只拿公钥，冻结文件、复制件、改时间戳 JSON 都不能自充 live 证据。
- [x] 编译后的 HTML 逐章重算 section/layer render signature，精确校验 tag、role、source SHA、字体/渲染 style、geometry、z-index、严格 DOM 子树、重复属性和实际图片字节；`compile-report.json` 绑定宿主签名的 intended HTML path 以及最终 HTML device/inode/SHA/bytes/handoff/revision；微信保存并重新打开后，harness 再签发 `wechat-host-saved-draft-receipt-v1`，绑定账号/草稿、compile report、HTML、live receipt、真实 `mmbiz.qpic.cn` 下载文件、互动签名、等高 390 px 截图与整份 readback 字节。
- [x] 互动 A/B 实验固定为 `delivery_eligible: false`，只输出 candidate/fallback fragment；删除剪贴板导入器和公众号直投入口，采用结果必须回到 handoff v5。

## 已实现的改进

- [x] 默认 source-zero：新组织包记录 `visual_reference_policy`、本轮视觉输入 source IDs、四类禁用旧视觉输入与隔离复核时间。
- [x] 入口隔离：不自动读取内置组织包、examples、旧 Ardot、截图或历史文章设计；历史文字若获准只能作为 voice/fact 来源，不能进入视觉校准。
- [x] 照片/AI 职责：纪录照片使用 `documentary-evidence` 与 `source_id`；AI 底图使用 `illustrative-atmosphere`，不能进入 gallery 证据位。
- [x] 连续底图：批准校准必须登记一个 generated-family、一个 master、1–3 个 companion、copy-safe zone，并在资产层绑定 family/variant。
- [x] 四类微组件：四个角色必须由四枚当前文章专属资产分别承担，并绑定正文原句、章节、主体、动作、构图职责和 Ardot 原生组件。
- [x] Alpha/抠图验收：解码 RGBA8，使用最大连通主体忽略飞点并检查紧裁切、截边、白/黑/彩色 matte、半透明白黑 halo、尺寸、角色宽高比与 SHA-256；登记后每次 ready 门禁都从当前像素重算。
- [x] compact-editorial：除字号、行高、字距、段距外，新增 24–40 px `major_gap_px` 门槛，并继续约束内容占用率和最大无意空洞。
- [x] Ardot 证据：visual review v3 要求本地 390 px node export、文件哈希、真实像素尺寸、导出时间、article root 绑定和 density-to-screenshot 哈希绑定；并用完整 instance inventory 与哈希化 node-property exports 计算微组件宽度、错落、文字包框和字号层级。
- [x] 测试隔离：测试完全使用运行时生成的组织包、文章、RGBA 微组件和 390 px 截图，不读取任何历史推文设计。
- [x] 跨公众号迁移：新增独立迁移说明，明确哪些语义可以迁移、哪些视觉必须重建以及组织包通过门槛。
- [x] 表现型字体：组织校准先批准策略与原生处理；单篇限定 2–4 个语义时刻，必须绑定正文、授权/系统字体、标准回退与唯一 Ardot 文本 node/style；禁止 AI 字图和扁平标题。
- [x] 底图像素门禁：family 统一声明 light/dark surface mode、结构化复制区、正文颜色、最低 4.5 对比度与复制区方差；`orgs.py validate` 解码最终 PNG，检查明暗面、大块相反色、复制区均匀度、对比度与 family 色差。
- [x] 艺术字构造门禁：`expressive-native` 至少批准两个 recipe；每个 recipe/文章时刻至少两种非字体技术和两个可编辑文字/点缀层，拒绝 font-swap-only，并在 Ardot 截图复核 `art_type_construction`。
- [x] 微组件构图门禁：拒绝只留透明边的矩形 alpha tile；所有实际实例逐一进入 inventory，图片/组件宽度分别不超过 72%/82%，四类角色跨至少三个截图区段并左右错落；含字实例禁止闭合文字框，主短句至少 22 px、1.35× 正文。
- [x] 截图可读性：五个密度样本都记录实测 `body_text_contrast_ratio >= 4.5`，同时新增 `background_surface_unity` 与 `reading_surface_contrast` 检查。
- [x] 隐藏来源水印：只对不透明的工作流生成底图/纯生成 raster 封面生成新 derivative；保留无水印母版，在登记及后续每个 ready 门禁中重新验证 HMAC、母版/成品/报告 SHA、独立 `PSNR >= 42 dB` 和完整画面 390px/JPEG-Q75 模拟，不信任报告自报字段，并将严格公开证据透传到 Ardot/compile/publisher。
- [x] 水印隐私与载体边界：密钥和 raw ID 映射始终在仓库外；真实照片、Logo、二维码、透明小组件、SVG 与 QA 证据不修改；发布前只有从实际微信 CDN/封面派生图回读检出才能标记 `transport_verified`。

## 仍需人工判断的部分

像素脚本能证明 Alpha、尺寸、底图色调/复制区和证据文件未被替换，结构校验能证明字体计划有 recipe、构造与 Ardot node/style 证据，但它们不能判断主体是否真的贴合文章、字效是否真的有表现力、照片裁切是否尊重人物、版面是否灵动。这些仍必须在真实 Ardot 390 px node screenshots 上完成全部视觉检查；脚本负责让“有证据”不可被布尔值代替。
