# 跨公众号 organization pack 迁移

迁移目标是复用流程语义，不复制另一个公众号的外观。新公众号始终建立新目录、新 organization ID、新 Ardot variable mode 和新视觉校准。

迁移开始时先运行[运行环境启动自检](runtime-preflight.md) 的 `migration` 阶段，不得先读组织材料或打开旧设计。目标 harness 必须加载当前项目根 Skill 和仓库内 publisher Skill 的相同 SHA，并把自己的工具映射到 `image.generate.opaque`、`image.generate.rgba`、`image.inspect`、`ardot.create/read/write/export`、`wechat.draft`、UI fallback 与 `secret.resolve`。Codex Desktop 的 RGBA 默认路由还需加载仓库内 `chatgpt-web-image-route`、已安装 `codex-with-chatgpt` 和完整内置 Browser route；它不是全局强制依赖。另一 harness 可改用能产生 Alpha 的原生/API provider，但必须在 adapter 声明真实稳定的 `generation_route_id`、`migration_probe_contract: neutral-rgba-route-probe-v1`，并保留同一 `subject-cutout-rgba8-v1` 处理、lineage 与像素门槛。

`migration` binding 通过后立即执行报告的 `run-migration-rgba-route-probe`：首轮精确 prompt 要求 provider-original 真透明 PNG，并以 `prepare_migration_probe.py --require-native-alpha` 禁止暗中去背景；binding nonce/digest 不进入图像 prompt，而由宿主侧 canonical request metadata SHA 与同一 provider request、生成完成和 original-download 事件关联。该锁定处理器要求绝对 binding-report 路径、选中 case 和 create-once ingestion，只允许 `migration-route-probe` / `migration.rgba-route-probe` / `floating-spot`；输出明确为 `migration_only=true`、`article_asset_authority=false`、`registerable=false`、`portable=false`、`carry_forward=false`。raw PNG 魔数/MIME/bytes/SHA/time、secure processor、RGBA8 像素门禁和 exact derivative 透明/浅/深三底验图也必须齐全。本地像素链不能自证 host route，host route 也不能代替像素验收。只有首轮处理器 create-once 写出可重算的原生 Alpha 失败证据，第二轮才可使用一次明确的 controlled-key fallback；current-session 与 portable 终结器都会重开 attempt 1 raw/ingestion/failure 并重算原因。登录、CAPTCHA、2FA、生成中断或下载修复不消耗第二次。探针只放本次 nonce 的 Git 忽略 runtime 目录，不得注册资产、进 Ardot、加水印、作为风格参考或充当首张正式资产证据。ChatGPT-web 路线遵守 C2C 单对话规则，不另开临时 chat；探针仅为无对象、无品牌、单一中灰的非语义校准轮廓，后续正式 prompt 必须排除该轮廓与灰度测试处理。

完成该起始自测后，再用 binding-only 检查无凭据链接与目标 provider/session，随后对新组织的 Ardot file/root 和目标公众号做本次会话宿主工具探针。本地 profile 不能自证 live ready；另一环境的登录态、工具清单、probe 报告和 `ok: true` JSON 都不能迁移为当前证据。每个新 harness 都要建立等价 adapter 路由；Codex 示例只读取 `runtime/adapters/codex-desktop.json`，不带走它的 ChatGPT 对话、配对码、Cookie 或登录态。

若新 harness/新组织尚无 Ardot file/root，先用 `bootstrap` 阶段绑定 adapter 中的 `ardot.create`，创建空白目标后再改用目标阶段（默认 `full`，明确只创作时为 `authoring`）。`bootstrap` census 只要求 `ardot.create`，不注入 Browser 或生图路线；`delivery` 选 API 时也不继承 ChatGPT/Browser download ingestion。`bootstrap` 不要求微信登录，只解决自举，不允许读取或复用旧推文设计。

## 可以迁移

- semantic component IDs 与文章 block 职责；
- 事实、来源、资产、Ardot 和投递适配的文件分层；
- 390 px、开放式构图、compact-editorial、截图证据与草稿投递门槛；
- Logo/二维码权限边界和发布确认规则。
- 仓库级末位使用归属 `感谢拓浙 AI 生态提供本篇内容生产工作流支持。`；它跟随工作流迁移，不是可换的组织品牌文案。
- 隐藏来源水印的算法版本、公开证据 schema、`local_verified → transport_verified` 状态机和排除资产类型；密钥与私有 registry 不随 pack 迁移。
- `wechat-svg-smil-self-v1` 的交互语义、探针协议、静态等价物合同、fallback 哈希和验收步骤。
- 创作层默认 2–3 个 semantic interaction modules、module/transport instance 计数边界、两阶段 Ardot 证据合同与显式静态例外 schema。
- 用户明确选择时，可迁移一个已审核 style preset 的九项抽象 grammar token、六项 non-copy boundary 与 canonical SHA；它只作用于被选 route，不携带来源文章内容。

## 必须重建

- 组织定位、受众、voice、personality、content pillars；
- tokens、motifs、avoid rules、route 与 component variants；
- 本公众号的真实照片 registry；
- 本轮 source-zero 视觉输入与隔离声明；
- Ardot calibration page、variable mode 和 route benchmark；
- generated background family 的 master/companions、唯一 surface mode、复制安全区和像素验收；
- 当前组织独立的水印密钥域、key epoch、私有 ID 映射，以及由本组织无水印母版重新生成的 marked derivatives；不得沿用另一公众号已经带水印的图。
- 从当前组织材料校准的表现型字体策略、至少两个 construction recipes 和 Ardot 文本/矢量样式；
- 每篇文章四枚主体专用、紧裁切 RGBA8 cutout，其 P0 抠图证据、asset SHA 与 Ardot component/image nodes；不迁移另一篇的透明 PNG 或底板。
- 每篇文章四枚 cutout 的生成原图、prompt SHA、provider route、处理器/配置 SHA、派生报告和最终像素 SHA；这些是文章级证据，不从另一个 organization pack 复制。
- 每篇文章 visual review v3（五类 390 px 截图、密度样本、完整微组件 instance inventory 与哈希 node-property exports）。
- 当前文章实际的 2–3 个读者任务、source blocks、instance copy/key/hash，以及该组织外观下的 `closed/open/fallback` Ardot group components。
- 目标公众号的 sanitizer 回读与 iOS/Android 客户端能力档案；它属于投递环境，不属于 organization pack。
- 即使选择同一个 style preset，也要从当前组织重新派生 paper/ink/display/wash tokens、真实照片职责、字体 recipes、背景 family 和 Ardot 原生组件。

## 禁止复制

- 旧推文截图、长图、PDF 预览或 Ardot 页面作为新组织视觉参考；
- 另一个组织的 generated assets、background family、component variant 外观或效果样稿；
- 旧文章的 `approved`、截图、密度数字或 component node ID；
- Logo、二维码、照片和品牌色的跨组织替换式复用。
- 另一公众号的探针结论、草稿 ID、capability profile、`media_id` / `thumb_media_id`、令牌或客户端截图证据。
- 旧迁移 RGBA probe 的 raw/derived/report、旧 binding nonce/digest、伪造 download receipt，或把中性 probe 复制进新 nonce 目录。
- 另一公众号的已加水印图片、raw watermark ID、私有 registry、嵌入/认证密钥或 CDN 检测结论。
- style preset 最初参考中的文字、照片、Logo、具体版式、组件几何、artwork、章节结构或专有视觉物件；后续组织不得为使用 preset 而重新打开最初参考。

## 迁移步骤

0. 运行 `--phase migration --binding-only`，然后在当前宿主轨迹完成 `neutral-rgba-route-probe-v1`。宿主路由与本地像素链缺一均停止；原生 Alpha 首轮和唯一 controlled-key fallback 都失败时不得降低 Alpha/抠图门槛。本步完成前不读组织材料，不初始化 pack，不打开 Ardot/微信。
1. 运行 `orgs.py init` 建立空 pack，不复制已有 pack。
2. 只登记本轮原始材料到 `sources.json`；默认填写 `provenance.visual_input_source_ids` 和四类 `excluded_visual_reference_kinds`。若用户明确选 preset，把 preset JSON 本身登记为 style source，并使用 `explicit-style-grammar` 的 abstract-only scope、review time 与 non-copy 契约。
3. 从组织证据推导 2–3 条路线，生成五项 calibration strip；preset 只写入被选 route，其他 route 保持 source-zero。先校准再全文。
4. 生成同一家族的 master 与 1–3 个 companion，保留当前组织的无水印母版；母版放在 Git 忽略的 `unwatermarked-masters/` 私有输入目录，换机时从组织私有资产库单独恢复。对符合 V1 的不透明生成图创建独立 marked derivative，使用仓库外随机 32-byte 密钥完成像素鉴权、独立 PSNR 和完整画面 390px/JPEG-Q75 模拟后才登记 final 文件。两类资产分别标记 `background_variant`。为整个 family 声明单一 light/dark surface mode、归一化复制安全区、正文颜色、最低 4.5 对比度与复制区方差上限。
5. 运行 `orgs.py validate` 分析所有底图实际像素；明暗模式混杂、大块相反色、复制区不均匀、文字对比不足或 family 色调跨度过大时必须重做校准资产，不能进入文章 root。通过后才将批准的 Ardot file/page/root、density mode 和 background family 写回 organization pack，并把状态改为 `confirmed`。
6. 在同一校准条中批准 `typography` 策略、授权边界、至少两个原生 construction recipes 与每篇上限；每个 recipe 至少两种非字体构造手法和两个可编辑图层，不复制另一公众号的字效。
7. 为当前文章批准 `interaction_plan`：默认 2–3 个 semantic modules，按实际 chapter 顺序分布 early/middle/late；每个 module 绑定本篇 source blocks，逐 transport instance 计算唯一 key/hash。不要复制另一篇文章的任务、文案或 Ardot nodes。
8. 为当前文章生成四枚不同微组件，不在 PNG 中为排版留白。Codex Desktop 用 `chatgpt-web-image-route` 操作 ChatGPT，首轮直接要求真透明 provider-original PNG 并真实下载，以 `--require-native-alpha` 只做验真与规范化；其他 harness 可用等价原生/API 路由。仅当该原图未通过严格 Alpha/像素门禁时，允许一次 controlled-key fallback 并以 `--key-color` 安全分离。逐张通过 RGBA8、robust Alpha bbox、紧裁切、无截边/彩色或中性 halo/碎片/底板门禁，并验证完整派生 lineage 后注册为 `article-micro`，再在 Ardot 建原生组件；image node 回写 derivative 的同一 asset ID/SHA，不加可见 backplate。
9. 为当前文章写 2–4 个有语义的表现型文字时刻，引用批准 recipe，回写唯一 Ardot 文本/点缀 node 与 style 证据。
10. 在当前文章 revision 中为每个 interaction module 建 `closed/open/fallback` 原生 group states，覆盖全部 instance IDs/hashes，并保存三态 390 px 截图与文件哈希。
11. 完成文章后从同一 article root 导出五类 390 px 截图，记录每个样本的正文对比度；导出所有 visual-kit instances 与逐实例 node properties。通过 visual review v3 后，冻结 handoff v5 与 `ardot-current-root-layer-export-v1`：chapter y 连续覆盖 artboard，current-root export 完整绑定 section/layer/source-node/font/render-style/body-assets，底图为精确 3x 无字层，cutout/photo/SVG 保持独立。编译前必须由当前 Ardot 宿主真实重读并导出另一份 live root。无 signer 的新 harness 使用 `current-session-draft`：带 `--session-draft` 绑定 `wechat-candidate.html` / `candidate-report.json`，在同一宿主轨迹中实际写入微信、重开并逐章 readback，但固定 `portable_audit_verified: false`。需要可携带审计时，新 harness 再提供真实 `host.receipt.attest` callable 和受保护公钥信任库，分别对 Ardot live read 和微信 readback 签发 Ed25519 receipt，使用终态 `wechat.html` / `compile-report.json` 链。缺 signer 只表示未迁移 `portable-signed-audit`，不再阻断本次 current-session 草稿。Article-JSON 预览不得投递；两档草稿都不得未经单独确认正式发表/群发。
12. 为目标公众号单独运行 `wechat-svg-smil-self-v1` 探针：禁止 JavaScript、`details`、任何 transport `id` 与跨 ID timing；先验证保存回读，再登记带有效期的 iOS/Android 真机证据。只有该账号 profile 为 current/passed 才可保留动态候选，否则同一草稿使用静态回退。缺失 profile 不取消创作层 module，只改变投递 payload。另从保存草稿取得实际 `mmbiz.qpic.cn` 正文图与封面派生图，对 locally verified carriers 运行水印 detector；required 模式未达到 `transport_verified` 时不得发布。

任何一步若需要查看旧视觉来“找感觉”，应停止并回到本轮原始材料、组织物件、真实照片和校准条，而不是把旧风格解释为品牌事实。已经沉淀为 preset 的风格只读取仓库中的抽象 grammar 与 SHA，不回看原稿。
