# 公众号动态组件 A/B MVP

这个实验只测试一个变量：动态组件是否提升同一篇公众号文章的阅读体验。

- A：实验静态基线，生态路径和现场照片均为静态纵向排版。
- B：实验动态候选，生态路径使用无 ID、自触发 `begin="click"` 的 SVG/SMIL 揭开 + 横向滑动，现场照片使用 CSS 横向滑动画廊。
- 两版共用 `content.json`，文案、顺序、照片、色彩、字体和 390 px 宽度完全一致。
- B 版同时生成 `static-fallback-fragment.html` 与 `interaction-policy-report.json`。两份 HTML 都只是实验片段，固定声明 `delivery_eligible: false`；不得直接复制、导入或提交到公众号。

按主工作流当前计数口径，B 版包含 2 个创作层 semantic modules：`ecosystem-path` 是一个揭开 + 横滑复合组（4 个 SVG transport instances，但只算 1 个 module），`field-moments` 是一个照片横滑 module。这里的 marker 数量不等于 module 数量。这个 MVP 的 `ardot-evidence.json` 早于当前三态/覆盖列表 schema，只用于 transport 回归；缺少完整 `closed/open/fallback` 覆盖证据的节点不能作为新文章最终编译的证明。

构建：

```bash
python3 experiments/interaction-mvp/build_experiment.py
```

查看：打开 `output/compare.html`。桌面端会左右并排；窄屏会上下排列。

采用实验结果：

1. 只把通过 A/B 的互动语义和状态设计带回当前 Ardot article root；不得把实验 HTML 当版式源。
2. 在 Ardot 中完成关闭/打开/fallback 三态与逐章图层，冻结 handoff schema v5。
3. 通过 `validate_transport_fidelity.py` 和 `compile_wechat.py --transport-fidelity` 生成唯一可投递的 `wechat.html`。
4. 保存并重新打开草稿，逐章回读 SVG/SMIL 结构、资源字节与 390 px 截图，再做目标账号 iOS/Android 真机验证。

Ardot 编辑源：<https://ardot.tencent.com/file/719663191870370>

- A 画板：`4:1`
- B 画板：`4:2`
- 轻触展开关闭态：`4:3`
- 轻触展开打开态：`4:4`
- 横滑照片条目：`4:5`
- 静态路径条目：`4:6`

截图、节点和哈希证据见 `ardot-evidence.json`。这些旧证据只能支持互动策略回归，不能替代当前 handoff v5 的 Ardot 图层、状态 export 与微信草稿回读。

验收：

```bash
python3 -m unittest tests.test_interaction_mvp -v
```

实验到正式链路：

1. 在 Ardot 的同一文件内维护 A、B 两个 390 px 画板和交互组件的关闭/展开状态。
2. 本脚本只从同一个 `content.json` 生成 A/B `candidate-fragment.html`，用于比较互动策略，不创建导入助手或交付文件。
3. 选定策略后，在当前 Ardot root 重建并冻结实际章节、文字、资产、几何与交互状态；禁止从候选片段反向拼装最终版。
4. frozen compiler 生成待投递 HTML 后，按 `wechat-svg-smil-self-v1` 回读 fallback key/hash、`<set>` / `<animateTransform>`、严格 `begin="click"` 与 SMIL 结构签名。
5. 回读只证明结构存活；还必须匹配目标账号、策略版本、有效期以及 iOS/Android 微信版本的真机证据。
6. 回读失败、能力档案缺失/过期/不匹配或任一真机失败时，使用同一 frozen handoff 的静态 fallback 更新同一草稿，不在发布时逐段手调，也不新建重复草稿。

实测回归证据位于 `tests/fixtures/wechat-capability/`：微信保存后保留 inline SVG、`<set>`、`<animateTransform>`、自身 `begin="click"`、微信 CDN SVG 图片和 CSS 横滑，但删除 `id`。因此 `<details>`、JavaScript、任何 transport `id` 和 `begin="foo.click"` 已永久从本 workflow 禁用。fixture 的移动端状态仍为 `pending`，不得解释为全局兼容认证。

本实验不使用旧推文截图、旧 PDF 排版或旧 Ardot 画板作为视觉参考；PDF 仅用于事实和文案提取，照片仅来自用户提供的数据包。
