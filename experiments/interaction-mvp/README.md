# 公众号动态组件 A/B MVP

这个实验只测试一个变量：动态组件是否提升同一篇公众号文章的阅读体验。

- A：现有基线 workflow，生态路径和现场照片均为静态纵向排版。
- B：动态 workflow，生态路径使用无 ID、自触发 `begin="click"` 的 SVG/SMIL 揭开 + 横向滑动，现场照片使用 CSS 横向滑动画廊。
- 两版共用 `content.json`，文案、顺序、照片、色彩、字体和 390 px 宽度完全一致。
- B 版同时生成 `wechat-fallback.html` 与 `interaction-policy-report.json`。保存回读或目标客户端能力档案不通过时，投递器必须更新同一草稿为与 A 同信息量、语义哈希匹配的静态表达。

按主工作流当前计数口径，B 版包含 2 个创作层 semantic modules：`ecosystem-path` 是一个揭开 + 横滑复合组（4 个 SVG transport instances，但只算 1 个 module），`field-moments` 是一个照片横滑 module。这里的 marker 数量不等于 module 数量。这个 MVP 的 `ardot-evidence.json` 早于当前三态/覆盖列表 schema，只用于 transport 回归；缺少完整 `closed/open/fallback` 覆盖证据的节点不能作为新文章最终编译的证明。

构建：

```bash
python3 experiments/interaction-mvp/build_experiment.py
```

查看：打开 `output/compare.html`。桌面端会左右并排；窄屏会上下排列。点击右上角“导入微信公众号”，进入自助导入助手。

自助导入：

1. 保持本地预览服务运行，打开 `output/import-assistant.html`。
2. 点击“复制标题”，粘贴到公众号标题。
3. 点击“复制 B 动态正文（含照片）”，再点进公众号正文区域按 `⌘V`。
4. 保存后回读 SVG/SMIL 结构，再在 iOS/Android 手机预览中测试轻触和横滑；手工 MVP 可改用“复制静态降级正文”，正式投递器则更新同一草稿。
5. 自行选择封面，保存草稿。正式群发始终单独确认。

Ardot 编辑源：<https://ardot.tencent.com/file/719663191870370>

- A 画板：`4:1`
- B 画板：`4:2`
- 轻触展开关闭态：`4:3`
- 轻触展开打开态：`4:4`
- 横滑照片条目：`4:5`
- 静态路径条目：`4:6`

截图、节点和哈希证据见 `ardot-evidence.json`。Ardot 维护视觉源和组件状态，浏览器/微信 HTML 维护运行时交互；两者通过组件名和 `data-component` 对齐。

验收：

```bash
python3 -m unittest tests.test_interaction_mvp -v
```

发布链路 MVP：

1. 在 Ardot 的同一文件内维护 A、B 两个 390 px 画板和交互组件的关闭/展开状态。
2. 导出视觉切图；本脚本从同一个 `content.json` 组装两版 HTML。
3. A 直接进入微信素材上传/草稿创建。
4. B 先上传图片，再提交动态候选 HTML，随后按 `wechat-svg-smil-self-v1` 回读 fallback key/hash、`<set>` / `<animateTransform>`、严格 `begin="click"` 与 SMIL 结构签名。
5. 回读只证明结构存活；还必须匹配目标账号、策略版本、有效期以及 iOS/Android 微信版本的真机证据。
6. 回读失败、能力档案缺失/过期/不匹配或任一真机失败时，更新同一草稿为 `wechat-fallback.html`，不在发布时逐段手调，也不新建重复草稿。

实测回归证据位于 `tests/fixtures/wechat-capability/`：微信保存后保留 inline SVG、`<set>`、`<animateTransform>`、自身 `begin="click"`、微信 CDN SVG 图片和 CSS 横滑，但删除 `id`。因此 `<details>`、JavaScript、任何 transport `id` 和 `begin="foo.click"` 已永久从本 workflow 禁用。fixture 的移动端状态仍为 `pending`，不得解释为全局兼容认证。

本实验不使用旧推文截图、旧 PDF 排版或旧 Ardot 画板作为视觉参考；PDF 仅用于事实和文案提取，照片仅来自用户提供的数据包。
