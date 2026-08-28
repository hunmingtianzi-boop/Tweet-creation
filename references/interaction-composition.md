# 动态组件构图与计数

主工作流在常规 4–10 章公众号文章中，默认规划 2–3 个 `interaction module`。这是创作层预算，不代表目标公众号一定启用动态 payload；投递层仍以静态等价版为默认，只有目标账号当前有效的保存回读与 iOS/Android 真机能力档案同时通过，才可保留动态候选。

## 两种计数单位

- `interaction module`：一个连续版面区域、一个读者任务、一个静态等价区域，是每篇 2–3 个的计数单位。
- `transport instance`：投递层的一个实际触发实例，必须独立拥有 `fallback_key` 与 `sha256:<64 hex>` 语义哈希。

四个并列部门各自点击展开，是 1 个 `tap-reveal-group` module、4 个 SVG transport instances；横向照片组整体是 1 个 module、1 个 swipe instance。模块数量只取 `modules.length`，绝不取 SVG 数、卡片数或 `instances.length`。

四枚文章专属微型插图、2–4 处表现型字体、纯装饰动画、无读者任务的动效都不计入 interaction module。

## 什么内容够资格

每个 module 必须完成一种明确任务：

- 按需展开并列对象的详情；
- 浏览一组有顺序或比较关系的内容；
- 逐步理解流程、指标、前后状态或因果关系。

不为凑数拆分同一语义区域，不重复正文，不把必要事实藏在点击后，不给普通段落加无意义触发。默认最多 3 个；第三个必须承担与前两个不同的读者任务。

2 个 module 必须分布在 `early` 与 `middle`，3 个必须分布在 `early`、`middle`、`late`，并绑定不同 storyboard chapters。位置带由批准后的 chapter 顺序按三等分计算，不接受把晚段 chapter 手写成 `early`。交互区域仍受开放式构图与 20% 方框上限约束，不能连续堆成组件墙。

## `interaction_plan` 两阶段门槛

装配前校验创作计划：

- `authoring_mode: dynamic-default` 时，`target_module_count` 与 `modules.length` 都必须是 2 或 3；
- 每个 module 绑定一个不同的 storyboard chapter、该章内的 `source_block_indices`、具体 `purpose` 和位置带；
- 每个 transport instance 的 `source_texts` 必须来自这些 blocks；
- 每个 instance 使用唯一 `id`、`fallback_key` 和由有序原文计算的 `sha256:<64 hex>`；
- `candidate_modes` 只允许 `svg-smil-self` 与 `horizontal-swipe`。复合揭开横滑组可以同时声明两者。

最终编译再校验证据：

- 当前 Ardot `article_root_node_id` 与 `ardot_revision_hash`；
- 每个 module 的原生可编辑 `closed`、`open`、`fallback` 三态；
- module 作为一个原生 group component 时，`covered_instance_ids` 与 `covered_semantic_hashes` 必须按顺序完整等于该 module 的 transport instances；组件内的 `revision_hash` 必须等于文章计划 revision；
- 三态使用不同 node，分别有本地 390 px PNG 与匹配的 SHA-256；
- `closed` 与 `open` 截图不能相同；
- module 必须属于当前组织的 Ardot 文件。

这两个阶段不能合并：装配清单必须先告诉 Ardot 要创建什么；只有文章装配完成后，才能取得当前 revision 的三态截图证据。

## 允许的实现

- 无 ID、元素自身 `begin="click"` 的 inline SVG `<set>` / `<animateTransform>`；
- 带可见滑动提示的 inline CSS 横向滚动；
- 每个 transport instance 都有信息等价静态实例及相同 key/hash。

禁止 JavaScript、`details/summary`、任何 transport `id`、跨 ID timing、fragment reference、`<use>`、`foreignObject` 与未探测 SMIL。

## 静态例外

原始材料确实只有 0–1 个合理交互机会，或用户明确要求静态时，可使用 `authoring_mode: static-exception`。必须记录：

- `category`：`user-requested-static`、`short-utility-notice`、`editorially-unsuitable` 或 `accessibility-priority`；
- 至少 12 字的具体 `reason`；
- `confirmed_by: user` 或 `editor`。

目标公众号暂无动态能力档案，不是跳过创作计划的理由：仍可设计 2–3 个 module，并在投递时选择它们的信息等价静态版。

## 生产边界

创作层默认动态候选，生产层默认静态安全。`compile_wechat.py` 的静态输出与 `interaction_authoring.module_count` 可以同时成立；语义模块数量不得写入 `wechat_interaction_policy.py`，因为 transport marker 数量与创作层 module 数量不同。

保存草稿后的结构回读只证明标签与属性未被清洗。只有目标账号、策略版本、iOS/Android 微信版本、有效期和真机证据全部匹配，`wechat-svg-smil-self-v1` 才能选择动态 payload；否则更新同一草稿为静态等价版。
