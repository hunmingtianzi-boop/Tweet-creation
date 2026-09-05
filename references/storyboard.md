# 叙事分镜

按材料决定章节数量（可以只有一章；4–10 章只是长文建议），先明确“读者此刻需要理解什么”的章节，再选组件。不要把每个 JSON block 当作一张卡。分镜批准后，再实现启动时确认的选项：`use_svg: true` 时选出有实际读者用途的 interaction opportunities（可为一个，2–3 个只是长文建议），`false` 时不选交互模块。一个机会必须对应一个读者任务和一组明确 source blocks，不按子卡或 SVG 数量计数。

每个 `storyboard.chapters[]` 需要：

- `id` 和 `label`；
- 一句 `thesis`；
- 一个可见的 `composition`，如图像主导开场、错落角色带、连续旅程、插图式结尾；
- `visual_intent`，说明主体如何进入、连接或结束页面；
- 结构化 `density_intent`：`mode` 为 `compact-editorial` / `standard` / `spacious-feature`，`target_content_occupancy_ratio` 必须落在该 mode 的区间，`intentional_whitespace` 为布尔值；为 true 时还必须填 `whitespace_reason`；
- 不重复且章内递增的 `block_indices`；章与章之间也必须严格保持 article block 顺序，不允许用视觉分镜悄悄重排文案。

分镜必须覆盖除 references/footer 外的所有正文 block，构图种类由内容决定，不要求凑满三种。运行：

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_storyboard.py" article.json \
  --output output/article-slug/storyboard-plan.json
```

只有 `ready_for_visual_kit: true` 时才能生图。后续每个插图都必须指定一个分镜章节。

交互计划独立于可选的 0–4 个视觉小组件。在动态 `interaction_plan.modules` 中记录 chapter、`source_block_indices`、reader-facing `purpose`、位置带和逐 transport instance 的原文/key/hash。位置带必须描述真实章节位置，不再要求固定 early/middle/late 配额，也允许同章多个任务；纯装饰动画、微插图和艺术字不能占名额。详见 [interaction-composition.md](interaction-composition.md)。

密度服从所选风格。`compact-editorial` 是建议，不是所有文章的默认硬门槛；留白与构图数字作为编辑建议。仍测量实际值、验证来源，并检查可读性与遮挡。
