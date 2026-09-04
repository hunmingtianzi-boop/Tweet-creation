# 叙事分镜

先把文章拆成 4–10 个“读者此刻需要理解什么”的章节，再选组件。不要把每个 JSON block 当作一张卡。分镜批准后，再实现启动时确认的选项：`use_svg: true` 时从不同章节选出 2–3 个 interaction opportunities，`false` 时不选交互模块。一个机会必须对应一个读者任务和一组明确 source blocks，不按子卡或 SVG 数量计数。

每个 `storyboard.chapters[]` 需要：

- `id` 和 `label`；
- 一句 `thesis`；
- 一个可见的 `composition`，如图像主导开场、错落角色带、连续旅程、插图式结尾；
- `visual_intent`，说明主体如何进入、连接或结束页面；
- 结构化 `density_intent`：`mode` 为 `compact-editorial` / `standard` / `spacious-feature`，`target_content_occupancy_ratio` 必须落在该 mode 的区间，`intentional_whitespace` 为布尔值；为 true 时还必须填 `whitespace_reason`；
- 不重复且章内递增的 `block_indices`；章与章之间也必须严格保持 article block 顺序，不允许用视觉分镜悄悄重排文案。

分镜必须覆盖除 references/footer 外的所有正文 block，并使用至少三种构图模式。运行：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_storyboard.py" article.json \
  --output output/article-slug/storyboard-plan.json
```

只有 `ready_for_visual_kit: true` 时才能生图。后续每个插图都必须指定一个分镜章节。

交互计划独立于可选的 0–4 个视觉小组件。在动态 `interaction_plan.modules` 中记录 chapter、`source_block_indices`、reader-facing `purpose`、位置带和逐 transport instance 的原文/key/hash。2 个模块使用 early + middle，3 个模块再增加 late；纯装饰动画、微插图和艺术字不能占名额。详见 [interaction-composition.md](interaction-composition.md)。

默认使用 `compact-editorial` 密度。留白强调只能服务于 Hero、转场或结尾，不能让普通正文区出现超过本区高度 20% 的无意空洞。
