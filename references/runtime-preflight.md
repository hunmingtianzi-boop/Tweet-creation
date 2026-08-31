# 运行环境启动自检

每次启动 `org-wechat-studio` 都先做两层自检：

1. `runtime_preflight.py --binding-only` 直接检查项目文件、Markdown 链接、Skill SHA、Python/Pillow/cryptography、工作区读写、工具 provider/session 路由、无凭据 URL 与 key/path 引用形状；
2. 当前 harness 通过它自己的真实工具调用进行无副作用 probe。这些调用必须在宿主工具轨迹中可见，不能由 profile、模型文字或旧报告自证。

这个真值边界是刻意的：仓库内进程可以验证本地合同，但不能证明自己真的调用了 ImageGen、在 ChatGPT 生成并下载了原图、访问了 Ardot，或读取了已登录的微信账号。因此 binding report 可以是 `binding_ready: true`，但 `phase_ready` 始终是 `false`。不得手动改写它。

所有安全敏感 Python CLI 必须通过 `python3 -I -S scripts/secure_runner.py scripts/ENTRYPOINT.py ...` 运行。runner 只使用标准库，忽略 `PYTHONPATH`、user-site 自动加载与 `sitecustomize`；它在导入 Pillow/cryptography 前，先按 [`runtime/python-dependency-lock.json`](../runtime/python-dependency-lock.json) 校验平台/Python tag、版本、文件数和全分发文件聚合 SHA-256，再把已验证字节复制到一次性私有 snapshot 后执行入口。直接 `python3 scripts/...`、未锁定平台或任一依赖字节漂移都必须失败。当前 lock 只覆盖已验证的 `darwin-arm64-cpython-39`；迁移到其他 harness 时，必须在发布审核中增加该平台的真实分发哈希，更新 trusted-bundle allowlist，不得用环境路径跳过。

## 阶段

- `bootstrap`：新组织还没有 Ardot file/root 时使用；只检查 `ardot.create` 路由，不要求生图、ChatGPT、验图、水印 secret、微信目标/登录，也不虚构文件链接。创建空白设计后立即改用目标阶段（默认 `full`，或用户明确的 `authoring`）重绑定精确 file/root。
- `full`：主工作流默认路由；要求不透明生图、RGBA 生产、验图、Ardot、微信草稿、宿主 receipt attestor 和 secret resolver。
- `authoring`：只有用户明确要求停在创作/Ardot 时使用；要求两类生图、验图、Ardot 和水印 secret，不证明微信投递就绪。
- `delivery`：`ardot-wechat-publisher` 使用；不要求再次生图，但必须重新绑定当前 Ardot root、目标公众号和宿主 receipt attestor。

`bootstrap` / `full` / `authoring` 要求项目根 `org-wechat-studio` 的当前 SHA 状态为 `loaded`；`delivery` 要求仓库内 `ardot-wechat-publisher` 状态为 `loaded`。`available` 不等于已加载，已安装旧副本不能代替项目版本。

## 语义能力合同

| 能力 | 职责 |
|---|---|
| `image.generate.opaque` | 生成不透明的同家族底图/封面源图 |
| `image.generate.rgba` | 为文章小组件提供原图，最终必须经 `subject-cutout-rgba8-v1` 处理和验收 |
| `image.inspect` | 读图、Alpha 检查与 390 px 截图验收 |
| `chatgpt.session` | Codex Desktop 的 ChatGPT 会话/连接准备；只证明 session，不证明生图或 Alpha |
| `ardot.create` | 新组织无 file/root 时创建空白设计/页 |
| `ardot.read` | 读取当前 file、page、root 和 node |
| `ardot.write` | 创建原生文本、矢量、组件和三态 |
| `ardot.export` | 导出 node properties 和 390 px 证据 |
| `browser.control` | 操作已登录网页；优先于通用 Computer Use |
| `computer.use` | UI 末级兜底，不是必选依赖 |
| `wechat.draft` | 微信素材、封面、draft upsert/get 与 CDN 回读 |
| `host.receipt.attest` | 宿主从真实 Ardot/微信工具轨迹签发短时效 receipt；私钥不进仓库进程 |
| `secret.resolve` | 只解析水印密钥与 Git 外私密路径的可用性，不返回值；receipt 公钥不允许作为普通 secret/环境变量注入 |

目标 harness 把自己的 callable 映射到这些能力。只发现 shell、JavaScript 或 Node 执行器，不等于 Browser/Computer Use 已加载。多个 callable 共同承担一项能力时，必须属于同一 provider 和当前 session。

Codex Desktop 的机器可读路由在 [`runtime/adapters/codex-desktop.json`](../runtime/adapters/codex-desktop.json)。其中不透明路由是 `image_gen__imagegen`；RGBA 默认是复合路由：仓库内 `chatgpt-web-image-route`、已安装 `codex-with-chatgpt`、同一 provider/session 的完整内置 Browser route，以及 `scripts/prepare_micro_cutout.py`。本地 ImageGen 不得直接映射到 RGBA。该文件是路由表，不是登录或 live proof；C2C doctor、会话登录成功和页面预览都不是图像证据。当前 Codex Desktop 没有可调用的 `host.receipt.attest`，因此本机 `delivery/full` 必须 fail closed；`authoring/bootstrap` 不要求该能力。

## runtime profile

profile 是当前会话的临时意图清单，放在 Git 忽略的 `output/runtime/`。不得放入 organization pack、article 目录或 Git，不得包含 probe 结论、token、Cookie、AppSecret、密钥、raw watermark ID 或任何 secret 值。

下例展示一个已完成宿主 attestor 集成、同时使用 ChatGPT-web RGBA 复合路线的目标 `full` profile 形状。`image.generate.rgba` 是 adapter 对外暴露的语义能力；在该路线中它不对应一个可以直接登记的“RGBA 生图工具”，而是由 `chatgpt.session` + 同 provider/session 的 `browser.control` + 本地 processor 共同实现。`HOST_ATTESTOR_TOOL_ID` 是占位符，不是当前 Codex Desktop 的真实 callable，不得照抄进当前 profile。`adapter_sha256` 在每次生成 profile 时重算；已集成的其他 harness 应使用自己的 adapter，不得假冒 `codex-desktop`。

```json
{
  "schema_version": 2,
  "kind": "org-wechat-runtime-profile",
  "harness": {"name": "YOUR_INTEGRATED_HARNESS", "adapter_path": "PATH_TO_HOST_ADAPTER.json", "adapter_sha256": "sha256:CURRENT_ADAPTER_SHA"},
  "skills": [
    {"id": "org-wechat-studio", "entrypoint": "SKILL.md", "status": "loaded", "sha256": "sha256:CURRENT_SHA"},
    {"id": "ardot-wechat-publisher", "entrypoint": "skills/ardot-wechat-publisher/SKILL.md", "status": "available", "sha256": "sha256:CURRENT_SHA"}
  ],
  "tools": [
    {"id": "image_gen__imagegen", "kind": "image.generate.opaque", "status": "available", "source": "runtime-registry", "provider": "codex-image-provider", "session_id": "current-session"},
    {"id": "view_image", "kind": "image.inspect", "status": "available", "source": "runtime-registry", "provider": "codex-image-provider", "session_id": "current-session"},
    {"id": "codex-with-chatgpt", "kind": "chatgpt.session", "status": "available", "source": "skill-registry", "provider": "codex-browser", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__fetch_file_info", "kind": "ardot.read", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__fetch_editor_state", "kind": "ardot.read", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__batch_read", "kind": "ardot.read", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__batch_edit", "kind": "ardot.write", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__capture_screenshot", "kind": "ardot.export", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__export_nodes", "kind": "ardot.export", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "browser:control-in-app-browser", "kind": "browser.control", "status": "available", "source": "skill-registry", "provider": "codex-browser", "session_id": "current-session"},
    {"id": "mcp__node_repl__js", "kind": "browser.control", "status": "available", "source": "runtime-registry", "provider": "codex-browser", "session_id": "current-session"},
    {"id": "HOST_ATTESTOR_TOOL_ID", "kind": "host.receipt.attest", "status": "available", "source": "runtime-registry", "provider": "host-attestor", "session_id": "current-session"}
  ],
  "links": {
    "ardot_current_workspace": {"url": "https://ardot.tencent.com/file/123456789?web_only=1&node_id=1%3A2", "purpose": "current organization workspace"},
    "wechat_current_account": {"url": "https://mp.weixin.qq.com/", "purpose": "current visible target account"}
  },
  "capabilities": {
    "opaque_image_generation": {"mode": "tool", "status": "declared", "tool_ids": ["image_gen__imagegen"]},
    "rgba_cutout_generation": {
      "mode": "chatgpt-web",
      "status": "declared",
      "tool_ids": ["codex-with-chatgpt", "browser:control-in-app-browser", "mcp__node_repl__js"],
      "provider_skill": {"id": "chatgpt-web-image-route", "status": "loaded", "contract": "chatgpt-web-image-route-v1"},
      "output_contract": "subject-cutout-rgba8-v1",
      "processor": "scripts/prepare_micro_cutout.py"
    },
    "visual_inspection": {"mode": "tool", "status": "declared", "tool_ids": ["view_image"]},
    "ardot_authoring": {"mode": "mcp", "status": "declared", "tool_ids": ["mcp__ardot_remote__fetch_file_info", "mcp__ardot_remote__fetch_editor_state", "mcp__ardot_remote__batch_read", "mcp__ardot_remote__batch_edit", "mcp__ardot_remote__capture_screenshot", "mcp__ardot_remote__export_nodes"], "workspace_link": "ardot_current_workspace", "expected_file_id": "123456789", "expected_root_id": "1:2"},
    "wechat_delivery": {"mode": "ui", "status": "declared", "tool_ids": ["browser:control-in-app-browser", "mcp__node_repl__js"], "account_link": "wechat_current_account", "target_account_ref": "visible-account-reference"},
    "host_receipt_attestation": {"mode": "host", "status": "declared", "tool_ids": ["HOST_ATTESTOR_TOOL_ID"], "trust_boundary": "host-owned-private-key-and-protected-trust-store"},
    "secret_store": {"mode": "environment", "status": "declared", "secret_refs": ["PROVENANCE_WATERMARK_KEY"], "path_refs": ["PROVENANCE_WATERMARK_PRIVATE_ROOT"]}
  }
}
```

## 执行 binding gate

```bash
python3 -I -S scripts/secure_runner.py scripts/runtime_preflight.py output/runtime/runtime-profile.json \
  --phase full --binding-only \
  --output output/runtime/binding-report-UNIQUE.json
```

输入和输出必须位于当前工作区的 Git 忽略路径，或位于不属于任何 Git 仓库的外部临时目录。报告不覆盖已有文件，每次使用新文件名。

通过标准：

- `ok: true`
- `binding_ready: true`
- `check_level: "binding"`
- `phase_ready: false` （预期值）
- 无安全、版本、链接、provider/session 或能力缺口。

`binding_nonce` 和 `binding_digest` 必须被后续宿主 receipt 签入；`binding_digest` 同时绑定根/publisher Skill、自检程序本身、两份 `agents/openai.yaml`、adapter、setup-links、终态使用/QA/互动/水印合同，以及 compiler、asset/cutout、workflow、SVG policy、watermark 与 transport validator 的完整本地执行闭包。`requirements.txt` 精确锁定 Pillow/cryptography 版本。任一活路由或 validator 逻辑漂移都会阻断或改变绑定摘要。宿主 signer 必须将 trusted-bundle digest 与其允许的已发布 digest 比较，不能只回签模型提供的本地值。宿主保留 Ed25519 私钥；仓库进程只能从 root-owned、无 symlink、组/其他用户不可写的 JSON 信任库读取公钥。`ORG_WECHAT_HOST_RECEIPT_TRUST_STORE` 只允许选择这个受保护文件的绝对路径；直接环境公钥不被读取。仓库进程为 root 时也必须 fail closed，因为它可自行造一份“root-owned”文件。

报告的 `host_setup_actions` 是启动时立即执行的准备队列，不是文章做完后的补救：

1. 加载当前阶段的仓库 Skill；
2. 仅 `authoring/full` 且 RGBA mode 为 `chatgpt-web` 时，按顺序加载仓库 `chatgpt-web-image-route`、已安装 `codex-with-chatgpt`，执行 `update-check` / `sandbox-allow` / `doctor`，再打开或复用唯一内置 Browser 标签并完成必要的 ChatGPT 登录，最后绑定原始 PNG 下载、`scripts/prepare_micro_cutout.py` 和 `image.inspect`。`bootstrap/delivery` 不加载、登录或打开 ChatGPT；
3. 按 profile 所选 Ardot route 准备：MCP 才连接/OAuth，UI 则加载已声明的 Browser/Computer Use；`full/authoring/delivery` 打开当前精确 Ardot 目标，`bootstrap` 只打开 Ardot 中性入口；
4. 需要微信的 `delivery/full` 按 mode 准备：API 连接并授权 publisher provider；UI 才打开 `https://mp.weixin.qq.com/`，若出现扫码/登录页，保持页面、说明需要的账号登录并等待用户；
5. `delivery/full` 绑定真实 `host.receipt.attest` callable 和受保护信任库；当前 Codex adapter 没有此 callable，不得在 profile 里凭空登记。能力存在时，最终编译前必须由上一步确认的同一 Ardot provider/session 重新读取精确 file/root，写入一份新的 live current-root export；它不得复制冻结 handoff 证据，也不得由模型手写。宿主紧接真实工具响应签发最长十分钟的 `ardot-host-live-read-receipt-v1`，绑定 binding nonce/digest、trusted bundle、provider/session/request、file/root、handoff、冻结/实时字节、revision 与 intended HTML path。重新打开微信草稿后，宿主再签发 `wechat-host-saved-draft-receipt-v1`，绑定账号/草稿、HTML、compile report、live receipt 与 readback 全字节。缺 callable、信任库或任一 receipt 均不得声明完成投递。
6. `authoring/full/delivery` 解析水印 secret 引用并绑定验图能力；`authoring/full` 另绑定不透明生图，原生 RGBA tool route 仅在 adapter 选中 `mode: tool` 时绑定。`bootstrap` 不要求验图、secret 或任何生图；
7. 登录/授权后在同一 session 重新读取账号/file/root/权限。

Ardot MCP OAuth 和 Ardot 网页登录是两个独立状态；其中一个成功不能代替另一个。宿主只打开 credential-free base/current target，不将登录后含 token 的 redirect/editor URL 写入 profile 或报告。`https://chatgpt.com/` 仅是无凭据登录入口，或 C2C 在 `long-chat` 且尚无 saved chat 时允许的新对话入口；正常工作要在同一内置 Browser 标签中恢复 `codex-with-chatgpt` 管理的 saved chat/project。恢复失败时修复 C2C session，不得用 base URL 另开对话。不将 saved chat URL、会话 ID 或登录后 URL 持久化到 profile、organization pack 或 binding report。

## 当前会话 host probes

binding 通过后，按选中路线执行：

1. **Skill**：在宿主中加载对应阶段的仓库 Skill，核对实际 resource/path 和 SHA；不使用旧安装副本。
2. **ChatGPT-web RGBA**：只在 `authoring/full` 且 adapter 选中该 mode 时执行。启动时的 C2C doctor、登录成功、会话恢复或页面预览只证明路线可用，都不是 `image.generate.rgba` 的 live proof。首张正式小组件原图必须由 ChatGPT 实际生成、下载 provider original PNG、记录 source SHA，再经 `scripts/prepare_micro_cutout.py` 产生 create-once RGBA/report，并由 `image.inspect` 读图；这个“原始下载 + 本地处理 + 终图验图”链条才是 live proof。
3. **Image inspect**：只在 `authoring/full/delivery` 真实读取一张中性本地图像；`bootstrap` 不要求。只枚举 schema 不算。
4. **Ardot**：`bootstrap` 只确认 `ardot.create` callable，随后仅创建空白设计/页来建立新目标；`full`/`authoring`/`delivery` 才先用 read-only file info/editor state 核对 canonical file ID 和精确 root ID，然后在同一 provider/session 确认 write/export callable 存在，且不为读探针创建节点。
5. **WeChat**：官方 API provider 存在时优先 API；否则优先 Browser，缺 Browser 但当前 session 有完整 Computer Use route 时可用其作 UI 兜底，读取无 token 入口的当前可见账号与草稿权限。登录页返回 `needs_user_login`，不能标成通过。
6. **Secret**：只在 `authoring/full/delivery` 返回 key present/format/length 和 private-root present/writable/non-symlink/outside-Git 布尔结果；不返回 key、稳定指纹或绝对路径。
7. **Opaque ImageGen**：只在 `authoring/full` 于启动时验证宿主已绑定 `image.generate.opaque` callable，不消耗额度生成 smoke image。首张正式资产必须实际生成、读图并记录资产 SHA；失败即阻断视觉阶段。

所有宿主 probe 都必须来自本次会话。旧报告、article JSON、organization pack、重写时间戳或一段模型说明都不是证据。

## 路由与降级

- Ardot：MCP 优先，其次 Browser，最后 Computer Use。缺少可读、可写或可导出能力时，不得用 HTML 冒充 Ardot 原生稿。
- 微信：官方 API 优先，其次 Browser，最后 Computer Use。UI 路线只需 Browser 或 Computer Use 中一条在同一 provider/session 完整可用；只有 API 文档链接不等于 publisher provider 已存在。
- 选中 MCP/API/Browser 路线已完整时，缺少 Computer Use 不阻断。
- 微信未登录、账号不符或 Ardot file/root 不符时停止，等用户处理后重新 probe。
- 正式发布仍需单独明确确认；自检不扩大写入或发布权限。

## 链接与 secret 安全

- 配置入口集中在 [`runtime/setup-links.json`](../runtime/setup-links.json)。
- 其中 `https://chatgpt.com/` 只是启动时登录入口，或 C2C 批准的 `long-chat` 新对话入口，不是 runtime profile 的可持久 target；profile 中不登记 ChatGPT saved chat/project URL。
- Ardot 文件 URL 只接受 `https://ardot.tencent.com/file/<数字>`，query 只允许 `node_id` 和 `web_only=1`。
- 微信 profile 只保存无 token 的 `https://mp.weixin.qq.com/` 或 `https://api.weixin.qq.com/`。
- 拒绝 URL userinfo、显式端口、fragment、相似恶意域名和 token/secret query。
- 水印私密 registry 必须是已存在、可写、非 symlink 且位于所有 Git 仓库之外的目录。
- profile/report 输出不覆盖已有文件，不跟随末级 symlink，不进入任何 Git 仓库的非忽略路径。

## 跨 harness adapter

迁移到其他 LLM/harness 时，保留上述十三个语义能力和 probe 真值边界，替换的只是 adapter route。新 adapter 至少要列出：实际 callable ID、provider、session 绑定方式、读/写/导出责任、登录探针、secret resolver 和无副作用限制。有可验收的原生 RGBA provider 时，adapter 可以将 `image.generate.rgba` 映射为 `mode: tool` 并将 `chatgpt.session` 明确标为 unavailable，但仍必须保留 `subject-cutout-rgba8-v1`、本地 processor 和首张正式资产 live proof。新 harness 还必须实现宿主外 Ed25519 signer，分别对真实 Ardot read 与微信 saved-draft readback 签发 receipt，绑定 binding nonce/digest、目标 file/root/account/draft、实际 provider/session/request、交付字节和有效期。仓库只配置公钥；没有 signer 的 harness 可完成作者预览，但不能声明最终 Ardot→微信投递证据已验证。
