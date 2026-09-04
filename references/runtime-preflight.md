# 运行环境启动自检

当前 release 的执行宿主固定为 **Codex Desktop**。第一次拉取先读[克隆、安装与登录前置条件](host-prerequisites.md)并从源码 checkout 运行 `release_skills.py clone-check --phase <phase>`；该命令只证明本地文件/二进制，不能证明登录。每次换 clone、机器、Codex 会话、adapter/provider route 或 Skill release 后，都要在读取组织材料前执行下列 live self-check。它不要求操作者手写庞大 profile：Codex Desktop 从“已验证安装 release + adapter allowlist + 本会话模型实际可见 registry id”生成非签名 census intent，再从 census 与紧凑 target 确定性生成 profile。

其他 LLM/harness、Linux、Windows、Intel Mac 或未审核 adapter 当前为 unsupported。`build-census` 和语义能力 schema 仅保留给未来 adapter 开发与契约测试；它们不能把另一个宿主现场升级为受支持运行时。

## 双层保证

| 档位 | 当前 Codex Desktop | 可以证明 | 不可声称 |
|---|---|---|---|
| `current-session` | 默认可用 | 已验证的 source-zero Skill release、当前宿主工具轨迹、Browser 返回的绝对下载路径、本地 create-once 摄取哈希，以及真实透明素材自身的质量检查 | 宿主签名 Browser 事件、宿主强制文件系统隔离、可脱离本会话携带的审计结论 |
| `host-enforced-source-zero` | 仅在 `filesystem.access.lease` callable 存在时升级 | 宿主只允许当前输入、当前 organization pack 和 runtime 输出，并拒绝 examples、其他组织、旧输出和旧 Ardot 引用 | 没有真实 lease callable 时不得伪装这一档 |
| `portable-signed-migration` | 仅在 `host.migration.finalize` 和宿主重放账本存在时升级 | 最长十分钟的 Ed25519 receipt 绑定 nonce/digest/route/prompt/raw/derivative/report/inspection、installed release、registry census 和 filesystem policy | 没有宿主 signer 时不得将本地 JSON 当作签名 receipt |

`filesystem.access.lease`、`host.migration.finalize` 和用于 portable audit 的 `host.receipt.attest` 是保证升级，不是当前会话的默认硬阻断。正式文章微组件在 current-session runtime binding、canonical request、create-once ingestion、exact raw bytes 和所选素材质量检查通过后，可以在 `authoring/full` operational accept；但固定是 operator/harness-trusted、`host_attested=false`、`portable=false`。不存在读取材料前的 RGBA 校准图门禁。`image.provider.acquire.authority` 仅是可选 trusted-harness veto policy，不是鉴真边界。

## 0. 安装根与会话根

从已加载的 `org-wechat-studio/SKILL.md` 反向解析其绝对父目录，定义为
`ORG_WECHAT_RUNTIME_ROOT`。安装版中，它与 `chatgpt-web-image-route`、
`ardot-wechat-publisher` 同为一个 Skill root 下的顶层 sibling，主包不包含
可发现的嵌套 `skills/`。用户项目仍是当前工作目录；不 `cd` 到 Skill。
将用户项目中绝对、Git-ignored、create-once 的会话目录定义为
`ORG_WECHAT_SESSION_ROOT`。macOS 临时目录使用 `/private/tmp/...`，不使用经过
symlink 的 `/tmp/...`。

```bash
ORG_WECHAT_RUNTIME_ROOT=/ABSOLUTE/SKILLS_ROOT/org-wechat-studio
ORG_WECHAT_SESSION_ROOT=/ABSOLUTE/USER/PROJECT/output/runtime/SESSION_UNIQUE

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/release_skills.py" verify-installed \
  /ABSOLUTE/SKILLS_ROOT/.org-wechat-release-manifests/RELEASE_SHA.json \
  --skills-root /ABSOLUTE/SKILLS_ROOT
```

下文所有 runner 和目标脚本都使用 `ORG_WECHAT_RUNTIME_ROOT` 下的绝对路径；
census、target、profile、evidence 和 report 都使用 `ORG_WECHAT_SESSION_ROOT`
下的绝对路径。安装包目录内不允许生成 `output/`。

## 1. 平台与依赖审计

所有安全敏感 Python CLI 通过锁定 runner 执行：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" --platform-audit
```

当前 trusted lock 支持 `darwin-arm64-cpython-39`。未知 OS/CPU/Python 必须在运行目标入口前失败。新平台只能生成待审核 candidate：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  --dependency-candidate "$ORG_WECHAT_SESSION_ROOT/dependency-candidate-PLATFORM-UNIQUE.json"
```

candidate 是 create-once、`trusted: false` 的审核材料，不修改 lock，不自动升级 trusted release。支持矩阵见 [`runtime/platform-support.json`](../runtime/platform-support.json)，完整非 MCP 依赖见 [`runtime/non-mcp-dependencies.json`](../runtime/non-mcp-dependencies.json)。

## 2. 安装包与 registry census

先通过 `scripts/release_skills.py` 安装并验证三个 Skill。安装器会在 Skill root 下 create-once 保存：

```text
<skills-root>/.org-wechat-release-manifests/<release_sha256>.json
```

安装态验证只接受这个目录中的 canonical 普通文件，文件名必须精确等于内部
`release_sha256 + ".json"`；Skill root、manifest store、三个包目录及其父路径都
不得经过 symlink。随后验证器才会校验 manifest 内部结构并逐字节 census 三个
sibling Skill。这个门禁只是本机 create-once 的位置与字节绑定，不是密码学签名，
也不是 host attestation；需要可携带保证时仍必须走独立的宿主签名路径。

不要信任 profile 或人工 JSON 里填写的 `loaded/available`。当前 Codex Desktop 没有 `host.registry.export` callable，默认用下面命令。`--visible-tool-id` 由宿主/代理从当前 model-visible registry 原样传入，只填 id，不填 kind/provider/session/status；CLI 会从已审核 adapter 与已验证 release 派生这些字段：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \
  init-current-session-census \
  --phase migration \
  --session-id CURRENT_HOST_SESSION_ID \
  --visible-tool-id image_gen__imagegen \
  --visible-tool-id view_image \
  --visible-tool-id codex-with-chatgpt \
  --visible-tool-id browser:control-in-app-browser \
  --visible-tool-id mcp__node_repl__js \
  --skills-root /ABSOLUTE/INSTALLED/SKILLS/ROOT \
  --release-manifest /ABSOLUTE/INSTALLED/SKILLS/ROOT/.org-wechat-release-manifests/RELEASE_SHA.json \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --output "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json"
```

输出必须标记 `registry_assurance.mode=current-session-model-visible-intent`、`host_attested_registry=false`、`portable=false`、`requires_later_live_probes=true`。它可用于生成本会话 profile；当前 Codex Desktop 的 `authoring/full` 不会仅因 provider policy hook 或 portable signer 缺失而失败。它不得称为 host-attested registry，也不替代后续 login/account/file/root/generation/download 真实探针和每张正式图的完整链门禁。

以下 `build-census` 格式只供未来 adapter 开发者做契约验证，不是当前 release 的操作路径，也不能用于真实文章或投递。未来版本若正式新增宿主，必须先让该宿主生成不可手写的 export、增加审核 adapter/登录路线/发布锁并完成全量前向测试；届时 export 还必须同时包含 `registry_export` 调用轨迹，且工具清单中有同 provider/session 的 `host.registry.export` 行：

```json
{
  "schema_version": 1,
  "kind": "org-wechat-host-registry-export-v1",
  "harness": "codex-desktop",
  "session_id": "current-session-id",
  "registry_export": {
    "capability": "host.registry.export",
    "tool_id": "host.registry.export",
    "provider": "host-registry-provider",
    "session_id": "current-session-id",
    "request_id": "host-request-id"
  },
  "tools": [
    {
      "id": "image_gen__imagegen",
      "kind": "image.generate.opaque",
      "status": "available",
      "source": "runtime-registry",
      "provider": "codex-image-provider",
      "session_id": "current-session-id"
    }
  ],
  "skills": [
    {
      "id": "org-wechat-studio",
      "status": "loaded",
      "installed_entrypoint": "/ABSOLUTE/INSTALLED/SKILLS/ROOT/org-wechat-studio/SKILL.md"
    },
    {
      "id": "chatgpt-web-image-route",
      "status": "loaded",
      "installed_entrypoint": "/ABSOLUTE/INSTALLED/SKILLS/ROOT/chatgpt-web-image-route/SKILL.md"
    },
    {
      "id": "ardot-wechat-publisher",
      "status": "available",
      "installed_entrypoint": "/ABSOLUTE/INSTALLED/SKILLS/ROOT/ardot-wechat-publisher/SKILL.md"
    }
  ]
}
```

实际 export 必须由 callable 生成并列出当前 adapter 所需的全部 host tools；不允许操作者手写这份 export。然后生成 census：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" build-census \
  "$ORG_WECHAT_SESSION_ROOT/host-registry-export.json" \
  --skills-root /ABSOLUTE/INSTALLED/SKILLS/ROOT \
  --release-manifest /ABSOLUTE/INSTALLED/SKILLS/ROOT/.org-wechat-release-manifests/RELEASE_SHA.json \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --output "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json"
```

`init-current-session-census` 和 `build-census` 都直接调用 `release_skills.verify_installed_packages`，验证真实安装路径和包摘要，并绑定 worktree、Git HEAD、adapter、provider/session。本地工具严格按 phase census 注入：`browser.download.ingest`/`scripts/ingest_browser_download.py` 用于 migration/authoring 图片摄取，不会被 API delivery 偷渡；`wechat.current-session-readback`/`scripts/ingest_wechat_readback_capture.py` 只在 delivery/full 的完整 Browser 路由中可用。`scripts/wechat_publisher.py` 作为本地 `wechat.draft` API 工具，不读取、不落盘微信凭据。草稿回读路由仅用于打开写后的确切草稿与截图，不是生图/下载摄取，也不推导发布权限。

安装 release 包内必须不存在 `.git/.pytest_cache/__pycache__/examples/experiments/organizations/output`。这证明 Skill 包本身 source-zero，不等于宿主已强制限制模型读取其他本地文件。

## 3. 生成 profile

操作者只写 `org-wechat-runtime-target-v1`：`links`、Ardot/WeChat 精确目标、当前资产清单，以及真实可用时才请求的高等级 assurance。`artifact_inventory.census_complete` 为 true 且没有 eligible carriers 时，水印 secret 不是前置条件；只有确实存在可嵌入载体时才需要 `PROVENANCE_WATERMARK_KEY` 和 Git 外 private root。一个无载体的 authoring target 例子：

```json
{
  "schema_version": 1,
  "kind": "org-wechat-runtime-target-v1",
  "links": {
    "ardot_current_workspace": {
      "url": "https://ardot.tencent.com/file/123456789?web_only=1&node_id=1%3A2",
      "purpose": "current organization workspace"
    }
  },
  "targets": {
    "ardot": {
      "workspace_link": "ardot_current_workspace",
      "expected_file_id": "123456789",
      "expected_root_id": "1:2"
    }
  },
  "artifact_inventory": {
    "census_complete": true,
    "source_sha256": "sha256:REPLACE_WITH_64_HEX",
    "eligible_watermark_carriers": []
  }
}
```

`migration` target 的 `links`/`targets` 为空且可不带资产清单。当前会话 census intent 是 phase-bound：切换到 `bootstrap/authoring/delivery/full` 时必须先重跑 `init-current-session-census --phase <目标阶段>`，不可复用 migration census。`delivery/full` 再增加 `targets.wechat.mode` (`api` 或 `ui`)、`terminal_state` (`draft` 或 `publish`，缺省为 `draft`)、`account_link` 和 exact `target_account_ref`。当选择 `api + draft` 且未选 portable `host_receipt_attestation` 时，profile 必须单独选中同 account 的 `wechat_current_session_readback`，且 census 中必须有完整 `wechat.current-session-readback` Browser/Computer Use 路由；缺路由直接失败。Portable signed API draft 保留自己的 screenshot/receipt 路线，不要求或注入 current-session bundle route。`wechat.draft` 只能证明 API 草稿路径，绝不推导发布权限：`publish+api` 还必须有独立 `wechat.current-session-authority` 或已选 portable receipt；否则 binding 提前失败并列出 UI live route。`publish+ui` 必须使用已声明的 Browser/Computer Use live route，并在点击前消费当次确认、点击后权威回读状态。不要在 adapter 无 callable 时填 `assurance.filesystem_access_lease` 或 `assurance.migration_probe_finalization`。

```bash
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

`--session-root` 是 migration 的强制外置边界：目录必须已存在、使用
canonical 绝对路径、全路径无 symlink、位于已安装 Skill 之外，并且位于
所有 Git 仓库之外或被 owning Git 明确忽略。报告把会话资产以及
ingest/processor 可执行文件都冻结为绝对路径；缺参、指向 Skill 内部或未忽略的
另一个项目都会在会话绑定前失败。profile 也必须在其所属 Git 工作树明确忽略
的绝对会话目录，或不属于任何 Git 仓库的外部绝对临时目录中。“位于 Skill root
外”不等于私有。profile 不得含 token、Cookie、AppSecret、水印密钥、ChatGPT
saved-chat URL 或微信带 token 链接。所有报告 create-once，拒绝覆盖和任一路径
组件中的 symlink。

## 4. C2C 与 Browser 启动动作

ChatGPT-web RGBA route 的 `host_setup_actions` 要依次闭合：

1. C2C `update-check` 和 `sandbox-allow`；
2. 确认当前精确 worktree session，不串到其他 checkout；
3. 读取 tunnel status，由用户在需要时选择直连/隧道；
4. 新 workspace 执行 setup；旧 workspace 恢复唯一 saved project/conversation；
5. 校验 project identity、connector identity 和 workspace identity；
6. 运行 `workspace-info` 和 `doctor`；
7. 复用唯一内置 Browser 标签；如果真实出现登录/2FA/同意页，再请用户处理该一步并于同一 session 重探。

tunnel 选择、setup、project/connector/workspace 错配都不是“登录问题”，必须按各自状态修复。当前 Codex route 不生成中性校准图，也禁止用 Computer Use 操作 ChatGPT；Computer Use 只是 Ardot/微信 UI 的末级降级。

## 5. Browser 下载的 create-once 摄取

Browser 完成 original download 后，立即用它刚返回的绝对路径运行报告中的 `ingestion_command_template`。最小调用形状为：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/ingest_browser_download.py" \
  /ABSOLUTE/PATH/RETURNED/BY/HOST.png \
  "$ORG_WECHAT_SESSION_ROOT/migration-probes/NONCE/raw/provider-original.png" \
  --report "$ORG_WECHAT_SESSION_ROOT/migration-probes/NONCE/raw/download-ingestion.json" \
  --allowed-target-root "$ORG_WECHAT_SESSION_ROOT/migration-probes/NONCE" \
  --binding-nonce NONCE --binding-digest sha256:DIGEST \
  --provider-session-id CURRENT --provider-request-id CURRENT \
  --observed-download-id CURRENT --request-metadata-sha256 sha256:DIGEST
```

必须传入宿主观察到的 canonical real path。macOS 上 `/tmp` 通常是指向 `/private/tmp` 的 symlink，因而会被全路径 no-symlink 门禁正常拒绝；宿主返回 `/tmp/...` 时，先从宿主/系统获取其解析后的 `/private/tmp/...` 真实路径，不要在报告中手改路径来冒充观察值。

摄取器拒绝 symlink、非普通文件、目标逃逸和覆盖；流式复制后比对源/目标 SHA-256 与 bytes，并 create-once 写报告。它证明“当前轨迹标识绑定的观察路径与摄取字节”，不独立证明 Browser 事件真实性。

上例仅用于真实文章原图的摄取。启动与迁移阶段默认不生成 PNG，也不运行 `prepare_migration_probe.py`；默认报告中完全不发出 `run-migration-rgba-route-probe` 动作。只有为诊断旧版路线而显式给 `runtime_preflight.py` 传入 `--include-legacy-rgba-probe` 时，才会生成该动作；它始终是 `blocking=false` 的兼容诊断，不能授权读材料、创作或注册文章资产。正式透明文章资产仍可执行 `prepare_micro_cutout.py --acquisition-report ...` 做自身质量处理。

### 正式文章资产的二次宿主绑定

Runtime session binding 只绑定本会话路由，不能为后续每张正式图代签。正式 `article-micro` 必须新建 `org-wechat-provider-image-acquisition-v2`，将这次文章 request/download 反向绑到：

1. 已验证 installed release 的 registry census 字节；
2. census 选中 adapter 的当前 SHA/bytes 与该 adapter 声明的 `generation_route_id`；
3. 同 provider session 的 current-session runtime binding；
4. 每个真实 source attempt 的 canonical `org-wechat-article-image-request-v1` metadata；
5. 该 attempt 的 create-once Browser ingestion report 与 exact target raw SHA/bytes。

仓库进程能重算上述结构与字节链，但不能将它升级为独立宿主鉴真。current-session 的真实语义是 operator/harness-trusted operational acceptance：prepare/register/pack/ready 重验 runtime binding/request/ingestion/raw 与真实素材质量链，并固定 `host_attested=false`、`portable=false`。`live_provider_acquisition_authority(callback)` 仅保留为可选 veto policy。

另一条可携带路线由宿主签名 migration receipt，并由 `host.receipt.attest` 对 canonical acquisition core 签发 `org-wechat-provider-image-host-receipt-v1`，standalone CLI 只用仓库外受保护公钥库验签。core 明确排除后附 receipt 引用，避免哈希环；其余 runtime/attempt/ingestion/raw SHA 和 byte length 全部受签名。仓库不提供本地自签捷径，file JSON 也不能冒充 signer。缺少 signer 仅使 portable 升级不可用，不阻断完整当前会话链。完整 API 见 [provider-acquisition-authority.md](provider-acquisition-authority.md)。

## 6. migration 终态

### 当前会话（Codex Desktop 默认）

宿主组装 `org-wechat-runtime-session-evidence-v1`，精确绑定 binding nonce/digest、trusted bundle、installed release、registry digest、adapter/route 与 provider session ID；不包含 PNG、Alpha 或三底检查，再运行：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" \
  finalize-current-session-migration \
  "$ORG_WECHAT_SESSION_ROOT/migration-binding-UNIQUE.json" \
  "$ORG_WECHAT_SESSION_ROOT/migration-session-evidence-UNIQUE.json" \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --consumption-record "$ORG_WECHAT_SESSION_ROOT/migration-session-consumption-UNIQUE.json" \
  --output "$ORG_WECHAT_SESSION_ROOT/migration-session-final-UNIQUE.json"
```

成功结果是 `operational_ready: true`、`phase_ready: false`、`scope: same-host-session-only`。这是真实可执行的当前会话续跑合同，不是假绿；`phase_ready` 保留给宿主签名可携带结果。

### 宿主签名可携带迁移

只有 adapter 真实提供 `filesystem.access.lease` 与 `host.migration.finalize`、签名密钥在仓库进程外、宿主原子消费 nonce 时才运行：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/runtime_preflight.py" finalize-migration \
  "$ORG_WECHAT_SESSION_ROOT/migration-binding-UNIQUE.json" HOST-RECEIPT.json \
  --workspace-root "$ORG_WECHAT_RUNTIME_ROOT" \
  --trust-store /PROTECTED/HOST-MIGRATION-PUBLIC-KEYS.json \
  --consumption-record "$ORG_WECHAT_SESSION_ROOT/migration-consumption-UNIQUE.json" \
  --output "$ORG_WECHAT_SESSION_ROOT/migration-final-UNIQUE.json"
```

有效 receipt 才会产生 `phase_ready: true`。复制 JSON、重写时间、自报 host action、缺少签名或重放账本、任一路径/SHA/provider/session/request 不匹配都必须失败。

## 7. 阶段和路由

- `migration`：绑定 runtime/provider session；不执行中性 RGBA route probe，不因图像检测阻断读组织材料。
- `bootstrap`：仅验证 `ardot.create`，创建空白设计后用精确 file/root 重跑目标阶段。
- `authoring`：绑定生图、验图与 Ardot；如没有可嵌入水印载体，不因缺 secret 阻断。
- `delivery`：不再生图，绑定当前 Ardot root 与目标公众号。
- `full`：作者与交付的全链路。

Ardot 路由优先 MCP，其次 Browser，最后 Computer Use。微信草稿路由可优先已验证本地 API publisher，其次 Browser，最后 Computer Use；正式发布还必须满足报告 `publication_routes` 矩阵的独立权限与确认/回读门禁。当前 `wechat_publisher.py` 只在执行时读取 `WECHAT_ACCESS_TOKEN` 和 `WECHAT_APP_ID`，未实现 AppSecret 换 token；凭据不进 registry/profile/report。UI 路由要先打开无 token 入口，只在实际登录墙出现时请用户登录，随后在同一 session 重读精确账号/file/root。

Ardot MCP 诊断必须分四层：`configured` 只来自脱敏本机配置；
`model_visible` 只来自当前任务 registry；`live_authenticated` 和
`target_access_verified` 只来自同会话精确 target 读取；
`last_mutation_outcome` 只来自单次 provider 确定响应。本机显示 OAuth 不会自动
升级任何后三层。配置正常但当前任务未注入时，唯一恢复是重载/新开
Codex 任务并重建 census。`create_design` 的超时、5xx 或截断响应必须保留
`create-unknown`，先按预绑 nonce/唯一标题只读对账，禁止盲目重试。

微信 API 路由先运行 `wechat_publisher.py preflight-account`，只读调用
`draft/count` 和 `material/get_materialcount`，并写出
`wechat-account-readonly-preflight-v1` create-once 报告。它固定
`mutations_attempted: 0`，只证明当前凭据/账号可读；上传、草稿写入、UI 回读和
发布仍是四个后续独立门禁。

可表达的 MCP 依赖已在三个 `agents/openai.yaml` 中声明；Browser、Computer Use、C2C、Node、本地 processor、API 凭据、host signer/lease 不是 MCP，统一由 [`runtime/non-mcp-dependencies.json`](../runtime/non-mcp-dependencies.json) 与 census/profile 管理。

机器合同见 [`runtime/host-registry-census-contract.json`](../runtime/host-registry-census-contract.json)、[`runtime/migration-host-receipt-contract.json`](../runtime/migration-host-receipt-contract.json) 和 [`runtime/adapters/codex-desktop.json`](../runtime/adapters/codex-desktop.json)。
