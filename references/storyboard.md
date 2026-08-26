# 叙事分镜

先把文章拆成 4–10 个“读者此刻需要理解什么”的章节，再选组件。不要把每个 JSON block 当作一张卡。

每个 `storyboard.chapters[]` 需要：

- `id` 和 `label`；
- 一句 `thesis`；
- 一个可见的 `composition`，如图像主导开场、错落角色带、连续旅程、插图式结尾；
- `visual_intent`，说明主体如何进入、连接或结束页面；
- `density_intent`，说明本章采用紧凑、标准或留白强调，以及正文、图片和转场如何占据纵向空间；
- 不重复的 `block_indices`。

分镜必须覆盖除 references/footer 外的所有正文 block，并使用至少三种构图模式。运行：

```bash
python3 scripts/build_storyboard.py article.json \
  --output output/article-slug/storyboard-plan.json
```

只有 `ready_for_visual_kit: true` 时才能生图。后续每个插图都必须指定一个分镜章节。

默认使用 `compact-editorial` 密度。留白强调只能服务于 Hero、转场或结尾，不能让普通正文区出现超过本区高度 20% 的无意空洞。
