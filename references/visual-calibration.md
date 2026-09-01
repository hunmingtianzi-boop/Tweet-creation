# 组织视觉校准

泛化工作流不允许从“组织类型 + 配色”直接跳到整篇推文。先证明视觉方向能成立，再扩展全文。

## 操作

1. 完成组织调研，保持 `status: provisional`。
2. 运行 `build_visual_directions.py`，得到 2–3 条材质、构图和图像策略明显不同的方向。默认全部是 source-zero。只有用户明确选择时，才允许其中一个方向携带经审核的 `route.style_grammar`；风格选项与契约见 [style-options.md](style-options.md)。
3. 每条方向在全新的组织 Ardot 页面制作五个小样：Hero、章节、真实照片编排、微型插图、信息密度条。Hero 和章节小样同时对比表现型标题字，但必须使用可编辑 Ardot 文本节点。每个候选艺术字 recipe 至少组合两种非字体替换手法与两个可编辑图层；只换字体不得进入批准清单。source-zero 方向不得打开旧推文、旧 Ardot、旧截图或其他组织 pack；preset 方向只能读取抽象 grammar 与 SHA，不能重新打开最初参考或读取其内容素材。密度条必须包含一段正文、一组列表/步骤和一处图文衔接。
4. 若路线使用 AI 底图，先生成一个母版和 1–3 个同系列伴生变体。整个 family 只能选择 `light` 或 `dark` 一种 surface mode；不得出现一章黑底、一章白底。用归一化 `x/y/width/height` 标记 copy-safe zone，声明正文十六进制颜色、最低对比度 `4.5`、复制区最大亮度标准差 `0.10`。注册已经合成到最终阅读面的不透明 PNG 后运行 `python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" "$ORG_WECHAT_RUNTIME_ROOT/scripts/orgs.py" validate PACK`，必须由像素检查确认安全区近纯色、文字对比和 family 色调连续；带透明像素的底图因无法确定下方阅读面而失败。不能用提示词或肉眼口头声明代替。
5. 比较标题空间、编辑节奏、组织识别度、图文关系、信息密度与手机阅读。若候选使用 style grammar，同时检查 grammar fidelity 与 non-copy boundary：色彩运动/材质/层叠可以相似，文字、照片、Logo、具体版式、组件几何和 artwork 必须不同。
6. 用户批准后，在 `organization.visual.calibration` 写入 `approved_routes`、Ardot `file_url`、`page_name`、`article_node_id`、默认 `density_mode`；底图写入 family ID、master asset ID、1–3 个 companion asset IDs、surface mode、结构化 copy-safe zone、正文颜色、最低对比度和复制区方差上限；`typography` 写入策略、授权边界、至少两个 construction recipes、每篇上限和复核日期。
7. 组织资料同时确认后，才把 `organization.status` 改为 `confirmed`。

`calibration.status != approved`、当前 route 不在 `approved_routes`、组织仍为 `provisional`、底图像素检查失败，或表现型字体 recipes 不完整时，全文制作必须停止。

视觉质量只用本组织当前材料生成的校准条判断。历史文章、examples 和其他组织的 Ardot 文件均不是基准。已审核 preset 只是一个可选的抽象语法输入，不是现成模板；`prismatic-paper-editorial` / 绚烂纸本也不得成为所有组织的全局默认。

表现型标题字的完整字段和禁止项见 [expressive-typography.md](expressive-typography.md)。
