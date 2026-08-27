# 组织视觉校准

泛化工作流不允许从“组织类型 + 配色”直接跳到整篇推文。先证明视觉方向能成立，再扩展全文。

## 操作

1. 完成组织调研，保持 `status: provisional`。
2. 运行 `build_visual_directions.py`，得到 2–3 条材质、构图和图像策略明显不同的方向。
3. 每条方向在全新的组织 Ardot 页面制作五个小样：Hero、章节、真实照片编排、微型插图、信息密度条。Hero 和章节小样同时对比表现型标题字，但必须使用可编辑 Ardot 文本节点。不得打开旧推文、旧 Ardot、旧截图或其他组织 pack。密度条必须包含一段正文、一组列表/步骤和一处图文衔接。
4. 若路线使用 AI 底图，先生成一个母版和 1–3 个同系列伴生变体；对比裸底图与叠字后的 390 px 小样，确认复制安全区、明暗连续和章节间风格一致。
5. 比较标题空间、编辑节奏、组织识别度、图文关系、信息密度与手机阅读。
6. 用户批准后，在 `organization.visual.calibration` 写入 `approved_routes`、Ardot `file_url`、`page_name`、`article_node_id`、默认 `density_mode`、底图 family ID、master asset ID、1–3 个 companion asset IDs、copy-safe zone、`typography` 策略/授权边界/批准手法/每篇上限和复核日期。
7. 组织资料同时确认后，才把 `organization.status` 改为 `confirmed`。

`calibration.status != approved`、当前 route 不在 `approved_routes` 或组织仍为 `provisional` 时，全文制作必须停止。

视觉质量只用本组织当前材料生成的校准条判断。历史文章、examples 和其他组织的 Ardot 文件均不是基准。

表现型标题字的完整字段和禁止项见 [expressive-typography.md](expressive-typography.md)。
