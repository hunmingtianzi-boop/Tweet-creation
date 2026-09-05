# Tweet Creation / Organization WeChat Studio

> [!IMPORTANT]
> **当前可执行版本只能运行在 Codex Desktop。** 拉取仓库并不等于环境已经可用。开始前必须安装同一 release 的三个仓库 Skill。仅制作透明组件时，另行安装并绑定当前 workspace 的 [Codex with ChatGPT](https://github.com/XiaoDuoYa/codex-with-chatgpt)，并在 Codex 内置 Browser 登录 ChatGPT；仅生成不透明底图/封面时需要 ImageGen。设计阶段连接并登录 Ardot Remote，取得精确 file/root 权限；投递阶段另行准备目标微信公众号登录或 API 凭据。当前发布锁只支持 Apple Silicon macOS + CPython 3.9。其他 LLM、harness、Linux、Windows 或 Intel Mac 目前不能声称可执行兼容。

克隆后先读[克隆、安装与登录前置条件](references/host-prerequisites.md)，并在读取任何组织材料前运行：

```bash
ORG_WECHAT_SOURCE_ROOT=/ABSOLUTE/SOURCE/CHECKOUT
python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" clone-check \
  --skills-root /ABSOLUTE/CODEX/SKILLS/ROOT \
  --phase full
```

该检查证明本地文件、版本、锁定依赖字节与脱敏 MCP 配置；如果当前
模型 registry 已知，还应对每个实际可见 ID 重复加
`--visible-tool-id ID`。`current_task_reload_required: true` 必须先重载/新开任务。
ChatGPT、Ardot、微信登录和当前文件/账号权限仍必须由本次 Codex 会话的 live probes 证明。

启动时一次询问小组件数量 `0–4`、是否 SVG、风格和是否生成底图；用户可以先提供材料，待共同理解后随分镜一次确认，不要求新用户先懂 route 名称。确认值写入 `article.production_preferences`，其中 `style_route` 与 `article.route` 一致。结合封面计划把三项生图选择保存到 `generation-plan.json`，给上述命令追加 `--generation-plan ABSOLUTE_FILE`，并原样带入各阶段 `target.generation`。全部关闭时不要求生图服务；未传选择时保守检查全部依赖。

本次审计修复的入口、原始节点转换、真实多宽度回读与人工验收动态草稿路线见 [集成说明](references/audit-repair-integration.md)。短通知不再为凑章节/交互/艺术字配额扩写；密度和构图比例是建议，内容完整性、透明资产、对比度和发布授权仍是硬门槛。新增传输方案必须经真实 Ardot/微信账号验收；本地测试不等于平台验证完成。

一套可迁移到不同组织和公众号的 **Codex Desktop + Ardot** 工作流。它把可编辑视觉组件、每个组织的品牌资料、单篇文章事实和最终微信投递适配分开管理。这里的“可迁移”指不同组织与公众号之间的内容/品牌迁移，不代表已经支持任意 LLM 或运行宿主。

不是“换 Logo 和颜色”的统一模板。新公众号会先建立组织包，再按该组织的受众、语气、视觉母题、文章类型和真实资料生成文章与文件资产。

## 安装版运行位置

默认迁移路径从已加载的顶层
`SKILLS_ROOT/org-wechat-studio/SKILL.md` 解析绝对
`ORG_WECHAT_RUNTIME_ROOT`。`chatgpt-web-image-route` 和
`ardot-wechat-publisher` 是同一 Skill root 下的顶层 sibling；主包不再内嵌另一份
可发现 Skill。用户项目保持为 cwd，所有会话产物写入该项目内绝对、
Git-ignored、create-once 的 `ORG_WECHAT_SESSION_ROOT`，不写入安装包。macOS
临时目录使用 `/private/tmp/...`，不使用 `/tmp/...` symlink。

只有在明确开发本仓库、且未选中 installed release 时，才可将当前仓库绝对根
当作 `ORG_WECHAT_RUNTIME_ROOT`。源码 fallback 不能在 installed release 验证失败后静默接管。

```bash
ORG_WECHAT_RUNTIME_ROOT=/ABSOLUTE/SKILLS_ROOT/org-wechat-studio
ORG_WECHAT_SESSION_ROOT=/ABSOLUTE/USER/PROJECT/output/runtime/SESSION_UNIQUE
```

## 使用声明

公开使用本仓库工作流制作的公众号推文，必须在正文最后保留以下可见文字：

> 感谢拓浙 AI 生态提供本篇内容生产工作流支持。

这是工作流使用归属，不是目标组织的品牌元素，因此不得被 organization pack 改写，也不得删除、隐藏、图片化或移到正文中间。Ardot 中应保留末位原生可编辑文本节点。发布前使用 `scripts/validate_workflow_attribution.py` 校验 handoff v5 的当前 Ardot root 节点导出，并使用 `scripts/validate_transport_fidelity.py` 校验同一 root 的逐章图层导出。保存并重新打开草稿后，再同时校验末位感谢语与逐章 section/text/asset/390px 回读。投递有两档保证：无 signer 的 `current-session-draft` 可以在当前宿主轨迹中创建并回读验证草稿，但始终标记 `portable_audit_verified: false`；只有含两份 Ed25519 receipt 的 `portable-signed-audit` 才能声称可携带签名审计。两档都不会隐式授权正式发表或群发；用户当次明确确认后，`current-session` API 路径还必须由宿主进程注入 live authority，现场重读精确 Ardot/账号/草稿并消费该确认事件。单独 CLI 或本地 JSON 不能自证发布授权；通过 live 门禁后仍必须标记 `portable_audit_verified: false`。

`current-session-draft` 路径（必须保留当前宿主的真实 Ardot reread 和微信写入/重新打开轨迹）：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_workflow_attribution.py" handoff.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store delivery/publisher.sqlite3 preflight-account \
  --target-account appid:EXACT_APPID --output delivery/account-preflight.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store delivery/publisher.sqlite3 prepare-uploads handoff.json \
  --target-account appid:EXACT_APPID --output delivery/upload-map.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --intended-html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --require-live-root --session-draft
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json \
  --session-draft --output delivery --check
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_workflow_attribution.py" handoff.json \
  --saved-draft-visible-text saved-draft-visible-text.txt \
  --require-readback
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --html delivery/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --compile-report delivery/candidate-report.json --require-compile-report \
  --expected-target-account 'exact-account-ref-from-delivery-preflight' \
  --readback saved-draft-readback.json --require-readback --session-draft
```

`prepare-uploads` 不会覆盖 `upload-map.json`：输出父目录必须事先存在且全路径不穿过用户 symlink，否则在任何上传前停止。首次运行会预留 `.<输出文件名>.upload-journal.jsonl`，对每笔上传前后追加哈希链事件，并绑定 canonical store 路径和持久 store identity。已知失败后只能用原命令、原 store、原输出路径续跑；已提交的 SHA/账号/类型直接复用，换库、丢失 committed 行、`pending` 或 `ambiguous` 都必须先人工对账，换输出名也不会解锁重传。

`portable-signed-audit` 路径：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_workflow_attribution.py" handoff.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store delivery/publisher.sqlite3 preflight-account \
  --target-account appid:EXACT_APPID --output delivery/account-preflight.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store delivery/publisher.sqlite3 prepare-uploads handoff.json \
  --target-account appid:EXACT_APPID --output delivery/upload-map.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --intended-html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --require-live-root
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --upload-map delivery/upload-map.json \
  --output delivery --check
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --compile-report delivery/compile-report.json --require-compile-report
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_workflow_attribution.py" handoff.json \
  --saved-draft-visible-text saved-draft-visible-text.txt \
  --require-readback
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --html delivery/wechat.html \
  --live-root-export qa/live-current-root.json \
  --live-root-receipt qa/live-current-root-receipt.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --compile-report delivery/compile-report.json --require-compile-report \
  --expected-target-account 'exact-account-ref-from-delivery-preflight' \
  --readback saved-draft-readback.json \
  --readback-receipt saved-draft-readback-receipt.json \
  --require-readback
```

## Source-zero 默认模式

新公众号只从本轮明确允许的组织资料、原始文案、品牌文件和真实照片开始视觉校准。工作流不会打开 `examples/`、另一组织的 pack、旧推文截图/PDF 或旧 Ardot 文件来“找风格”。仓库中的历史目录仅用于迁移兼容审计，不是视觉基准，也不参与测试。

机器门槛会检查 source-zero 输入清单、四类旧视觉排除项、四项已确认生产偏好、按 `0–4` 选定的文章专属微组件、与 SVG 选择相符的零模块或 2–3 个 semantic interaction modules、与底图选择相符的原生连续表面或同家族底图、每个已选小组件的 RGBA8/robust Alpha/紧裁切/无 matte 最终 cutout、Ardot 原生组件 node 与 asset SHA 证据、表现型字体的原生文本 node/style 证据，schema-v3 的 390 px 视觉证据，以及 handoff v5 的逐章冻结图层与草稿回读。

只有 `portable-signed-audit` 要求宿主从真实 Ardot 工具响应签发短时效 `ardot-host-live-read-receipt-v1`，并在重新打开微信草稿后签发 `wechat-host-saved-draft-receipt-v1`。宿主私有 Ed25519 私钥；仓库只能从 root-owned、非 symlink、组/其他用户不可写的信任库读取公钥，`ORG_WECHAT_HOST_RECEIPT_TRUST_STORE` 最多选择这个受保护文件的绝对路径，不能直接注入公钥。`host.receipt.attest` 缺失不再阻断 `delivery/full` 中的 current-session 草稿写入；它只使 `portable-signed-audit` 不可用。无 signer 时仍必须在同一宿主会话中真实重读精确 Ardot file/root，绑定 live export、`wechat-candidate.html`、`candidate-report.json`，写入微信后重新打开并逐章验收；本地 JSON 不能代替这些宿主轨迹。receipt 会绑定 runtime binding、provider/session/request、目标 HTML 路径、handoff、编译报告、微信账号/草稿与整份 readback 字节，因此普通环境变量、复制 JSON、改时间戳或伪造 mmbiz URL 都不能自证“刚刚读取”。

所有公开工作流 CLI（包括组织包读写/门禁、视觉方向、分镜、视觉套件、Ardot manifest/视觉复核、runtime preflight、Browser 下载摄取、Ardot handoff、WeChat publisher、transport validator、final compiler、watermark 与 cutout/inspect）均拒绝普通 `python3 scripts/...` 直调，必须经 `python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" "$ORG_WECHAT_RUNTIME_ROOT/scripts/TARGET.py" ...`。runner 会先用跟随 trusted bundle 的平台依赖锁验证 Pillow/cryptography 全部可执行字节，然后从一次性 snapshot 导入；`PYTHONPATH`、`sitecustomize`、未锁定 wheel 或同名模块不能进入最终验证进程。

这个门槛不只在 CLI `__main__` 检查：发布级 compiler/validator API 在函数内也会再验证 secure runtime。普通 import 的测试或外部 harness 只能调用显式的 candidate/diagnostic API；它们不产生 `wechat.html` / `compile-report.json`，也不能返回任何可发布声明。

## 能力

- 新组织调研与组织包初始化。
- 全文前先做 2–3 组 Ardot 小样校准，未批准路线不得开始整篇。
- 先写 4–10 章叙事分镜，再选组件和生图，避免 block 直接变卡片。
- 启动时选择 SVG 才规划 2–3 个语义动态模块；不选则使用零模块 `static-selected`。四张并列点击卡仍只算一个模块，逐卡 transport instance 分别保留静态 key/hash。
- 语气、品牌色、视觉路线、文章类型与事实来源建模。
- 按公众号与文章类型生成资产计划。
- 分镜后按已确认数量从浮动插图、章节转场、行内解释图和收尾视觉中选择 0–4 个语义角色，只生成当前推文真正需要的互不相同小组件。
- 封面背景、章节视觉、透明/开放边缘插画、技术解释图与照片派生资产的生成和注册。
- 选择生成底图时，按“一个母版 + 1–3 个同系列变体”登记 family/variant/copy-safe zone；不选时只用 Ardot 原生填充、渐变与开放矢量。两种模式都禁止黑白表面跳变。
- Ardot 语义变量模式、原生组件、390 px 长文画板和分段视觉 QA。
- 由文章 JSON 生成可执行的 Ardot 装配清单。
- 默认开放式构图；闭合方框不超过正文区块的 20%、不连续，并至少保留三处不对称或越界视觉。
- 微组件图片不超过 72% 行宽、整体不超过 82%；证据要求随数量缩放为 `min(3, count)` 个截图区段/偏移/构图关系，数量不小于 2 时必须左右错落且有明显尺寸变化。含字组件禁止文字框/底板，主短句至少 22 px、1.35× 正文。静态微信适配也保留所有实际实例，不转成通栏卡片。
- 默认 `compact-editorial` 信息密度：15–17 px 正文、1.45–1.62 行高、轻微负字距、8–14 px 段距、24–40 px 章内主间隔，并校验内容占用率与最大无意空洞。
- 每个组织先校准表现型字体策略；单篇只在 2–4 个高影响位置使用可编辑 Ardot 标题字，正文保持紧凑可读，禁止 AI 字图。
- 16 类语义区块用于 Ardot 作者组装；最终微信 HTML 只从冻结的 Ardot 章节/图层/文字/几何证据编译，不再按 block 模板二次设计。
- 事实来源、占位符、图片、Logo、二维码和微信安全格式校验。
- 固定 `wechat-svg-smil-self-v1` 交互能力：生成无 ID、自触发 SVG/SMIL 与 CSS 横滑候选，强制语义哈希静态回退、草稿结构回读和目标账号 iOS/Android 能力档案；任一门槛失败即降级同一草稿。
- 封面使用目标账号永久素材 `thumb_media_id` 并在草稿回读中验证，不与正文图片链路混用。
- 默认只生成草稿交付物，正式发布需要单独确认。

## 快速开始

启动时不手填庞大 profile，也不手写 `loaded/available`。先审计平台；当前 Codex Desktop 通过已验证的安装 release、adapter allowlist 和当前 model-visible registry id 生成非签名本会话 census，再从紧凑 target 文件生成 profile：

```bash
ORG_WECHAT_RUNTIME_ROOT=/ABSOLUTE/SKILLS_ROOT/org-wechat-studio
ORG_WECHAT_SESSION_ROOT=/ABSOLUTE/USER/PROJECT/output/runtime/SESSION_UNIQUE

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/release_skills.py" verify-installed \
  /ABSOLUTE/SKILLS_ROOT/.org-wechat-release-manifests/RELEASE_SHA.json \
  --skills-root /ABSOLUTE/SKILLS_ROOT

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" --platform-audit

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \
  init-current-session-census \
  --phase migration --session-id CURRENT_HOST_SESSION_ID \
  --visible-tool-id image_gen__imagegen \
  --visible-tool-id view_image \
  --visible-tool-id codex-with-chatgpt \
  --visible-tool-id browser:control-in-app-browser \
  --visible-tool-id mcp__node_repl__js \
  --skills-root /ABSOLUTE/INSTALLED/SKILLS/ROOT \
  --release-manifest /ABSOLUTE/INSTALLED/SKILLS/ROOT/.org-wechat-release-manifests/RELEASE_SHA.json \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --output "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json"

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" init-profile \
  "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json" \
  "$ORG_WECHAT_SESSION_ROOT/target.json" \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --phase migration \
  --output "$ORG_WECHAT_SESSION_ROOT/migration-profile-UNIQUE.json"

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \
  "$ORG_WECHAT_SESSION_ROOT/migration-profile-UNIQUE.json" \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --session-root "$ORG_WECHAT_SESSION_ROOT" \
  --phase migration --binding-only \
  --output "$ORG_WECHAT_SESSION_ROOT/migration-binding-UNIQUE.json"
```

Migration profile 只绑定生图/摄取/检查能力，不包含组织、Ardot 或微信链接。`--session-root` 是强制外置边界：必须是已存在、全路径无 symlink、位于已安装 Skill 之外且在 Git 外或被 owning Git 忽略的绝对目录；摄取/处理器路径全部绝对绑定到这里，严禁写进 Skill。已安装 runtime 可为只读，自检不会往 Skill 根写 `.runtime-preflight-*`。该 census 明确是 `current-session-model-visible-intent`，不是 host-attested registry，后续仍要真实 live probes。默认 migration 报告不生成 RGBA 探针动作；只有显式 `--include-legacy-rgba-probe` 才生成一个非阻断旧路线诊断，它不授权正式资产注册。Browser 生成第一个实际文章小组件后，必须通过 `scripts/ingest_browser_download.py` create-once 摄取宿主返回的绝对原图路径；原图可为真 Alpha 或事先规划的均匀纯色 key 源，但注册前派生图仍必须通过真 RGBA8、Alpha、matte/光晕/边缘/紧裁切门槛。当前 Codex Desktop 可在该真实 host trace 中以 `finalize-current-session-migration` 产生 `operational_ready: true`的同会话续跑报告；它保持 `phase_ready: false`，因为只有真实 host signer 可产生可携带的 `phase_ready: true`。缺少 `filesystem.access.lease` 或 `host.migration.finalize` 不阻断 migration 当前会话续跑，只使相应高等级保证不可用。普通 Python callback 只能作可选 veto policy，不能升级保证。

迁移自测通过后，将 target 阶段改为 `authoring`、`delivery` 或 `full`。当前会话路径要先以新阶段重跑 `init-current-session-census --phase <新阶段>`，再对新 census 调用 `init-profile`；不允许把 phase-bound migration census 用于其他阶段。然后对新 profile 运行 binding gate。`authoring/full` 只接受同一 trusted bundle/adapter/route 的当前会话迁移续跑，或宿主签名迁移结果。`delivery/full` target 的 `terminal_state` 缺省为 `draft`；`wechat.draft` API 不推导正式发布权限，`publish+api` 必须另有 `wechat.current-session-authority` 或 portable receipt，否则报告会将 API live publish 标为不可用并列出 UI live 候选。

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \
  "$ORG_WECHAT_SESSION_ROOT/full-profile-UNIQUE.json" \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --phase full --binding-only \
  --output "$ORG_WECHAT_SESSION_ROOT/binding-report-UNIQUE.json"
```

只有 binding report 的 `ok` 和 `binding_ready` 同时为 true，且当前宿主轨迹已闭合该阶段动作，才进入材料与视觉校准。C2C doctor、ChatGPT 文字回复、页面预览、本地报告或模型手写 receipt 均不算 host route proof。首张正式资产仍要保留独立 lineage。水印 secret 只在当前清单存在 eligible carriers 时要求。完整命令、target schema、摄取与终态合同见[运行环境启动自检](references/runtime-preflight.md)。

绑定通过后立即执行报告的 `host_setup_actions`：`migration/authoring/full` 先加载两个 ChatGPT 技能和内置 Browser，运行 C2C 日常检查，保持一个可见的 ChatGPT 标签；如果要登录/2FA/同意，在读材料前就只请求这一个操作。`migration` 紧接执行一次中性 RGBA 链路实测；普通 `authoring/full` 不重复这张 smoke image。之后再准备 Ardot；微信选 API 时授权 provider，只有 UI 路线才打开无 token 公众平台入口。ChatGPT 严禁 Computer Use 和外部浏览器。`bootstrap` 只准备 `ardot.create`，`delivery` 不打开 ChatGPT。任何登录成功后都在同一 session 重新探针，不把带 token 的跳转链接或 ChatGPT 对话 URL 落盘。

新组织还没有 Ardot file/root 时，先完成上述 `migration` 自测，再将目标命令改为 `--phase bootstrap`，验证 `ardot.create` 后只创建空白设计/页，再使用新 file/root 重跑目标阶段（默认 `full`，用户明确只做 Ardot 时为 `authoring`）。`bootstrap` 不要求微信目标或登录，也不需要伪造 Ardot 链接。

安装态不允许临时 `pip install` 改写依赖根；先运行已审核 wheel 锁的平台门禁：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" --platform-audit
```

只有源码开发者在独立开发环境中才可以用源码根的绝对路径安装
`$ORG_WECHAT_SOURCE_ROOT/requirements.txt`；这不会更新受信任的
`runtime/python-dependency-lock.json`，也不允许跳过平台审计。

列出已有组织包：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/orgs.py" list
```

初始化新公众号：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/orgs.py" init new-account-id \
  --name "新组织或公众号名称" \
  --root organizations
```

先生成组织视觉校准方向（只做小样，不做全文）：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_directions.py" \
  organizations/new-account-id recruitment \
  --background-mode generated-family \
  --output output/new-account-id/visual-directions.json
```

`--background-mode` 必须与启动时已确认的选择一致：生成底图用 `generated-family`，不生成用 `native-surfaces`。

待用户批准 Ardot 小样并回写 `organization.visual.calibration` 后，生成通用资产计划与文章叙事分镜。`asset-plan` 不再预造四枚通用微组件；分镜批准后由 `build_visual_kit.py` 按 `production_preferences.micro_component_count` 和 `visual_kit.selected_roles` 生成当前推文实际需要的 0–4 枚：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/orgs.py" asset-plan \
  organizations/new-account-id recruitment \
  --route confirmed-route \
  --background-mode generated-family \
  --output output/new-account-id/recruitment-asset-plan.json
```

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_storyboard.py" article.json \
  --output output/new-account-id/article-slug/storyboard-plan.json
```

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_kit.py" article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug/visual-kit-plan.json
```

AI 生成的不透明底图或纯生成 raster 封面，在登记资产前先保留无水印母版并生成带来源水印的派生图。`PROVENANCE_WATERMARK_KEY` 必须来自仓库外的 secret store，以 `hex:` 或 `base64:` 表示至少 32 个随机字节；裸口令会被拒绝。如需 raw-ID 记录，先将 `PROVENANCE_WATERMARK_PRIVATE_ROOT` 设为一个已存在且位于所有 Git 仓库外的私密目录：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/provenance_watermark.py" embed \
  organizations/new-account-id/assets/generated/background-master-raw.png \
  organizations/new-account-id/assets/derived/background-master-final.png \
  --key-epoch 1 \
  --report organizations/new-account-id/assets/derived/background-master-watermark.json \
  --private-record /secure/private-registry/background-master.json
```

上述成品、公开报告与私密记录都是 create-once：路径已存在时不会覆盖。嵌入时会强制重跑完整画面的 `390px-if-larger → JPEG Q75` 模拟；不承诺裁切、加边、旋转或透视变换后的截图检出。

只有公开报告为 `local_verified` 后才注册 final 文件，并同时绑定 pack 内的无水印母版与公开报告。登记、`orgs.py validate`、Ardot manifest 和微信编译都会用外部密钥重新鉴权，不信任 JSON 中自报的 `authenticated`：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/orgs.py" register-asset organizations/new-account-id \
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
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/provenance_watermark.py" detect \
  "/absolute/path/background-final.png" \
  --report "$audit_dir/local-detect.json"
```

检查保存后草稿的真实微信托管图由 publisher 的 API 回读完成：
它从权威 `draft/get` 响应取得真实 `mmbiz.qpic.cn` URL，用内置
受锁定下载器取回完整对象，再调用同一水印检测器。正式链路不
依赖 `curl`，也不接受人工填写的 CDN URL。

无 host signer 的 current-session API 草稿走完整的 `capture-raw →
Browser/Computer Use 打开确切草稿并逐章截取 390 px PNG → ingest →
capture-readback --capture-bundle` 链：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store delivery/publisher.sqlite3 preflight-account \
  --target-account appid:EXACT_APPID --output delivery/account-preflight.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-raw DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output "$EXTERNAL_READBACK_ROOT/raw-draft-UNIQUE.json"

# 同一 Browser/Computer Use session 打开该 account/draft，产出每章真实 390px PNG。
# token-bearing query 只留在活跃浏览器中，不得写入命令、文件或 bundle。
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/ingest_wechat_readback_capture.py" \
  HANDOFF_JSON OUTPUT/candidate-report.json \
  "$EXTERNAL_READBACK_ROOT/raw-draft-UNIQUE.json" \
  --runtime-profile "$ORG_WECHAT_SESSION_ROOT/delivery-profile-UNIQUE.json" \
  --runtime-report "$ORG_WECHAT_SESSION_ROOT/delivery-preflight-report-UNIQUE.json" \
  --registry-census "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json" \
  --target-account appid:EXACT_APPID --draft-id DRAFT_MEDIA_ID \
  --article-revision 'sha256:EXACT_TRANSPORT_REVISION' \
  --host-session-id CURRENT_HOST_SESSION_ID \
  --capture-tool-id scripts/ingest_wechat_readback_capture.py \
  --observed-url https://mp.weixin.qq.com/cgi-bin/appmsg \
  --nonce FRESH_CURRENT_SESSION_NONCE_AT_LEAST_32_CHARS \
  --chapter-capture CHAPTER_ID "$EXTERNAL_CAPTURE_ROOT/chapter.png" RFC3339_TIME EVENT_ID \
  --output-dir "$EXTERNAL_READBACK_ROOT/ingested-capture-UNIQUE"

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-readback \
  HANDOFF_JSON OUTPUT/candidate-report.json DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output-dir "$EXTERNAL_READBACK_ROOT/readback-UNIQUE" \
  --capture-bundle "$EXTERNAL_READBACK_ROOT/ingested-capture-UNIQUE/capture-bundle.json"
```

`--chapter-capture` 按章重复。三类输出都要放在 runtime/installed Skills 之外、
已存在的无 symlink 父目录下，且最终文件/目录必须尚未存在。Bundle 仅是
current-session 回读证据，明确为 `host_attested=false`、`portable=false`、
`publication_authority=false`；缺 signer 不阻断草稿回读，也绝不授权
`freepublish`。

Portable signed 路线保留独立的 host screenshot manifest，不使用 capture bundle：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-readback \
  HANDOFF_JSON OUTPUT/compile-report.json DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output-dir "$EXTERNAL_READBACK_ROOT/portable-readback-UNIQUE" \
  --screenshots DELIVERY/portable-signed-wechat-chapter-screenshots.json
```

通过时 `watermark-carrier-census.json` 中每个应检载体都必须是
`transport_verified`，并绑定下载字节 SHA/长度与本地的
`payload_fingerprint`、`key_epoch`、`version`、`purpose`、`algorithm`。
微信 CDN 可能改变文件 SHA；任一应检载体无法鉴真都阻断交付。

按启动时确认的选项在 `article.json` 写入 `interaction_plan`：`use_svg: true` 时使用 `dynamic-default`，2 个模块分布在 `early` + `middle`，3 个再增加 `late`；`use_svg: false` 时使用零模块的 `static-selected`。动态方案先绑定 chapter、source blocks 和逐实例语义哈希，当前 Ardot revision 的三态截图在全文装配后补齐。详见 [动态组件构图与计数](references/interaction-composition.md)。

为本篇文章生成小组件/小插图计划：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_kit.py" article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug/visual-kit-plan.json
```

逐张生图、验图，每张都必须绑定正文原句、具体主体/动作、分镜章节和构图职责。Codex Desktop 用内置 Browser 让 ChatGPT 生成并下载 provider-original PNG；原图放 `assets/generated/`，不直接进 Ardot。每张真实组件在请求前从 `source_generation.source_options` 选择真透明 `native-alpha` 或易安全分离的纯色 `controlled-key`，两者都可作为首试。以下是 `native-alpha` 的处理示例：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/prepare_micro_cutout.py" \
  path/to/raw.png path/to/derived.png \
  --role floating-spot \
  --article-id article-slug \
  --asset-slot-id kit.floating-spot \
  --prompt-sha256 sha256:PROMPT_SHA \
  --generation-route chatgpt-web-image-route-v1 \
  --acquisition-report path/to/provider-acquisition-v2.json \
  --require-native-alpha \
  --report path/to/cutout-report.json
```

然后对派生图运行像素级 Alpha、尺寸与角色宽高比检查：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/inspect_asset.py" \
  path/to/derived.png --role floating-spot
```

每个已选真实小组件可在请求前直接选择 `source_generation.source_options` 中的 native-alpha 或 controlled-key。前者使用 `--require-native-alpha` 验真且不暗中去背景；后者使用当前 slot 的 `controlled_key_color` 与完整 `processor_args`，可直接作为首试，不需伪造 native-alpha 失败。不得把所有 slot 硬编码为同一键色。无论 raw 路线，只有终态 `assets/derived/` 成品通过 RGBA8、真 Alpha、紧裁切、open-edge、矩形底/matte/halo/debris 与多底色像素门禁才能做成 Ardot 原生组件。将每个已选组件的 file/node/name 证据写回文章；只有 `ready_for_layout: true` 才生成 Ardot 装配清单：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_ardot_manifest.py" article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug/ardot-manifest.json
```

按分镜章节完成 Ardot 长文装配后，截取 Hero、章节、证据、复杂区块和 CTA 五类实际节点，并导出全部 visual-kit instance inventory 与逐实例 node properties，建立独立 schema-v3 验收文件：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_review.py" visual-review.json --article article.json
```

把路径写入 `article.visual_review_file`。通过后，从同一 Ardot root 冻结 handoff v5 与逐章图层 export，再生成微信投递文件。当前宿主无 receipt signer 时使用 `current-session-draft`：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store delivery/publisher.sqlite3 prepare-uploads handoff.json \
  --target-account appid:EXACT_APPID --output delivery/upload-map.json
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/validate_transport_fidelity.py" handoff.json \
  --intended-html output/new-account-id/article-slug/wechat-candidate.html \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json --require-upload-map \
  --require-live-root --session-draft
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/compile_wechat.py" \
  --transport-fidelity handoff.json \
  --live-root-export qa/live-current-root.json \
  --upload-map delivery/upload-map.json \
  --session-draft \
  --output output/new-account-id/article-slug \
  --check
```

该路径只有在当前宿主中实际写入微信、重新打开草稿并通过带 `--session-draft --require-readback` 的逐章验收后，才能称为“当前会话已验证草稿”。未签名的 candidate/report 只做结构绑定，始终保持 `draft_write_eligible: false`、`delivery_eligible: false`、`finalization_verified: false` 与 `portable_audit_verified: false`；草稿写入是当前宿主可见轨迹中的可逆动作策略，不是本地 JSON 可携带的授权声明。需要可携带审计时，再切换到带 `--live-root-receipt`、终态 `wechat.html` / `compile-report.json` 和草稿 readback receipt 的 `portable-signed-audit`。两条路径都默认停在草稿，正式发表/群发需另行明确确认。

详细流程见[使用说明](references/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.md)，所有已知故障点、机器门禁和降级语义见[端到端断点矩阵](references/end-to-end-breakpoint-matrix.md)，传输契约见[Ardot → 微信高保真传输](references/ardot-transport-fidelity.md)，跨公众号边界见[organization pack 迁移](references/organization-pack-migration.md)，水印合同见[隐藏来源水印](references/provenance-watermark.md)，改进依据见[source-zero 审计](references/source-zero-audit.md)。

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

`organizations/` 与 `examples/` 中的历史内容不得作为新公众号的视觉输入。其他公众号应从空 organization pack 开始，新增独立组织证据、Ardot 品牌模式和文章组件；只有启动时选择生成底图时才建立底图家族。

`article.json` 是内容源，Ardot 是视觉源；`wechat.html` 只是最终传输文件。

## 动态组件 A/B MVP

仓库开发树可以保留同输入的静态/动态对照实验，但 release 包不携带 `experiments/`。主工作流只在已确认 `use_svg: true` 时创建 2–3 个 semantic modules；否则为零模块。transport marker 数量不等于 module 数量。任何实验候选都不提供剪贴板直投入口；采用后的状态必须回到当前 Ardot root，并经 handoff v5 冻结编译、草稿回读和目标账号 iOS/Android 能力验证后才可选择动态 payload。

## 安全边界

- Logo 和二维码只能来自用户或官方资料。
- 生成图像不能冒充真实人物、活动或项目成果。
- 组织包不存储 AppSecret、access token 或其他账号凭据。
- 正式发布始终需要一次独立确认。

## 验证

以下只是源码 checkout 的开发者回归，不是安装后的运行命令。
从任意 cwd 执行时都使用绝对源码根：

```bash
ORG_WECHAT_SOURCE_ROOT=/ABSOLUTE/SOURCE/CHECKOUT
(cd "$ORG_WECHAT_SOURCE_ROOT" && python3 -m unittest discover -s tests -p 'test_*.py' -v)
python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" validate-structure
```

`validate-structure` 是发布硬门禁，只使用 Python 标准库，不依赖用户环境里
偶然存在的 `yaml`。`skill-creator/scripts/quick_validate.py` 可在开发环境中作为
可选交叉检查，但它不是发布真相来源，也不得把 PyYAML 加入生产
`requirements.txt` 或锁定执行运行时。

跨平台 CI 只运行不依赖真实登录和受信任本机 wheel 的契约测试，并验证未知 OS/Python 会在执行目标前 fail-closed；它不表示 Linux、Windows、Intel Mac 或其他 harness 已获得工作流运行支持。完整发布回归只能在 `runtime/platform-support.json` 已登记、且 `secure_runner.py --platform-audit` 真正通过的 Codex Desktop 运行时执行，不能让 CI 临时生成的 dependency candidate 自动升级信任。

## 确定性发布与安装

三个 Skill 使用同一份 byte-level release manifest；包内明确排除 `examples/`、`experiments/`、`organizations/`、`output/` 与缓存，因此迁移安装不会顺带携带旧稿视觉。完成全量测试和内置 `validate-structure` 后，为本次版本创建清单：
本节是唯一的源码开发例外：组包必须同时读取仓库中两个 wrapper 源目录，
因此要显式使用源码 checkout 的绝对根，不使用已安装且故意不含嵌套 wrapper
的 `ORG_WECHAT_RUNTIME_ROOT`。

```bash
ORG_WECHAT_SOURCE_ROOT=/ABSOLUTE/SOURCE/CHECKOUT

python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" write-manifest \
  "$ORG_WECHAT_SOURCE_ROOT/release/org-wechat-skills-v1.json"
python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" verify \
  "$ORG_WECHAT_SOURCE_ROOT/release/org-wechat-skills-v1.json"
```

安装会先逐字节验证仓库与清单、在临时目录组包、保留旧 Skill 的时间戳备份，再替换 `org-wechat-studio`、`chatgpt-web-image-route` 和 `ardot-wechat-publisher`。同时把本次清单 create-once 保存到 Skill 根目录，供当前 Codex census 和 installed-release 校验使用；未来 adapter 的契约测试不得把它解释为已支持其他 harness：

```bash
python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" install \
  "$ORG_WECHAT_SOURCE_ROOT/release/org-wechat-skills-v1.json" \
  --skills-root /ABSOLUTE/CODEX/SKILLS
python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" verify-installed \
  /ABSOLUTE/CODEX/SKILLS/.org-wechat-release-manifests/RELEASE_SHA.json \
  --skills-root /ABSOLUTE/CODEX/SKILLS
```

清单与任一已安装字节不一致都必须停止；不要手工复制单个 `SKILL.md`，也不要把仓库工作分支已更新误报成当前 harness 已加载更新。
