# 正式文章生图的采集与保证边界

正式 `article-micro` 使用 `org-wechat-provider-image-acquisition-v2`。每次采集必须绑定：

- 已验证 installed release 的 registry census；
- census 所选 adapter 的当前字节与 `generation_route_id`；
- 同 provider session 的完整 migration result；
- 每次 native/fallback attempt 的 canonical request metadata；
- Browser 返回路径经 `ingest_browser_download.py` 生成的 create-once report；
- ingestion target 的当前 raw SHA-256/byte length，以及后续 RGBA8/Alpha/边缘/紧裁验收。

四类正式微组件还有文章级唯一性门禁：slot 必须是 `kit.<role>`，四个 accepted raw SHA、provider request ID、acquisition binding 与 derivative SHA 必须各自四向唯一。同一原图不能靠复制、换路径或多次裁切充当四类组件。

旧 v1、任意 route 名、复制的 host trace，或 JSON 里自写的 `passed` / `authorized` / `callback` 字段一律拒绝。

## 当前会话：`current-session-operator-harness-trusted`

完整当前会话 migration、canonical request、create-once ingestion、exact raw bytes 和 RGBA 像素链通过后，v2 采集可以 operational accept，不需要宿主 signer 或 Python callback。该档位必须明示：

```json
{
  "authority_mode": "current-session-operator-harness-trusted",
  "assurance": "operator-harness-trusted-current-session",
  "operationally_accepted": true,
  "authorized": false,
  "host_attested": false,
  "portable": false
}
```

这是可运行的当前会话合同，不是密码学证明。操作者或同权限 Python 进程可以伪造普通 callback，因此不得用“不可序列化”、`ContextVar` 或类型接口宣称宿主鉴真或不可伪造。

`live_provider_acquisition_authority(callback)` 保留为兼容 API，但语义只是可选 trusted-harness policy hook：

- 返回 `True`：不 veto，保证等级完全不变；
- 返回 `False` 或抛异常：阻断当次采集；
- 无论回调如何返回，都不得产生 `host_attested=true`、`portable=true` 或签名宣称。

prepare、register、pack validate 与 `ready_for_layout` 会分别重算整条 migration→request→ingestion→raw→derivative 链。脱离当前会话时不能将这档宣称为可携带审计。

## 可携带：`portable-signed`

强保证路线不变：宿主先完成 portable migration 并提供有效的 migration Ed25519 receipt，再用 `host.receipt.attest` 对 `org-wechat-provider-image-authority-challenge-v1` 签发独立 provider receipt。两份签名都必须通过仓库外、root-owned、非 symlink、当前进程不可写的公钥库验证。

provider receipt 签名 canonical acquisition core；core 仅排除后附的 `portable_host_receipt` 引用，避免 report→receipt→report 哈希环，其余 route/session/request/ingestion/raw SHA 与 byte length 全部受签名。

Standalone CLI 可以验证这一档：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/prepare_micro_cutout.py" \
  RAW_PNG DERIVED_PNG \
  --role ROLE \
  --article-id ARTICLE_ID \
  --asset-slot-id kit.ROLE \
  --prompt-sha256 sha256:PROMPT_SHA \
  --generation-route chatgpt-web-image-route-v1 \
  --acquisition-report ACQUISITION_V2.json \
  --portable-trust-store /PROTECTED/PUBLIC-KEYS.json \
  --require-native-alpha \
  --report DERIVATION_REPORT.json
```

`--portable-trust-store` 只验签，不会签发 receipt；仓库不提供测试密钥或本地自签放行捷径。任意一份签名、时效、binding、重放保护或信任库验证失败，都必须 fail closed，且不能降级到当前会话模式。

## 结论边界

- 完整当前会话链可用于正常 authoring/full；缺少 callback 或 signer 本身不是阻断。
- callback 只是 veto policy，不是证明。
- 完整链不足、callback 否决/异常、旧 v1、伪 route、raw/像素篡改仍会阻断。
- 只有两份受保护 Ed25519 receipt 都有效时，才可声称 host-attested 且 portable。
