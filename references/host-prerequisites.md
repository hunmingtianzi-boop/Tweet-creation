# 克隆、安装与登录前置条件

## 当前支持边界

这个仓库当前不是通用 LLM / 通用 harness 工作流。可执行发布版只支持：

- **Codex Desktop 本地任务**；
- Apple Silicon macOS；
- 发布锁中登记的 CPython 3.9 与依赖字节；
- Codex 当前会话实际可见的 Skill、Browser、ImageGen、Ardot 与微信投递路线。

ChatGPT 在这里是由 Codex 调用的规划、审阅和透明图来源，不是替代 Codex 的执行宿主。仓库中的语义 schema、organization pack 和 transport contract 可以作为未来移植依据，但这不等于其他 harness 已经可运行。其他 LLM、CLI agent、云端 agent、Windows、Linux 或 Intel Mac 在新增并审核 adapter、登录路线、完整前向测试和发布锁之前，一律标记为 **unsupported**，不得声称兼容。

`git clone` 只取得代码，不会带走任何 Skill 加载状态、ChatGPT Project/连接、Cookie、OAuth、Ardot 权限、微信登录、公众号凭据、目标文件/root 或移动端交互证据。

## 拉取后必须准备

| 条件 | `migration` | `bootstrap` | `authoring` | `delivery` | `full` |
|---|---:|---:|---:|---:|---:|
| Codex Desktop + 锁定平台 | 必须 | 必须 | 必须 | 必须 | 必须 |
| 同一 release 的三个仓库 Skill | 必须 | 必须 | 必须 | 必须 | 必须 |
| `codex-with-chatgpt` Skill、构建产物与当前 workspace 连接 | 选 RGBA 时 | — | 选 RGBA 时 | — | 选 RGBA 时 |
| Node.js ≥ 20 与 `cloudflared` | 选 RGBA 时 | — | 选 RGBA 时 | — | 选 RGBA 时 |
| 内置 Browser 中的 ChatGPT 登录 | 选 RGBA 时 | — | 选 RGBA 时 | — | 选 RGBA 时 |
| Codex ImageGen | 选不透明生图时 | — | 选不透明生图时 | — | 选不透明生图时 |
| `view_image` 验图 | 必须 | — | 必须 | 必须 | 必须 |
| Ardot Remote 连接、登录与精确 file/root 权限 | — | 必须 | 必须 | 必须 | 必须 |
| 微信目标账号登录或运行时 API 凭据 | — | — | — | 必须 | 必须 |

Computer Use 只能作为声明过的 Ardot/微信 UI fallback。ChatGPT 生成与 C2C 配置只能使用 Codex 内置 Browser，禁止用 Computer Use、Chrome、Safari、截图或剪贴板代替。

Ardot 必须分开记录四层状态：本机 MCP 配置存在、当前任务已注入必需
tool IDs、同会话 OAuth/精确 file/root 可读、本次远程操作有确定返回。
前一层不能推导后一层。`codex mcp list/get` 只是本机配置证据；即使显示
OAuth，当前任务没有 `mcp__ardot_remote__*` 时也只能重载/新开任务，
仓库无法热注入。

## 第一次拉取的顺序

1. 在 **Codex Desktop** 中把这个 clone 打开为本地任务；不要先把材料交给另一个 LLM 执行。
2. 只有选中真实小组件生图时，才安装并配置 [`Codex with ChatGPT`](https://github.com/XiaoDuoYa/codex-with-chatgpt)。它是仓库外部依赖，本仓库不会把它打包进 release。必须把连接绑定到当前 clone 的精确 workspace，而不是同名旧 checkout。
3. 从本仓库发布清单原子安装三个同版本 Skill：

   ```bash
   ORG_WECHAT_SOURCE_ROOT=/ABSOLUTE/SOURCE/CHECKOUT
   python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" install \
     "$ORG_WECHAT_SOURCE_ROOT/release/org-wechat-skills-v1.json" \
     --skills-root /ABSOLUTE/CODEX/SKILLS/ROOT
   ```

4. 新开或重新加载 Codex 任务，让本次 release 的 Skill registry 生效。
5. 先记录用户的生产偏好（允许理解材料后再确认），用 generation-plan.json 声明组件/底图/封面生成选择，再运行克隆条件声明：

   ```bash
   python3 -I -S "$ORG_WECHAT_SOURCE_ROOT/scripts/release_skills.py" clone-check \
     --skills-root /ABSOLUTE/CODEX/SKILLS/ROOT \
     --phase full --generation-plan /ABSOLUTE/generation-plan.json
   ```

   可把 `full` 换成 `migration`、`bootstrap`、`authoring` 或 `delivery`。命令会真实
   执行锁定 Python 分发文件审计，并以脱敏方式检查 Ardot 本机配置。
   当当前模型注册表可见时，对每个实际可见的 ID 重复加
   `--visible-tool-id ID`。若返回 `current_task_reload_required: true`，立即重载/
   新开 Codex 任务并重跑，不要在旧任务继续试调。只有
   `local_prerequisites_ready: true` 才说明本地文件、版本和锁定依赖字节已配齐；
   该命令仍不会把配置当成登录/权限证明，因此 `live_session_ready` 与
   `ready_to_read_source_material` 固定为 false。
6. 由当前 Codex 会话运行 `runtime_preflight.py`，闭合报告中的 `host_setup_actions` 和 live probes。只有这一步可以确认当前 registry、页面登录、账号身份和精确 Ardot file/root。

   `migration` 的默认报告不会发出合成 RGBA 探针动作，也不需要生成测试图。只有在排查旧版路线时，才显式向 `runtime_preflight.py` 加 `--include-legacy-rgba-probe`；此时才会发出 `blocking=false` 的 `run-migration-rgba-route-probe`，且它不能作为正式文章资产的注册授权。

## 登录与打开项

### ChatGPT / Codex with ChatGPT

- 先由 `codex-with-chatgpt` 执行 update check、sandbox allow、当前 workspace setup/doctor 和 workspace identity 检查。
- 只保留一个 Codex 内置 Browser ChatGPT 标签。
- 真实出现 ChatGPT 登录、CAPTCHA、2FA 或同意页时，保持页面不关闭，让用户只完成当前一步，然后在同一会话重探。
- C2C 的文字回复、连接文件或旧 conversation URL 都不能代替本次登录和 workspace identity。

### Ardot

- 在 Codex 中连接 `ardot-remote`，完成 Ardot OAuth；UI fallback 才打开 [`https://ardot.tencent.com/`](https://ardot.tencent.com/)。
- `bootstrap` 要证明 `ardot.create`；`authoring/full` 要证明精确 file/root 的 read/write/export；`delivery` 仍要在交付前重读同一个成稿 root。
- “浏览器已经登录”不等于 MCP 已授权；“MCP 已连接”也不等于当前用户有目标文件/root 权限，两条路线分别验收。
- `create_design` 是非幂等远程变更。超时、5xx 或截断响应都标记为
  `create-unknown`，禁止盲目重试。创建前绑定唯一 nonce/标题；恢复后先只读
  搜索或让用户在 Ardot UI 对账，明确未创建才能再发起。

### 微信公众号

- 只在 `delivery/full` 准备。UI 路线从 [`https://mp.weixin.qq.com/`](https://mp.weixin.qq.com/) 进入，API 路线只在执行时解析目标账号凭据。
- Clone、target、profile 和日志中禁止保存 token、Cookie、AppSecret 或带 token 的编辑器 URL。
- 登录后必须重新读取精确公众号身份；能打开首页不等于草稿已写入，能看到草稿不等于已经发表。
- 仓库自带的 `scripts/wechat_publisher.py` 是本地 API client，不依赖当前
  任务出现同名 MCP tool。但脚本存在也不等于账号可用。任何上传/写草稿前，
  先运行其 `preflight-account`，只读成功调用 `draft/count` 和
  `material/get_materialcount`，产出 create-once 脱敏报告且 `mutations_attempted: 0`。
  这仍不证明上传、草稿写入、UI 回读或发布权限，后续各自实测。

## 当前状态与历史问题

追加式 Markdown 问题日志只是人读历史，不是当前 readiness 证据。同一天的
“缺失→OAuth 成功→已注入→运输失败→未注入”可能分属不同 task/session，不得
合并为一个当前状态。每次启动都以本 release 新生成的 `clone-check` +
current-session census + runtime live probe 覆盖当前视图；旧日志不参与门禁。

## 停止条件

遇到以下任一项时，在读取材料或写入外部系统前停止：不是 Codex Desktop、平台不在发布锁、三个仓库 Skill 不是同一 release、本次确实需要的 `codex-with-chatgpt` 未配置到当前 workspace、当前阶段需要的 ChatGPT/Ardot/微信需要登录、Ardot file/root 不匹配，或当前 Codex registry 缺少该阶段要求的完整路线。

不要通过手写 `loaded=true`、复制旧 profile、复用 Cookie、把 shell 冒充 Browser，或把 schema 可移植性解释为其他 harness 已受支持来绕过这些条件。
