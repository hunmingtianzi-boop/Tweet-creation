# 跨公众号 organization pack 迁移

迁移目标是复用流程语义，不复制另一个公众号的外观。新公众号始终建立新目录、新 organization ID、新 Ardot variable mode 和新视觉校准。

迁移开始时先运行[运行环境启动自检](runtime-preflight.md)。目标 harness 必须加载当前项目根 Skill 和仓库内 publisher Skill 的相同 SHA，并把自己的工具映射到 `image.generate`、`image.inspect`、`ardot.create/read/write/export`、`wechat.draft`、UI fallback 与 `secret.resolve`。先用 binding-only 检查无凭据链接与 provider/session 路由，随后对新组织的 Ardot file/root 和目标公众号做本次会话宿主工具探针。本地 profile 不能自证 live ready；另一环境的登录态、工具清单、probe 报告和 `ok: true` JSON 都不能迁移为当前证据。每个新 harness 都要建立等价 adapter 路由；Codex 示例只读取 `runtime/adapters/codex-desktop.json`，不带走它的登录态。

若新 harness/新组织尚无 Ardot file/root，先用 `bootstrap` 阶段绑定 adapter 中的 `ardot.create`，创建空白目标后再改用目标阶段（默认 `full`，明确只创作时为 `authoring`）。`bootstrap` 不要求微信登录，只解决自举，不允许读取或复用旧推文设计。

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
- 另一公众号的已加水印图片、raw watermark ID、私有 registry、嵌入/认证密钥或 CDN 检测结论。
- style preset 最初参考中的文字、照片、Logo、具体版式、组件几何、artwork、章节结构或专有视觉物件；后续组织不得为使用 preset 而重新打开最初参考。

## 迁移步骤

1. 运行 `orgs.py init` 建立空 pack，不复制已有 pack。
2. 只登记本轮原始材料到 `sources.json`；默认填写 `provenance.visual_input_source_ids` 和四类 `excluded_visual_reference_kinds`。若用户明确选 preset，把 preset JSON 本身登记为 style source，并使用 `explicit-style-grammar` 的 abstract-only scope、review time 与 non-copy 契约。
3. 从组织证据推导 2–3 条路线，生成五项 calibration strip；preset 只写入被选 route，其他 route 保持 source-zero。先校准再全文。
4. 生成同一家族的 master 与 1–3 个 companion，保留当前组织的无水印母版；母版放在 Git 忽略的 `unwatermarked-masters/` 私有输入目录，换机时从组织私有资产库单独恢复。对符合 V1 的不透明生成图创建独立 marked derivative，使用仓库外随机 32-byte 密钥完成像素鉴权、独立 PSNR 和完整画面 390px/JPEG-Q75 模拟后才登记 final 文件。两类资产分别标记 `background_variant`。为整个 family 声明单一 light/dark surface mode、归一化复制安全区、正文颜色、最低 4.5 对比度与复制区方差上限。
5. 运行 `orgs.py validate` 分析所有底图实际像素；明暗模式混杂、大块相反色、复制区不均匀、文字对比不足或 family 色调跨度过大时必须重做校准资产，不能进入文章 root。通过后才将批准的 Ardot file/page/root、density mode 和 background family 写回 organization pack，并把状态改为 `confirmed`。
6. 在同一校准条中批准 `typography` 策略、授权边界、至少两个原生 construction recipes 与每篇上限；每个 recipe 至少两种非字体构造手法和两个可编辑图层，不复制另一公众号的字效。
7. 为当前文章批准 `interaction_plan`：默认 2–3 个 semantic modules，按实际 chapter 顺序分布 early/middle/late；每个 module 绑定本篇 source blocks，逐 transport instance 计算唯一 key/hash。不要复制另一篇文章的任务、文案或 Ardot nodes。
8. 为当前文章生成四枚不同微组件，不在 PNG 中为排版留白。逐张通过 RGBA8、robust Alpha bbox、紧裁切、无截边/白黑色 matte 门禁，注册为 `article-micro`，再在 Ardot 建原生组件；image node 回写同一 asset ID/SHA，不加可见 backplate。
9. 为当前文章写 2–4 个有语义的表现型文字时刻，引用批准 recipe，回写唯一 Ardot 文本/点缀 node 与 style 证据。
10. 在当前文章 revision 中为每个 interaction module 建 `closed/open/fallback` 原生 group states，覆盖全部 instance IDs/hashes，并保存三态 390 px 截图与文件哈希。
11. 完成文章后从同一 article root 导出五类 390 px 截图，记录每个样本的正文对比度；导出所有 visual-kit instances 与逐实例 node properties。通过 visual review v3 后，冻结 handoff v5 与 `ardot-current-root-layer-export-v1`：chapter y 连续覆盖 artboard，current-root export 完整绑定 section/layer/source-node/font/render-style/body-assets，底图为精确 3x 无字层，cutout/photo/SVG 保持独立。编译前由当前 Ardot 宿主重新导出另一份 live root，并由目标 harness 的真实 `host.receipt.attest` callable 用私有 Ed25519 私钥对工具响应签发短时效 receipt；新 harness 必须配置 root-owned、无 symlink、组/其他用户不可写的公钥信任库，不得用环境公钥替代。先跑带 `--intended-html` 的 live-root gate，再跑 final compiler；微信回读还需第二份宿主签名 receipt，绑定账号/草稿、HTML、compile report 和 readback 全字节。缺这两项宿主能力时只能迁移 authoring，不能声称迁移了可验证投递。Article-JSON 预览不得投递。
12. 为目标公众号单独运行 `wechat-svg-smil-self-v1` 探针：禁止 JavaScript、`details`、任何 transport `id` 与跨 ID timing；先验证保存回读，再登记带有效期的 iOS/Android 真机证据。只有该账号 profile 为 current/passed 才可保留动态候选，否则同一草稿使用静态回退。缺失 profile 不取消创作层 module，只改变投递 payload。另从保存草稿取得实际 `mmbiz.qpic.cn` 正文图与封面派生图，对 locally verified carriers 运行水印 detector；required 模式未达到 `transport_verified` 时不得发布。

任何一步若需要查看旧视觉来“找感觉”，应停止并回到本轮原始材料、组织物件、真实照片和校准条，而不是把旧风格解释为品牌事实。已经沉淀为 preset 的风格只读取仓库中的抽象 grammar 与 SHA，不回看原稿。
