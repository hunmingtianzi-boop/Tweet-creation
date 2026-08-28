# 公众号动态组件 A/B MVP

这个实验只测试一个变量：动态组件是否提升同一篇公众号文章的阅读体验。

- A：现有基线 workflow，生态路径和现场照片均为静态纵向排版。
- B：动态 workflow，生态路径使用轻触展开 + 横向滑动，现场照片使用横向滑动画廊。
- 两版共用 `content.json`，文案、顺序、照片、色彩、字体和 390 px 宽度完全一致。
- B 版同时生成 `wechat-fallback.html`。当微信草稿回读或目标客户端不支持交互结构时，自动回退为与 A 同信息量的静态表达。

构建：

```bash
python3 experiments/interaction-mvp/build_experiment.py
```

查看：打开 `output/compare.html`。桌面端会左右并排；窄屏会上下排列。

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
4. B 先上传图片，再提交动态候选 HTML，随后回读草稿正文并做标签、字符数和关键文案检查。
5. 回读失败、交互标签被清洗或真机抽检失败时，提交 `wechat-fallback.html`，不在发布时临时手调。

本实验不使用旧推文截图、旧 PDF 排版或旧 Ardot 画板作为视觉参考；PDF 仅用于事实和文案提取，照片仅来自用户提供的数据包。
