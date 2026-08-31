# Tweet Creation / Organization WeChat Studio

一套可迁移到不同组织和公众号的 Codex + Ardot 工作流。它把可编辑视觉组件、每个组织的品牌资料、单篇文章事实和最终微信投递适配分开管理。

不是“换 Logo 和颜色”的统一模板。新公众号会先建立组织包，再按该组织的受众、语气、视觉母题、文章类型和真实资料生成文章与文件资产。

## 使用声明

公开使用本仓库工作流制作的公众号推文，必须在正文最后保留以下可见文字：

> 感谢拓浙 AI 生态提供本篇内容生产工作流支持。

这是工作流使用归属，不是目标组织的品牌元素，因此不得被 organization pack 改写，也不得删除、隐藏、图片化或移到正文中间。Ardot 中应保留末位原生可编辑文本节点。发布前使用 `scripts/validate_workflow_attribution.py` 校验 handoff v5 的当前 Ardot root 节点导出，并使用 `scripts/validate_transport_fidelity.py` 校验同一 root 的逐章图层导出。保存并重新打开草稿后，再同时校验末位感谢语与逐章 section/text/asset/390px 回读。投递有两档保证：无 signer 的 `current-session-draft` 可以在当前宿主轨迹中创建并回读验证草稿，但始终标记 `portable_audit_verified: false`；只有含两份 Ed25519 receipt 的 `portable-signed-audit` 才能声称可携带签名审计。两档都不授权正式发表或群发。

`current-session-draft` 路径（必须保留当前宿主的真实 Ardot reread 和微信写入/重新打开轨迹）：

```bash
python3 scripts/validate_workflow_attribution.py handoff.json
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --intended-html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --require-live-root --session-draft
python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --session-draft --output delivery --check
python3 scripts/validate_workflow_attribution.py handoff.json \
  --saved-draft-visible-text saved-draft-visible-text.txt \
  --require-readback
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --compile-report delivery/candidate-report.json --require-compile-report \
  --expected-target-account 'exact-account-ref-from-delivery-preflight' \
  --readback saved-draft-readback.json --require-readback --session-draft
```

`portable-signed-audit` 路径：

```bash
python3 scripts/validate_workflow_attribution.py handoff.json
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --intended-html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --require-live-root
python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --output delivery --check
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --compile-report delivery/compile-report.json --require-compile-report
python3 scripts/validate_workflow_attribution.py handoff.json \
  --saved-draft-visible-text saved-draft-visible-text.txt \
  --require-readback
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --compile-report delivery/compile-report.json --require-compile-report \
  --expected-target-account 'exact-account-ref-from-delivery-preflight' \
  --readback saved-draft-readback.json \
  --readback-receipt saved-draft-readback-receipt.json \
  --require-readback
```

## Source-zero 默认模式

新公众号只从本轮明确允许的组织资料、原始文案、品牌文件和真实照片开始视觉校准。工作流不会打开 `examples/`、另一组织的 pack、旧推文截图/PDF 或旧 Ardot 文件来“找风格”。仓库中的历史目录仅用于迁移兼容审计，不是视觉基准，也不参与测试。

机器门槛会检查 source-zero 输入清单、四类旧视觉排除项、同家族底图、四枚文章专属微组件、常规文章 2–3 个 semantic interaction modules 与逐实例 fallback hash、RGBA8/robust Alpha/紧裁切/无 matte cutout、Ardot 原生组件 node 与 asset SHA 证据、表现型字体的原生文本 node/style 证据，schema-v3 的 390 px 视觉证据，以及 handoff v5 的逐章冻结图层与草稿回读。

只有 `portable-signed-audit` 要求宿主从真实 Ardot 工具响应签发短时效 `ardot-host-live-read-receipt-v1`，并在重新打开微信草稿后签发 `wechat-host-saved-draft-receipt-v1`。宿主私有 Ed25519 私钥；仓库只能从 root-owned、非 symlink、组/其他用户不可写的信任库读取公钥，`ORG_WECHAT_HOST_RECEIPT_TRUST_STORE` 最多选择这个受保护文件的绝对路径，不能直接注入公钥。`host.receipt.attest` 缺失不再阻断 `delivery/full` 中的 current-session 草稿写入；它只使 `portable-signed-audit` 不可用。无 signer 时仍必须在同一宿主会话中真实重读精确 Ardot file/root，绑定 live export、`wechat-candidate.html`、`candidate-report.json`，写入微信后重新打开并逐章验收；本地 JSON 不能代替这些宿主轨迹。receipt 会绑定 runtime binding、provider/session/request、目标 HTML 路径、handoff、编译报告、微信账号/草稿与整份 readback 字节，因此普通环境变量、复制 JSON、改时间戳或伪造 mmbiz URL 都不能自证“刚刚读取”。

这四个敏感入口（runtime preflight、transport validator、final compiler、watermark verifier）均拒绝普通 `python3 scripts/...` 直调，必须经 `python3 -I -S scripts/secure_runner.py ...`。runner 会先用跟随 trusted bundle 的平台依赖锁验证 Pillow/cryptography 全部可执行字节，然后从一次性 snapshot 导入；`PYTHONPATH`、`sitecustomize`、未锁定 wheel 或同名模块不能进入最终验证进程。

这个门槛不只在 CLI `__main__` 检查：发布级 compiler/validator API 在函数内也会再验证 secure runtime。普通 import 的测试或外部 harness 只能调用显式的 candidate/diagnostic API；它们不产生 `wechat.html` / `compile-report.json`，也不能返回任何可发布声明。

## 能力

- 新组织调研与组织包初始化。
- 全文前先做 2–3 组 Ardot 小样校准，未批准路线不得开始整篇。
- 先写 4–10 章叙事分镜，再选组件和生图，避免 block 直接变卡片。
- 常规文章创作层默认规划 2–3 个语义动态模块；四张并列点击卡仍只算一个模块，逐卡 transport instance 分别保留静态 key/hash。
- 语气、品牌色、视觉路线、文章类型与事实来源建模。
- 按公众号与文章类型生成资产计划。
- 排版前强制生成四枚互不相同的文章专属浮动插图、章节转场、行内解释图和收尾视觉，并先做成 Ardot 小组件。
- 封面背景、章节视觉、透明/开放边缘插画、技术解释图与照片派生资产的生成和注册。
- AI 底图按“一个母版 + 1–3 个同系列变体”登记 family/variant/copy-safe zone，章节只改变裁切、透明度和局部构图，不随机换风格。
- Ardot 语义变量模式、原生组件、390 px 长文画板和分段视觉 QA。
- 由文章 JSON 生成可执行的 Ardot 装配清单。
- 默认开放式构图；闭合方框不超过正文区块的 20%、不连续，并至少保留三处不对称或越界视觉。
- 微组件图片不超过 72% 行宽、整体不超过 82%，四类角色左右错落并跨至少三个截图区段；含字组件禁止文字框/底板，主短句至少 22 px、1.35× 正文。静态微信适配也保留所有实际实例，不转成通栏卡片。
- 默认 `compact-editorial` 信息密度：15–17 px 正文、1.45–1.62 行高、轻微负字距、8–14 px 段距、24–40 px 章内主间隔，并校验内容占用率与最大无意空洞。
- 每个组织先校准表现型字体策略；单篇只在 2–4 个高影响位置使用可编辑 Ardot 标题字，正文保持紧凑可读，禁止 AI 字图。
- 16 类语义区块用于 Ardot 作者组装；最终微信 HTML 只从冻结的 Ardot 章节/图层/文字/几何证据编译，不再按 block 模板二次设计。
- 事实来源、占位符、图片、Logo、二维码和微信安全格式校验。
- 固定 `wechat-svg-smil-self-v1` 交互能力：生成无 ID、自触发 SVG/SMIL 与 CSS 横滑候选，强制语义哈希静态回退、草稿结构回读和目标账号 iOS/Android 能力档案；任一门槛失败即降级同一草稿。
- 封面使用目标账号永久素材 `thumb_media_id` 并在草稿回读中验证，不与正文图片链路混用。
- 默认只生成草稿交付物，正式发布需要单独确认。

## 快速开始

先运行启动自检。当前 harness 必须把真实 callable 映射为生图、验图、Ardot 创建/读写/导出、微信草稿和 secret resolver。本地脚本只验证 Skill SHA、工具路由合同和无凭据 URL；真正的 Ardot/微信/生图可用性必须来自当前宿主可见的工具调用结果。迁移到新 harness/机器/adapter/provider route 或建立新组织工作流时，在读材料前先运行 migration profile：

```bash
python3 -I -S scripts/secure_runner.py scripts/runtime_preflight.py output/runtime/migration-profile.json \
  --phase migration --binding-only \
  --output output/runtime/migration-binding-report-UNIQUE.json
```

Migration profile 只绑定 opaque/RGBA/inspect，不包含组织、Ardot 或微信链接。RGBA 能力必须匹配 adapter 的真实 `generation_route_id` 和 `neutral-rgba-route-probe-v1`。执行报告的 `host_setup_actions`：首轮要求真透明 provider-original PNG 并以 `--require-native-alpha` 验真；只有严格 Alpha/像素门禁失败后才允许一次 controlled-key fallback。nonce/digest 留在宿主 request metadata，不进入图片 prompt；该 metadata SHA、当前 provider request/original download、raw PNG 事实、secure RGBA 处理和 exact derivative 透明/浅/深三底验收必须属于同一证据链。探针只放 Git 忽略的 `output/runtime/migration-probes/<nonce>/`，禁止登记、上传 Ardot、加水印或作为风格参考。ChatGPT-web 路线遵守 C2C 单对话规则，不另开临时 chat；探针只使用无对象、无品牌、单一中灰的非语义校准轮廓，正式组件 prompt 明确排除该轮廓与灰度测试处理，避免把自检变成视觉参考。

迁移自测通过后，再为实际目标运行：

```bash
python3 -I -S scripts/secure_runner.py scripts/runtime_preflight.py output/runtime/runtime-profile.json \
  --phase full --binding-only \
  --output output/runtime/binding-report-UNIQUE.json
```

`authoring/full` 中的 `enforce-migration-rgba-route-gate` 是宿主工作流必须执行的硬门禁；本地 CLI 只负责发出该阻断动作，不能自行认证旧宿主 trace。

只有 binding report 同时为 `ok: true` 和 `binding_ready: true`，且当前宿主工具轨迹已通过所选路线的真实探针，才进入材料读取与视觉校准。报告的 `phase_ready` 故意保持 `false`，避免将自填 profile 误当宿主证据。Codex Desktop 的默认透明小组件路由是 `chatgpt-web-image-route` + `codex-with-chatgpt` + 内置 Browser。中性迁移 probe 只证明该路由在本次宿主轨迹中跑通；它不是文章资产。首张正式资产的页面生成、原图下载事件、raw SHA、RGBA 派生报告和终态验图仍共同承担它自己的 lineage。C2C doctor、ChatGPT 文字回复、页面预览、本地报告或模型手写 receipt 均不算 host route proof。Ardot 与微信必须真实读取当前 file/root/可见账号。缺登录时停在登录步骤。profile 与报告只放在 Git 忽略的 `output/runtime/`，不得包含 token、Cookie、AppSecret 或水印密钥。Codex 的精确工具路由见 [runtime/adapters/codex-desktop.json](runtime/adapters/codex-desktop.json)，完整合同见[运行环境启动自检](references/runtime-preflight.md)。

绑定通过后立即执行报告的 `host_setup_actions`：`migration/authoring/full` 先加载两个 ChatGPT 技能和内置 Browser，运行 C2C 日常检查，保持一个可见的 ChatGPT 标签；如果要登录/2FA/同意，在读材料前就只请求这一个操作。`migration` 紧接执行一次中性 RGBA 链路实测；普通 `authoring/full` 不重复这张 smoke image。之后再准备 Ardot；微信选 API 时授权 provider，只有 UI 路线才打开无 token 公众平台入口。ChatGPT 严禁 Computer Use 和外部浏览器。`bootstrap` 只准备 `ardot.create`，`delivery` 不打开 ChatGPT。任何登录成功后都在同一 session 重新探针，不把带 token 的跳转链接或 ChatGPT 对话 URL 落盘。

新组织还没有 Ardot file/root 时，先完成上述 `migration` 自测，再将目标命令改为 `--phase bootstrap`，验证 `ardot.create` 后只创建空白设计/页，再使用新 file/root 重跑目标阶段（默认 `full`，用户明确只做 Ardot 时为 `authoring`）。`bootstrap` 不要求微信目标或登录，也不需要伪造 Ardot 链接。

安装确定性图片处理依赖：

```bash
python3 -m pip install -r requirements.txt
```

列出已有组织包：

```bash
python3 scripts/orgs.py list
```

初始化新公众号：

```bash
python3 scripts/orgs.py init new-account-id \
  --name "新组织或公众号名称" \
  --root organizations
```

先生成组织视觉校准方向（只做小样，不做全文）：

```bash
python3 scripts/build_visual_directions.py \
  organizations/new-account-id recruitment \
  --output output/new-account-id/visual-directions.json
```

待用户批准 Ardot 小样并回写 `organization.visual.calibration` 后，生成资产计划与文章叙事分镜：

```bash
python3 scripts/orgs.py asset-plan \
  organizations/new-account-id recruitment \
  --output output/new-account-id/recruitment-asset-plan.json
```

```bash
python3 scripts/build_storyboard.py article.json \
  --output output/new-account-id/article-slug/storyboard-plan.json
```

AI 生成的不透明底图或纯生成 raster 封面，在登记资产前先保留无水印母版并生成带来源水印的派生图。`PROVENANCE_WATERMARK_KEY` 必须来自仓库外的 secret store，以 `hex:` 或 `base64:` 表示至少 32 个随机字节；裸口令会被拒绝。如需 raw-ID 记录，先将 `PROVENANCE_WATERMARK_PRIVATE_ROOT` 设为一个已存在且位于所有 Git 仓库外的私密目录：

```bash
python3 -I -S scripts/secure_runner.py scripts/provenance_watermark.py embed \
  organizations/new-account-id/assets/generated/background-master-raw.png \
  organizations/new-account-id/assets/derived/background-master-final.png \
  --key-epoch 1 \
  --report organizations/new-account-id/assets/derived/background-master-watermark.json \
  --private-record /secure/private-registry/background-master.json
```

上述成品、公开报告与私密记录都是 create-once：路径已存在时不会覆盖。嵌入时会强制重跑完整画面的 `390px-if-larger → JPEG Q75` 模拟；不承诺裁切、加边、旋转或透视变换后的截图检出。

只有公开报告为 `local_verified` 后才注册 final 文件，并同时绑定 pack 内的无水印母版与公开报告。登记、`orgs.py validate`、Ardot manifest 和微信编译都会用外部密钥重新鉴权，不信任 JSON 中自报的 `authenticated`：

```bash
python3 scripts/orgs.py register-asset organizations/new-account-id \
  --id visual.background-master --kind background --title "Background master" \
  --location assets/derived/background-master-final.png \
  --watermark-source assets/generated/background-master-raw.png \
  --watermark-report assets/derived/background-master-watermark.json \
  --origin generated-illustrative --style current-route --use recruitment \
  --visual-role illustrative-atmosphere \
  --background-family-id current-family --background-variant master
```

真实照片、Logo、二维码、透明小组件、SVG 和 QA 截图不进入 V1 水印链路。无水印母版的标准 `unwatermarked-masters/` 目录已被 Git 忽略，迁移时需从组织的私有资产库单独恢复。完整边界见[隐藏来源水印](references/provenance-watermark.md)。

### 检查已生成图的水印

先由 secret manager 向当前进程注入 `PROVENANCE_WATERMARK_KEY`；值必须是 `hex:` 或 `base64:` 编码的至少 32 字节随机密钥，不要写入 Git、命令参数或公开报告。检查本地成品：

```bash
audit_dir="$(mktemp -d)"
python3 -I -S scripts/secure_runner.py scripts/provenance_watermark.py detect \
  "/absolute/path/background-final.png" \
  --report "$audit_dir/local-detect.json"
```

检查保存后草稿的真实微信托管图：

```bash
curl --fail --location --silent --show-error \
  -H 'Accept: image/png,image/jpeg' \
  "$WECHAT_CDN_URL" --output "$audit_dir/wechat-hosted-image"
python3 -I -S scripts/secure_runner.py scripts/provenance_watermark.py detect \
  "$audit_dir/wechat-hosted-image" \
  --report "$audit_dir/cdn-detect.json"
```

成功时退出码为 `0`，且报告需同时为 `status: payload_authenticated` 和 `authenticated: true`。本地成品与微信 CDN 图都要核对 `payload_fingerprint`、`key_epoch`、`version`、`purpose` 和 `algorithm`；本地成品还要求 `input_sha256` 等于 embed 报告的 `post_sha256`。微信 CDN 可能改变文件 SHA，不要强求两者 SHA 相同。退出码 `1` 是 `not_detected`，可能表示未标记、密钥不对或传输破坏，不能证明“从未加过水印”；退出码 `2` 表示密钥、输入、路径或格式错误。日常检测不要使用 `--private-record`，也不要用截图、裁切图或转码图替代实际 `mmbiz.qpic.cn` 对象。

在 `article.json` 写入 `interaction_plan`：常规文章使用 `dynamic-default`，2 个模块分布在 `early` + `middle`，3 个再增加 `late`。先绑定 chapter、source blocks 和逐实例语义哈希；当前 Ardot revision 的三态截图在全文装配后补齐。详见 [动态组件构图与计数](references/interaction-composition.md)。

为本篇文章生成小组件/小插图计划：

```bash
python3 scripts/build_visual_kit.py article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug/visual-kit-plan.json
```

逐张生图、验图，每张都必须绑定正文原句、具体主体/动作、分镜章节和构图职责。Codex Desktop 默认先让 ChatGPT 直接生成具有真实透明像素的 provider-original PNG，用内置 Browser 下载原图；原图放 `assets/generated/`，不直接进 Ardot。首轮必须使用原生 Alpha 路由生成 create-once 的规范化派生图与报告：

```bash
python3 -I -S scripts/secure_runner.py scripts/prepare_micro_cutout.py \
  path/to/raw.png path/to/derived.png \
  --role floating-spot \
  --article-id article-slug \
  --asset-slot-id kit.floating-spot \
  --prompt-sha256 sha256:PROMPT_SHA \
  --generation-route chatgpt-web-image-route-v1 \
  --require-native-alpha \
  --report path/to/cutout-report.json
```

然后对派生图运行像素级 Alpha、尺寸与角色宽高比检查：

```bash
python3 -I -S scripts/secure_runner.py scripts/inspect_asset.py \
  path/to/derived.png --role floating-spot
```

`--require-native-alpha` 会拒绝 RGB、全不透明 RGBA 和假棋盘格，不会在首轮暗中去背景；通过时本地只做验真、清理透明像素 RGB、紧裁切和规范化。只有该原图未通过 Alpha/像素门禁时，才按当前 slot 的 `fallback_prompt` 重生成一次受控单色底原图，并严格使用该 slot 的 `source_generation.fallback_processor_args` / `fallback_key_color`，不得把所有 slot 硬编码为同一绿色。背景不均、主体碰边、彩色 halo、碎片或底板均阻断，不降低门槛。把四张 `assets/derived/` 成品做成 Ardot 原生组件，将 component file/node/name 证据写回文章。只有 `ready_for_layout: true` 才生成 Ardot 装配清单：

```bash
python3 scripts/build_ardot_manifest.py article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug/ardot-manifest.json
```

按分镜章节完成 Ardot 长文装配后，截取 Hero、章节、证据、复杂区块和 CTA 五类实际节点，并导出全部 visual-kit instance inventory 与逐实例 node properties，建立独立 schema-v3 验收文件：

```bash
python3 scripts/build_visual_review.py visual-review.json --article article.json
```

把路径写入 `article.visual_review_file`。通过后，从同一 Ardot root 冻结 handoff v5 与逐章图层 export，再生成微信投递文件。当前宿主无 receipt signer 时使用 `current-session-draft`：

```bash
python3 -I -S scripts/secure_runner.py scripts/validate_transport_fidelity.py handoff.json \
  --intended-html output/new-account-id/article-slug/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --require-live-root --session-draft
python3 -I -S scripts/secure_runner.py scripts/compile_wechat.py \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --session-draft \
  --output output/new-account-id/article-slug \
  --check
```

该路径只有在当前宿主中实际写入微信、重新打开草稿并通过带 `--session-draft --require-readback` 的逐章验收后，才能称为“当前会话已验证草稿”。未签名的 candidate/report 只做结构绑定，始终保持 `draft_write_eligible: false`、`delivery_eligible: false`、`finalization_verified: false` 与 `portable_audit_verified: false`；草稿写入是当前宿主可见轨迹中的可逆动作策略，不是本地 JSON 可携带的授权声明。需要可携带审计时，再切换到带 `--live-root-receipt`、终态 `wechat.html` / `compile-report.json` 和草稿 readback receipt 的 `portable-signed-audit`。两条路径都默认停在草稿，正式发表/群发需另行明确确认。

详细流程见[使用说明](references/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.md)，传输契约见[Ardot → 微信高保真传输](references/ardot-transport-fidelity.md)，跨公众号边界见[organization pack 迁移](references/organization-pack-migration.md)，水印合同见[隐藏来源水印](references/provenance-watermark.md)，改进依据见[source-zero 审计](references/source-zero-audit.md)。

## 目录

```text
├── SKILL.md
├── README.md
├── agents/
├── references/
├── scripts/
├── organizations/
├── examples/
└── tests/
```

`organizations/` 与 `examples/` 中的历史内容不得作为新公众号的视觉输入。其他公众号应从空 organization pack 开始，新增独立组织证据、Ardot 品牌模式、底图家族和文章组件。

`article.json` 是内容源，Ardot 是视觉源；`wechat.html` 只是最终传输文件。

## 动态组件 A/B MVP

仓库内提供一个同输入对照实验：A 使用静态基线排版，B 只替换为无 JavaScript、无 ID、元素自身 `begin="click"` 的 SVG 揭开组件与 CSS 横向滑动，并保留语义哈希匹配的静态降级文件。主工作流进一步固定了创作层默认 2–3 个 semantic modules；transport marker 数量不等于 module 数量。入口见 [experiments/interaction-mvp/README.md](experiments/interaction-mvp/README.md)。实验只输出 `delivery_eligible: false` 的候选片段，不提供剪贴板导入或公众号直投入口；采用后的状态必须回到当前 Ardot root，并经 handoff v5 冻结编译、草稿回读和目标账号 iOS/Android 能力验证后才可选择动态 payload。

## 安全边界

- Logo 和二维码只能来自用户或官方资料。
- 生成图像不能冒充真实人物、活动或项目成果。
- 组织包不存储 AppSecret、access token 或其他账号凭据。
- 正式发布始终需要一次独立确认。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py .
```
