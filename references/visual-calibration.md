# 组织视觉校准

泛化工作流不允许从“组织类型 + 配色”直接跳到整篇推文。先证明视觉方向能成立，再扩展全文。

## 操作

1. 完成组织调研，保持 `status: provisional`。
2. 运行 `build_visual_directions.py`，得到 2–3 条材质、构图和图像策略明显不同的方向。
3. 每条方向在 Ardot 制作五个小样：Hero、章节、真实照片编排、微型插图、信息密度条。密度条必须包含一段正文、一组列表/步骤和一处图文衔接。
4. 若路线使用 AI 底图，先生成一个母版和 1–3 个同系列伴生变体；对比裸底图与叠字后的 390 px 小样，确认复制安全区、明暗连续和章节间风格一致。
5. 比较标题空间、编辑节奏、组织识别度、图文关系、信息密度与手机阅读。
6. 用户批准后，在 `organization.visual.calibration` 写入 `approved_routes`、Ardot `file_url`、`page_name`、`article_node_id`、默认 `density_mode`、底图 family ID 和复核日期。
7. 组织资料同时确认后，才把 `organization.status` 改为 `confirmed`。

`calibration.status != approved`、当前 route 不在 `approved_routes` 或组织仍为 `provisional` 时，全文制作必须停止。

Ocean 的质量基准是 [灵动丰富版 Ardot 文件](https://ardot.tencent.com/file/718358960022995)，页面 `招新推文｜灵动丰富版 2026`，文章根节点 `51:2`。它是 Ocean 的构图方法基准，不是其他组织的外观模板。
