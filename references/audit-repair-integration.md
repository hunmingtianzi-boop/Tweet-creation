# 审计修复后的执行连接

代码/单元测试、真实浏览器渲染、Ardot 实际导出、微信保存回读、手机交互是五种不同证据。
不要把前一种的成功写成后一种完成。这里的新增适配器仍需真实平台 forward test，不能声称兼容所有 Ardot 节点或所有微信客户端。

## 启动选择与依赖

先询问小组件数量、是否 SVG、风格和是否生成底图；允许用户暂缓决定。理解原始材料后，在分镜审批中一次确认具体选择。无需为了一个短通知凑四章或凑两个交互。

运行目标文件增加 `generation`，内容例如：

```json
{"micro_component_count": 0, "generate_backgrounds": false, "generate_cover": false}
```

这三个字段也单独保存为 generation-plan.json，传给 `release_skills.py clone-check --generation-plan ABSOLUTE_FILE`。
它们必须与本次正式文章选择、封面计划一致。全部关闭时不要求 ImageGen/ChatGPT/C2C 生图服务；仍保留 Ardot 和按所选阶段需要的微信服务。未传选择时保守地保持原来的生图预检，不能静默推断已关闭。
没有选中 RGBA 路由时，不调用 provider migration finalizer；它只负责真实生图会话的绑定，不能成为纯原生排版的前置条件。

## Ardot 原始节点 → 冻结交接

新增 `ardot_capture_adapter.normalize_capture`，由现有受保护导出入口调用：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/export_ardot_handoff.py" RAW_CAPTURE.json \
  --bindings SEMANTIC_BINDINGS.json --output NEW_HANDOFF_DIRECTORY
```

RAW_CAPTURE 来自当前会话实际 `batch_read` 结果，包含 `source: ardot-batch-read-capture-v1`、`file_id`、`root_node_id`、`captured_at` 和完整 `root`。读取 resolved instances/variables；遇到压缩 children、缺少几何/样式继续读节点，不能手填。

SEMANTIC_BINDINGS 包含 article（含已确认 preferences）、assets（实际导出下载的路径和 SHA）、font_mapping 和 chapters。章节绑定 section_node_id、chapter_id、reference_screenshot、background_layer、visible_text_nodes、decorations、photos、interaction。绑定只指定语义与节点/资产 ID，不重写文字、几何、样式或状态树哈希。文本使用 node_id/tag/semantic_role；图片使用 source_node_id/asset_id；交互另外指定 state_node_ids 的 closed/open/fallback 节点，以及实际状态导出的 SVG 与 fallback 资产。

转换器从原始节点计算这些属性，拒绝未覆盖的可见叶子、文字底图、未解析字体/行高、压缩节点、暂不支持的效果/裁切/变换。当前支持的范围是 resolved numeric geometry、纯色原生文字、独立导出背景/图片和明确的状态节点。复杂设计先在 Ardot 里改成受支持表达，不允许另写 HTML 冒充原样导出。

资产仍由实际 Ardot export_nodes/download_source_media 工具产生；本地转换器不具备登录/下载能力，也不签发宿主真实性证明。新 handoff 保存 raw capture、生产选择和完整 transport 的哈希绑定。用户修改 Ardot 后必须重新冻结；改变生产选择还需重新确认。

## 响应式排版与实际验收

文字字号/字距与图层统一按章节容器缩放：`container-type:inline-size` + `cqw`。单位语义参见 [CSS 容器相对长度规范](https://www.w3.org/TR/css-contain-3/#container-lengths)。这是候选传输方案，不是微信兼容性承诺。客户端清洗掉这些样式时必须报告失败，不能静默回到混合比例和固定字号。

`scripts/measure_wechat_viewport.js` 是宿主中的只读浏览器诊断，**不能放入公众号 HTML**。保存并重新打开同一草稿，在 320、390、430px 的实际文章容器各采集一次完整截图和 text_layers。固定外部浏览器 viewport 不等于改变了文章容器宽度，必须检查真实 bounding rect。

生成 `source: wechat-render-viewport-review-v1` 的 review，绑定 target_account_ref、draft_id、实际保存内容的 content_sha256；samples 含 width_px、captured_at、真实 capture_event_id、screenshot 的 path/sha256 和测量脚本返回的 text_layers。将它传给 `wechat_publisher.py capture-readback --viewport-review FILE`。验证器逐节点检查字号、字距、宽高随容器缩放和 scroll 溢出，缺任何宽度不能完成最终回读验收。

截图比对允许真正相同的像素；采集时间、来源、账号/草稿和文件身份另外核验。全图平均误差与最差局部块同时检查；阈值只是回归容差，不是审美评分。

## 可执行的动态草稿路径

1. 上传绑定资产，保存静态等价草稿，取得现有草稿 ID。
2. `compile_wechat.py --session-draft --interaction-probe` 编译动态候选，用 save-draft 更新同一草稿，不创建第二篇；不发表。
3. 回读真实 HTML，确认交互结构；编辑者在 iOS 和 Android 实际点击/滑动并检查关闭、打开、静态等价内容。
4. 保留现有 mobile profile v2 字段与真实截图。将 assurance_scope 设为 `current-session-editor-reviewed`，签名相关字段为 null，增加 editor_review：reviewed_by、真实 review_event_id、scope=`exact-draft-and-both-mobile-interactions`。这是一份有文件绑定的人审记录，不是程序独立认证。
5. 当前会话编译时传 `--session-draft --mobile-profile FILE --interaction-readback SAVED_HTML --accept-editor-mobile-review`，save-draft 和 capture-readback 也传 `--accept-editor-mobile-review`。各处均显式接受人审后才能使用此路由。只有已有草稿可更新动态内容。
6. 再次保存回读及多宽度验收；交付草稿地址。发表/群发仍走独立的明确确认与发布授权，不因人审 profile 获得权限。

若没有真实手机验收，继续停留在 interaction-probe，不宣称动态功能认证完成。宿主回调和 portable-signed 保持独立可选路径；不要在普通 Python 中伪造回调，或为正常人审安装不存在的 signer。

## 回归边界

2026-09-05 本地修复验证：首轮全量跑了 404 项；当时的 8 项失败涉及旧文档断言、release 字节漂移与新增回读字段，随后分别修正和复验。后续新增原始节点→冻结端到端与单交互用例，当前收集为 406 项，不把收集数宣称为最终全量通过数。最终相关套件覆盖 release/安装入口、runtime preflight、传输、导出器、发布器，以及简洁路线与单交互回归；真实 Chrome 测试覆盖 320/390/430px。真实 Ardot、微信保存清洗与双端点击未在本次仓库修复中执行。

本地单元测试使用显式 synthetic/mock 数据。`tests/browser_responsive_probe.cjs` 只测实际浏览器在生成测试 HTML 上的布局，不打开真实服务。真实 Ardot 导出、目标账号清洗和双端交互必须在交付时补齐，不能由 fixtures 代签。
