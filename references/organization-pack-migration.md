# 跨公众号 organization pack 迁移

迁移目标是复用流程语义，不复制另一个公众号的外观。新公众号始终建立新目录、新 organization ID、新 Ardot variable mode 和新视觉校准。

## 可以迁移

- semantic component IDs 与文章 block 职责；
- 事实、来源、资产、Ardot 和投递适配的文件分层；
- 390 px、开放式构图、compact-editorial、截图证据与草稿投递门槛；
- Logo/二维码权限边界和发布确认规则。

## 必须重建

- 组织定位、受众、voice、personality、content pillars；
- tokens、motifs、avoid rules、route 与 component variants；
- 本公众号的真实照片 registry；
- 本轮 source-zero 视觉输入与隔离声明；
- Ardot calibration page、variable mode 和 route benchmark；
- generated background family 的 master/companions；
- 每篇文章四枚专属微组件及其 Ardot component nodes；
- 每篇文章 visual review v2。

## 禁止复制

- 旧推文截图、长图、PDF 预览或 Ardot 页面作为新组织视觉参考；
- 另一个组织的 generated assets、background family、component variant 外观或效果样稿；
- 旧文章的 `approved`、截图、密度数字或 component node ID；
- Logo、二维码、照片和品牌色的跨组织替换式复用。

## 迁移步骤

1. 运行 `orgs.py init` 建立空 pack，不复制已有 pack。
2. 只登记本轮原始材料到 `sources.json`；填写 `provenance.visual_input_source_ids` 和四类 `excluded_visual_reference_kinds`。
3. 从组织证据推导 2–3 条路线，生成五项 calibration strip；先校准再全文。
4. 生成并登记同一家族的 master 与 1–3 个 companion；两类资产分别标记 `background_variant`。
5. 将批准的 Ardot file/page/root、density mode 和 background family 写回 organization pack，状态才可改为 `confirmed`。
6. 为当前文章生成四枚不同微组件，逐张运行 Alpha 检查，注册为 `article-micro`，再在 Ardot 建原生组件并回写 node 证据。
7. 完成文章后从同一 article root 导出五类 390 px 截图，生成 visual review v2，最后运行 `compile_wechat.py --check`。

任何一步若需要查看旧视觉来“找感觉”，应停止并回到本轮原始材料、组织物件、真实照片和校准条，而不是把旧风格解释为品牌事实。
