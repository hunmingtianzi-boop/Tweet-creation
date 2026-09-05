# 跨公众号 organization pack 迁移

迁移目标是复用流程语义，不复制另一个公众号的外观。新公众号始终建立新目录、新 organization ID、新 Ardot variable mode 和新视觉校准。

这里的“迁移”是 **Codex Desktop 内跨组织、公众号、clone 或机器迁移**，不是已经支持把执行层换成另一个 LLM/harness。当前 release 只有 `codex-desktop` adapter 和一条锁定平台记录；schema 与语义能力映射只是未来移植规范。另一个宿主必须先开发并审核 adapter、登录路线、原生下载/Alpha 链、Ardot/微信 live probes、完整前向测试和发布锁，才能发布新的受支持版本；不能靠手写 census 或跑一次 probe 自行宣布兼容。

迁移开始时先读[克隆、安装与登录前置条件](host-prerequisites.md)，再运行[运行环境启动自检](runtime-preflight.md) 的 `migration` 阶段。Codex Desktop 必须加载同一 release 的三个仓库 Skill。先保存本篇 `generation` 选择：仅选透明组件时要求绑定精确 workspace 的 `codex-with-chatgpt` 与 ChatGPT Browser；仅选不透明生图时要求 ImageGen；零生图不要求这两条路线。验图和 Ardot/微信工具按当前阶段检查。后续 `bootstrap/authoring/delivery/full` 再按阶段连接并登录 Ardot Remote、验证精确 file/root；`delivery/full` 另行准备目标微信公众号。

`migration` binding 通过后只建立 `org-wechat-runtime-session-evidence-v1`：精确绑定 release、registry、adapter、route、nonce/digest 与当前 provider session，不生成任何中性 RGBA 校准图。默认报告完全不发 `run-migration-rgba-route-probe`；只有显式 `--include-legacy-rgba-probe` 才加入这条非阻断兼容诊断，而且它不授权资产注册。正式透明素材在自身下载与派生阶段单独验图。

启动时一次性询问（可先读本轮材料再共同确定，不要求用户凭空做设计决策）：本篇微组件数量 `0–4`、是否使用 SVG、风格路线/校准模式、是否生成 raster 背景底图。不得静默套默认值；将最终选择写入 `article.production_preferences`，后续 pack、组件、Ardot 与交互门禁全部按该选择条件化。

未选择 RGBA 时跳过 provider binding/finalizer，保留必要的本地与当前阶段检查。所有后续 target 必须携带同一 `generation` 字段，不能复用丢失选择的旧样例。

完成该起始自测后，再用 binding-only 检查无凭据链接与目标 provider/session，随后对新组织的 Ardot file/root 和目标公众号做本次 Codex 会话宿主工具探针。本地 profile 不能自证 live ready；另一机器、clone 或会话的登录态、工具清单、probe 报告和 `ok: true` JSON 都不能迁移为当前证据。当前只读取 `runtime/adapters/codex-desktop.json`，也不会带走旧 ChatGPT 对话、配对码、Cookie 或登录态。

若新组织尚无 Ardot file/root，先在当前 Codex Desktop 中用 `bootstrap` 阶段绑定 adapter 的 `ardot.create`，创建空白目标后再改用目标阶段（默认 `full`，明确只创作时为 `authoring`）。`bootstrap` census 只要求 `ardot.create`，不注入 Browser 或生图路线；`delivery` 选 API 时也不继承 ChatGPT/Browser download ingestion。`bootstrap` 不要求微信登录，只解决自举，不允许读取或复用旧推文设计。

## 可以迁移

- semantic component IDs 与文章 block 职责；
- 事实、来源、资产、Ardot 和投递适配的文件分层；
- 390 px、开放式构图、compact-editorial、截图证据与草稿投递门槛；
- Logo/二维码权限边界和发布确认规则。
- 仓库级末位使用归属 `感谢拓浙 AI 生态提供本篇内容生产工作流支持。`；它跟随工作流迁移，不是可换的组织品牌文案。
- 隐藏来源水印的算法版本、公开证据 schema、`local_verified → transport_verified` 状态机和排除资产类型；密钥与私有 registry 不随 pack 迁移。
- `wechat-svg-smil-self-v1` 的交互语义、探针协议、静态等价物合同、fallback 哈希和验收步骤。
- 启动时选择 SVG 后才使用 2–3 个 semantic interaction modules，否则使用零模块 `static-selected`；同时保留 module/transport instance 计数边界、两阶段 Ardot 证据合同与显式静态例外 schema。
- 用户明确选择时，可迁移一个已审核 style preset 的九项抽象 grammar token、六项 non-copy boundary 与 canonical SHA；它只作用于被选 route，不携带来源文章内容。

## 必须重建

- 组织定位、受众、voice、personality、content pillars；
- tokens、motifs、avoid rules、route 与 component variants；
- 本公众号的真实照片 registry；
- 本轮 source-zero 视觉输入与隔离声明；
- Ardot calibration page、variable mode 和 route benchmark；
- 若选择生成底图：generated background family 的 master/companions、唯一 surface mode、复制安全区和像素验收；选择原生表面时不迁移 raster family；
- 当前组织独立的水印密钥域、key epoch、私有 ID 映射，以及由本组织无水印母版重新生成的 marked derivatives；不得沿用另一公众号已经带水印的图。
- 从当前组织材料校准的表现型字体策略、所选表现型字体路线的 construction recipes（至少一个；简洁原生文字路线不强制） 和 Ardot 文本/矢量样式；
- 每篇文章按确认数量生成 `0–4` 枚主体专用、紧裁切 RGBA8 cutout；每个已选角色都保留 P0 抠图证据、asset SHA 与 Ardot component/image nodes，不迁移另一篇的透明 PNG 或底板。
- 每枚已选 cutout 的生成原图、prompt SHA、provider route、处理器/配置 SHA、派生报告和最终像素 SHA；这些是文章级证据，不从另一个 organization pack 复制。
- 每篇文章 visual review v3（按篇幅覆盖的 390 px 截图（五章及以上用五类，短文逐章）、密度样本、完整微组件 instance inventory 与哈希 node-property exports）。
- 当前文章实际存在且已选择的读者任务、source blocks、instance copy/key/hash，以及该组织外观下的 `closed/open/fallback` Ardot group components。
- 目标公众号的 sanitizer 回读与 iOS/Android 客户端能力档案；它属于投递环境，不属于 organization pack。
- 即使选择同一个 style preset，也要从当前组织重新派生 paper/ink/display/wash tokens、真实照片职责、字体 recipes、被选择的背景系统和 Ardot 原生组件。

## 禁止复制

- 旧推文截图、长图、PDF 预览或 Ardot 页面作为新组织视觉参考；
- 另一个组织的 generated assets、background family、component variant 外观或效果样稿；
- 旧文章的 `approved`、截图、密度数字或 component node ID；
- Logo、二维码、照片和品牌色的跨组织替换式复用。
- 另一公众号的探针结论、草稿 ID、capability profile、`media_id` / `thumb_media_id`、令牌或客户端截图证据。
- 旧 binding nonce/digest、伪造 download receipt，或把旧会话证据复制进新会话目录。
- 另一公众号的已加水印图片、raw watermark ID、私有 registry、嵌入/认证密钥或 CDN 检测结论。
- style preset 最初参考中的文字、照片、Logo、具体版式、组件几何、artwork、章节结构或专有视觉物件；后续组织不得为使用 preset 而重新打开最初参考。

## 迁移步骤

0. 仅选 RGBA 时运行 `--phase migration --binding-only`，建立当前 provider session binding；默认不发 `neutral-rgba-route-probe-v1` 动作，也不因 RGBA 检测阻断读材料、初始化 pack 或打开 Ardot。仅调试旧路线时显式加 `--include-legacy-rgba-probe`。首次正式透明素材再做自身质量检查。
1. 运行 `orgs.py init` 建立空 pack，不复制已有 pack。
2. 只登记本轮原始材料到 `sources.json`；默认填写 `provenance.visual_input_source_ids` 和四类 `excluded_visual_reference_kinds`。若用户明确选 preset，把 preset JSON 本身登记为 style source，并使用 `explicit-style-grammar` 的 abstract-only scope、review time 与 non-copy 契约。
3. 从组织证据推导 2–3 条路线，生成五项 calibration strip；preset 只写入被选 route，其他 route 保持 source-zero。先校准再全文。
4. 若启动选择生成底图，生成同一家族的 master 与 1–3 个 companion，保留当前组织的无水印母版；母版放在 Git 忽略的 `unwatermarked-masters/` 私有输入目录，换机时从组织私有资产库单独恢复。对符合 V1 的不透明生成图创建独立 marked derivative，使用仓库外随机 32-byte 密钥完成像素鉴权、独立 PSNR 和完整画面 390px/JPEG-Q75 模拟后才登记 final 文件。两类资产分别标记 `background_variant`。为整个 family 声明单一 light/dark surface mode、归一化复制安全区、正文颜色、最低 4.5 对比度与复制区方差上限。若选择不生成底图，则省略 family，只校准 Ardot 原生连续阅读面。
5. 对生成式路线运行 `orgs.py validate` 分析所有底图实际像素；明暗模式混杂、大块相反色、复制区不均匀、文字对比不足或 family 色调跨度过大时必须重做校准资产，不能进入文章 root。原生表面路线不要求 raster family，但仍由 Ardot 截图/节点证据校验表面统一与对比度。通过后才将批准的 Ardot file/page/root、density mode 和所选背景系统写回 organization pack，并把状态改为 `confirmed`。
6. 在同一校准条中批准 `typography` 策略、授权边界、所选路线的原生 construction recipes 与每篇上限（简洁原生文字无需添加表现型字效）；每个 recipe 至少两种非字体构造手法和两个可编辑图层，不复制另一公众号的字效。
7. 为当前文章批准与 `use_svg` 一致的 `interaction_plan`：选择 SVG 时按真实读者任务确定一个或多个 semantic modules（2–3 仅长文建议），记录真实 chapter 位置，不为凑配额分散；选择不用 SVG 时使用零 module 的 `static-selected`。每个动态 module 绑定本篇 source blocks，逐 transport instance 计算唯一 key/hash。不要复制另一篇文章的任务、文案或 Ardot nodes。
8. 为当前文章按 `micro_component_count` 生成 0–4 枚不同微组件，不在 PNG 中为排版留白。Codex Desktop 用 `chatgpt-web-image-route` 操作 ChatGPT，可按真实组件选择真透明 provider-original PNG 或计划给出的均匀 controlled-key 原图并真实下载；前者用 `--require-native-alpha`，后者可直接用 `--key-color` 安全分离。原始文件门槛可选，但成品门槛不变：逐张通过 RGBA8、robust Alpha bbox、紧裁切、无截边/彩色或中性 halo/碎片/底板门禁，并验证完整派生 lineage 后注册为 `article-micro`，再在 Ardot 建原生组件；image node 回写 derivative 的同一 asset ID/SHA，不加可见 backplate。数量为 0 时不得拿旧组件补位。其他 harness 的等价路线是未来 adapter 的验收要求，不是当前 release 的可选运行分支。
9. 仅选表现型文字路线时设置有语义的文字时刻；数量服务于文章，不设每篇 2–4 个硬配额。引用批准 recipe，回写唯一 Ardot 文本/点缀 node 与 style 证据。
10. 若选择 SVG，在当前文章 revision 中为每个 interaction module 建 `closed/open/fallback` 原生 group states，覆盖全部 instance IDs/hashes，并保存三态 390 px 截图与文件哈希；静态选择跳过这一项。
11. 完成文章后从同一 article root 导出按篇幅覆盖的 390 px 截图（五章及以上用五类，短文逐章），记录每个样本的正文对比度；导出所有 visual-kit instances 与逐实例 node properties。通过 visual review v3 后，冻结 handoff v5 与 `ardot-current-root-layer-export-v1`：chapter y 连续覆盖 artboard，current-root export 完整绑定 section/layer/source-node/font/render-style/body-assets，底图为精确 3x 无字层，cutout/photo/SVG 保持独立。编译前必须由当前 Ardot 宿主真实重读并导出另一份 live root。无 signer 的 Codex 当前会话使用 `current-session-draft`：带 `--session-draft` 绑定 `wechat-candidate.html` / `candidate-report.json`，在同一宿主轨迹中实际写入微信、重开并逐章 readback，但固定 `portable_audit_verified: false`。需要可携带审计时，由宿主集成真实 `host.receipt.attest` callable 和受保护公钥信任库，分别对 Ardot live read 和微信 readback 签发 Ed25519 receipt，使用终态 `wechat.html` / `compile-report.json` 链。缺 signer 只表示 `portable-signed-audit` 不可用，不再阻断本次 current-session 草稿。Article-JSON 预览不得投递；两档草稿都不得未经单独确认正式发表/群发。
12. 只有选择 SVG 时才为目标公众号单独运行 `wechat-svg-smil-self-v1` 探针：禁止 JavaScript、`details`、任何 transport `id` 与跨 ID timing；先验证保存回读，再登记带有效期的 iOS/Android 真机证据。只有该账号 profile 为 current/passed 才可保留动态候选，否则同一草稿使用静态回退。缺失 profile 不取消已选择的创作层 module，只改变投递 payload。静态选择无需该探针。另从保存草稿取得实际 `mmbiz.qpic.cn` 正文图与封面派生图，对 locally verified carriers 运行水印 detector；required 模式未达到 `transport_verified` 时不得发布。

任何一步若需要查看旧视觉来“找感觉”，应停止并回到本轮原始材料、组织物件、真实照片和校准条，而不是把旧风格解释为品牌事实。已经沉淀为 preset 的风格只读取仓库中的抽象 grammar 与 SHA，不回看原稿。
