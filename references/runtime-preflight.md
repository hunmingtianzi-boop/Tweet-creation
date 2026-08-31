# 运行环境启动自检

每次启动 `org-wechat-studio` 都先做两层自检：

1. `runtime_preflight.py --binding-only` 直接检查项目文件、Markdown 链接、Skill SHA、Python/Pillow、工作区读写、工具 provider/session 路由、无凭据 URL 与 secret 引用形状；
2. 当前 harness 通过它自己的真实工具调用进行无副作用 probe。这些调用必须在宿主工具轨迹中可见，不能由 profile、模型文字或旧报告自证。

这个真值边界是刻意的：仓库内进程可以验证本地合同，但不能证明自己真的调用了 ImageGen、Ardot 或已登录的微信。因此 binding report 可以是 `binding_ready: true`，但 `phase_ready` 始终是 `false`。不得手动改写它。

## 阶段

- `bootstrap`：新组织还没有 Ardot file/root 时使用；检查 `ardot.create` 路由而不要求虚构一个文件链接，也不要求微信目标/登录。创建空白设计后立即改用目标阶段（默认 `full`，或用户明确的 `authoring`）重绑定精确 file/root。
- `full`：主工作流默认路由；要求生图、验图、Ardot、微信草稿和 secret resolver。
- `authoring`：只有用户明确要求停在创作/Ardot 时使用；不证明微信投递就绪。
- `delivery`：`ardot-wechat-publisher` 使用；不要求再次生图，但必须重新绑定当前 Ardot root 和目标公众号。

`bootstrap` / `full` / `authoring` 要求项目根 `org-wechat-studio` 的当前 SHA 状态为 `loaded`；`delivery` 要求仓库内 `ardot-wechat-publisher` 状态为 `loaded`。`available` 不等于已加载，已安装旧副本不能代替项目版本。

## 语义能力合同

| 能力 | 职责 |
|---|---|
| `image.generate` | 生成同家族底图和文章专属视觉 |
| `image.inspect` | 读图、Alpha 检查与 390 px 截图验收 |
| `ardot.create` | 新组织无 file/root 时创建空白设计/页 |
| `ardot.read` | 读取当前 file、page、root 和 node |
| `ardot.write` | 创建原生文本、矢量、组件和三态 |
| `ardot.export` | 导出 node properties 和 390 px 证据 |
| `browser.control` | 操作已登录网页；优先于通用 Computer Use |
| `computer.use` | UI 末级兜底，不是必选依赖 |
| `wechat.draft` | 微信素材、封面、draft upsert/get 与 CDN 回读 |
| `secret.resolve` | 只解析 secret 引用可用性，不返回值 |

目标 harness 把自己的 callable 映射到这些能力。只发现 shell、JavaScript 或 Node 执行器，不等于 Browser/Computer Use 已加载。多个 callable 共同承担一项能力时，必须属于同一 provider 和当前 session。

Codex Desktop 的机器可读路由在 [`runtime/adapters/codex-desktop.json`](../runtime/adapters/codex-desktop.json)。其中已列出 `image_gen__imagegen`、`view_image`、Ardot create/read/write/export MCP、Browser Skill + Node REPL、Computer Use fallback、微信 Browser 路线与水印 secret 引用。该文件是路由表，不是登录或 live proof。

## runtime profile

profile 是当前会话的临时意图清单，放在 Git 忽略的 `output/runtime/`。不得放入 organization pack、article 目录或 Git，不得包含 probe 结论、token、Cookie、AppSecret、密钥、raw watermark ID 或任何 secret 值。

下例使用仓库内 Codex adapter 的实际路由 ID。`adapter_sha256` 在每次生成 profile 时重算。

```json
{
  "schema_version": 1,
  "kind": "org-wechat-runtime-profile",
  "harness": {"name": "codex-desktop", "adapter_path": "runtime/adapters/codex-desktop.json", "adapter_sha256": "sha256:CURRENT_ADAPTER_SHA"},
  "skills": [
    {"id": "org-wechat-studio", "entrypoint": "SKILL.md", "status": "loaded", "sha256": "sha256:CURRENT_SHA"},
    {"id": "ardot-wechat-publisher", "entrypoint": "skills/ardot-wechat-publisher/SKILL.md", "status": "available", "sha256": "sha256:CURRENT_SHA"}
  ],
  "tools": [
    {"id": "image_gen__imagegen", "kind": "image.generate", "status": "available", "source": "runtime-registry", "provider": "codex-image-provider", "session_id": "current-session"},
    {"id": "view_image", "kind": "image.inspect", "status": "available", "source": "runtime-registry", "provider": "codex-image-provider", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__fetch_file_info", "kind": "ardot.read", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__fetch_editor_state", "kind": "ardot.read", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__batch_read", "kind": "ardot.read", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__batch_edit", "kind": "ardot.write", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__capture_screenshot", "kind": "ardot.export", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "mcp__ardot_remote__export_nodes", "kind": "ardot.export", "status": "available", "source": "runtime-registry", "provider": "ardot-remote", "session_id": "current-session"},
    {"id": "browser:control-in-app-browser", "kind": "browser.control", "status": "available", "source": "skill-registry", "provider": "codex-browser", "session_id": "current-session"},
    {"id": "mcp__node_repl__js", "kind": "browser.control", "status": "available", "source": "runtime-registry", "provider": "codex-browser", "session_id": "current-session"}
  ],
  "links": {
    "ardot_current_workspace": {"url": "https://ardot.tencent.com/file/123456789?web_only=1&node_id=1%3A2", "purpose": "current organization workspace"},
    "wechat_current_account": {"url": "https://mp.weixin.qq.com/", "purpose": "current visible target account"}
  },
  "capabilities": {
    "image_generation": {"mode": "tool", "status": "declared", "tool_ids": ["image_gen__imagegen"]},
    "visual_inspection": {"mode": "tool", "status": "declared", "tool_ids": ["view_image"]},
    "ardot_authoring": {"mode": "mcp", "status": "declared", "tool_ids": ["mcp__ardot_remote__fetch_file_info", "mcp__ardot_remote__fetch_editor_state", "mcp__ardot_remote__batch_read", "mcp__ardot_remote__batch_edit", "mcp__ardot_remote__capture_screenshot", "mcp__ardot_remote__export_nodes"], "workspace_link": "ardot_current_workspace", "expected_file_id": "123456789", "expected_root_id": "1:2"},
    "wechat_delivery": {"mode": "ui", "status": "declared", "tool_ids": ["browser:control-in-app-browser", "mcp__node_repl__js"], "account_link": "wechat_current_account", "target_account_ref": "visible-account-reference"},
    "secret_store": {"mode": "environment", "status": "declared", "secret_refs": ["PROVENANCE_WATERMARK_KEY"], "path_refs": ["PROVENANCE_WATERMARK_PRIVATE_ROOT"]}
  }
}
```

## 执行 binding gate

```bash
python3 scripts/runtime_preflight.py output/runtime/runtime-profile.json \
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

`binding_nonce` 和 `binding_digest` 为后续宿主签名 receipt 预留；`binding_digest` 同时绑定根/publisher Skill、自检程序本身、两份 `agents/openai.yaml`、adapter、setup-links 与本合同的可信 bundle 哈希。任一活 MCP 端点或 validator 逻辑漂移都会阻断或改变绑定摘要。未来的宿主 receipt 必须将返回的 trusted-bundle digest 与宿主允许的已发布 digest 比较，不能只回签未校验的本地值。在当前没有宿主 receipt API 时，它们不会自动把 `phase_ready` 改为 true。

报告的 `host_setup_actions` 是启动时立即执行的准备队列，不是文章做完后的补救：

1. 加载当前阶段的仓库 Skill；
2. 按 profile 所选 Ardot route 准备：MCP 才连接/OAuth，UI 则加载已声明的 Browser/Computer Use；
3. `full/authoring/delivery` 打开当前精确 Ardot 目标，`bootstrap` 只打开 Ardot 中性入口；
4. 需要微信的阶段按 mode 准备：API 连接并授权 publisher provider；UI 才打开 `https://mp.weixin.qq.com/`，若出现扫码/登录页，保持页面、说明需要的账号登录并等待用户；
5. 验图能力在每个阶段都是阻断项；生图只在非 `delivery` 阶段准备；
6. 登录/授权后在同一 session 重新读取账号/file/root/权限。

Ardot MCP OAuth 和 Ardot 网页登录是两个独立状态；其中一个成功不能代替另一个。宿主只打开 credential-free base/current target，不将登录后含 token 的 redirect/editor URL 写入 profile 或报告。

## 当前会话 host probes

binding 通过后，按选中路线执行：

1. **Skill**：在宿主中加载对应阶段的仓库 Skill，核对实际 resource/path 和 SHA；不使用旧安装副本。
2. **Image inspect**：真实读取一张中性本地图像。只枚举 schema 不算。
3. **Ardot**：`bootstrap` 只确认 `ardot.create` callable，随后仅创建空白设计/页来建立新目标；`full`/`authoring`/`delivery` 才先用 read-only file info/editor state 核对 canonical file ID 和精确 root ID，然后在同一 provider/session 确认 write/export callable 存在，且不为读探针创建节点。
4. **WeChat**：官方 API provider 存在时优先 API；否则加载 Browser Skill，读取无 token 入口的当前可见账号与草稿权限。登录页返回 `needs_user_login`，不能标成通过。
5. **Secret**：只返回 key present/format/length 和 private-root present/writable/non-symlink/outside-Git 布尔结果；不返回 key、稳定指纹或绝对路径。
6. **ImageGen**：启动时只验证宿主已绑定 callable，不消耗额度生成 smoke image。首张正式资产必须实际生成、读图并记录资产 SHA；失败即阻断视觉阶段。

所有宿主 probe 都必须来自本次会话。旧报告、article JSON、organization pack、重写时间戳或一段模型说明都不是证据。

## 路由与降级

- Ardot：MCP 优先，其次 Browser，最后 Computer Use。缺少可读、可写或可导出能力时，不得用 HTML 冒充 Ardot 原生稿。
- 微信：官方 API 优先，其次 Browser，最后 Computer Use。只有 API 文档链接不等于 publisher provider 已存在。
- 选中 MCP/API/Browser 路线已完整时，缺少 Computer Use 不阻断。
- 微信未登录、账号不符或 Ardot file/root 不符时停止，等用户处理后重新 probe。
- 正式发布仍需单独明确确认；自检不扩大写入或发布权限。

## 链接与 secret 安全

- 配置入口集中在 [`runtime/setup-links.json`](../runtime/setup-links.json)。
- Ardot 文件 URL 只接受 `https://ardot.tencent.com/file/<数字>`，query 只允许 `node_id` 和 `web_only=1`。
- 微信 profile 只保存无 token 的 `https://mp.weixin.qq.com/` 或 `https://api.weixin.qq.com/`。
- 拒绝 URL userinfo、显式端口、fragment、相似恶意域名和 token/secret query。
- 水印私密 registry 必须是已存在、可写、非 symlink 且位于所有 Git 仓库之外的目录。
- profile/report 输出不覆盖已有文件，不跟随末级 symlink，不进入任何 Git 仓库的非忽略路径。

## 跨 harness adapter

迁移到其他 LLM/harness 时，保留上述十个语义能力和 probe 真值边界，替换的只是 adapter route。新 adapter 至少要列出：实际 callable ID、provider、session 绑定方式、读/写/导出责任、登录探针、secret resolver 和无副作用限制。如果宿主未来提供可验签 receipt API，receipt 必须绑定 binding nonce/digest、阶段、目标 file/root/account、callable schema digest 和有效期；未验签 receipt 不能改变 `phase_ready`。
