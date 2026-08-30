# Tweet Creation / Organization WeChat Studio

一套可迁移到不同组织和公众号的 Codex + Ardot 工作流。它把可编辑视觉组件、每个组织的品牌资料、单篇文章事实和最终微信投递适配分开管理。

不是“换 Logo 和颜色”的统一模板。新公众号会先建立组织包，再按该组织的受众、语气、视觉母题、文章类型和真实资料生成文章与文件资产。

## Source-zero 默认模式

新公众号只从本轮明确允许的组织资料、原始文案、品牌文件和真实照片开始视觉校准。工作流不会打开 `examples/`、另一组织的 pack、旧推文截图/PDF 或旧 Ardot 文件来“找风格”。仓库中的历史目录仅用于迁移兼容审计，不是视觉基准，也不参与测试。

机器门槛会检查 source-zero 输入清单、四类旧视觉排除项、同家族底图、四枚文章专属微组件、常规文章 2–3 个 semantic interaction modules 与逐实例 fallback hash、真实且非矩形卡片式 Alpha、Ardot 原生组件 node 证据、表现型字体的原生文本 node/style 证据，以及 schema-v3 的 390 px 截图、完整微组件实例清单与哈希节点属性证据。

## 能力

- 新组织调研与组织包初始化。
- 全文前先做 2–3 组 Ardot 小样校准，未批准路线不得开始整篇。
- 先写 4–10 章叙事分镜，再选组件和生图，避免 block 直接变卡片。
- 常规文章创作层默认规划 2–3 个语义动态模块；四张并列点击卡仍只算一个模块，逐卡 transport instance 分别保留静态 key/hash。
- 语气、品牌色、视觉路线、文章类型与事实来源建模。
- 按公众号与文章类型生成资产计划。
- 排版前强制生成四枚互不相同的文章专属浮动插图、章节转场、行内解释图和收尾视觉，并先做成 Ardot 小组件。
- 封面背景、章节视觉、透明/开放边缘插画、技术解释图与照片派生资产的生成和注册。
- AI 底图按“一个母版 + 1–3 个同系列变体”登记 family/variant/copy-safe zone，章节只改变裁切、透明度和局部构图，不随机换风格。
- Ardot 语义变量模式、原生组件、390 px 长文画板和分段视觉 QA。
- 由文章 JSON 生成可执行的 Ardot 装配清单。
- 默认开放式构图；闭合方框不超过正文区块的 20%、不连续，并至少保留三处不对称或越界视觉。
- 微组件图片不超过 72% 行宽、整体不超过 82%，四类角色左右错落并跨至少三个截图区段；含字组件禁止文字框/底板，主短句至少 22 px、1.35× 正文。静态微信适配也保留所有实际实例，不转成通栏卡片。
- 默认 `compact-editorial` 信息密度：15–17 px 正文、1.45–1.62 行高、轻微负字距、8–14 px 段距、24–40 px 章内主间隔，并校验内容占用率与最大无意空洞。
- 每个组织先校准表现型字体策略；单篇只在 2–4 个高影响位置使用可编辑 Ardot 标题字，正文保持紧凑可读，禁止 AI 字图。
- 16 类语义区块与隐藏的微信内联 HTML 投递适配。
- 事实来源、占位符、图片、Logo、二维码和微信安全格式校验。
- 固定 `wechat-svg-smil-self-v1` 交互能力：生成无 ID、自触发 SVG/SMIL 与 CSS 横滑候选，强制语义哈希静态回退、草稿结构回读和目标账号 iOS/Android 能力档案；任一门槛失败即降级同一草稿。
- 封面使用目标账号永久素材 `thumb_media_id` 并在草稿回读中验证，不与正文图片链路混用。
- 默认只生成草稿交付物，正式发布需要单独确认。

## 快速开始

安装确定性图片处理依赖：

```bash
python3 -m pip install -r requirements.txt
```

列出已有组织包：

```bash
python3 scripts/orgs.py list
```

初始化新公众号：

```bash
python3 scripts/orgs.py init new-account-id \
  --name "新组织或公众号名称" \
  --root organizations
```

先生成组织视觉校准方向（只做小样，不做全文）：

```bash
python3 scripts/build_visual_directions.py \
  organizations/new-account-id recruitment \
  --output output/new-account-id/visual-directions.json
```

待用户批准 Ardot 小样并回写 `organization.visual.calibration` 后，生成资产计划与文章叙事分镜：

```bash
python3 scripts/orgs.py asset-plan \
  organizations/new-account-id recruitment \
  --output output/new-account-id/recruitment-asset-plan.json
```

```bash
python3 scripts/build_storyboard.py article.json \
  --output output/new-account-id/article-slug/storyboard-plan.json
```

AI 生成的不透明底图或纯生成 raster 封面，在登记资产前先保留无水印母版并生成带来源水印的派生图。`PROVENANCE_WATERMARK_KEY` 必须来自仓库外的 secret store，以 `hex:` 或 `base64:` 表示至少 32 个随机字节；裸口令会被拒绝。如需 raw-ID 记录，先将 `PROVENANCE_WATERMARK_PRIVATE_ROOT` 设为一个已存在且位于所有 Git 仓库外的私密目录：

```bash
python3 scripts/provenance_watermark.py embed \
  organizations/new-account-id/assets/generated/background-master-raw.png \
  organizations/new-account-id/assets/derived/background-master-final.png \
  --key-epoch 1 \
  --report organizations/new-account-id/assets/derived/background-master-watermark.json \
  --private-record /secure/private-registry/background-master.json
```

上述成品、公开报告与私密记录都是 create-once：路径已存在时不会覆盖。嵌入时会强制重跑完整画面的 `390px-if-larger → JPEG Q75` 模拟；不承诺裁切、加边、旋转或透视变换后的截图检出。

只有公开报告为 `local_verified` 后才注册 final 文件，并同时绑定 pack 内的无水印母版与公开报告。登记、`orgs.py validate`、Ardot manifest 和微信编译都会用外部密钥重新鉴权，不信任 JSON 中自报的 `authenticated`：

```bash
python3 scripts/orgs.py register-asset organizations/new-account-id \
  --id visual.background-master --kind background --title "Background master" \
  --location assets/derived/background-master-final.png \
  --watermark-source assets/generated/background-master-raw.png \
  --watermark-report assets/derived/background-master-watermark.json \
  --origin generated-illustrative --style current-route --use recruitment \
  --visual-role illustrative-atmosphere \
  --background-family-id current-family --background-variant master
```

真实照片、Logo、二维码、透明小组件、SVG 和 QA 截图不进入 V1 水印链路。无水印母版的标准 `unwatermarked-masters/` 目录已被 Git 忽略，迁移时需从组织的私有资产库单独恢复。完整边界见[隐藏来源水印](references/provenance-watermark.md)。

在 `article.json` 写入 `interaction_plan`：常规文章使用 `dynamic-default`，2 个模块分布在 `early` + `middle`，3 个再增加 `late`。先绑定 chapter、source blocks 和逐实例语义哈希；当前 Ardot revision 的三态截图在全文装配后补齐。详见 [动态组件构图与计数](references/interaction-composition.md)。

为本篇文章生成小组件/小插图计划：

```bash
python3 scripts/build_visual_kit.py article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug/visual-kit-plan.json
```

逐张生图、验图，每张都必须绑定正文原句、具体主体/动作、分镜章节和构图职责。四张图分别运行像素级 Alpha、尺寸与角色宽高比检查：

```bash
python3 scripts/inspect_asset.py path/to/micro.png --role floating-spot
```

把四张图做成 Ardot 原生组件，将 component file/node/name 证据写回文章。只有 `ready_for_layout: true` 才生成 Ardot 装配清单：

```bash
python3 scripts/build_ardot_manifest.py article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug/ardot-manifest.json
```

按分镜章节完成 Ardot 长文装配后，截取 Hero、章节、证据、复杂区块和 CTA 五类实际节点，并导出全部 visual-kit instance inventory 与逐实例 node properties，建立独立 schema-v3 验收文件：

```bash
python3 scripts/build_visual_review.py visual-review.json --article article.json
```

把路径写入 `article.visual_review_file`，通过后才生成微信投递文件：

```bash
python3 scripts/compile_wechat.py article.json \
  --org organizations/new-account-id \
  --output output/new-account-id/article-slug \
  --check
```

详细流程见[使用说明](references/%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.md)，跨公众号边界见[organization pack 迁移](references/organization-pack-migration.md)，水印合同见[隐藏来源水印](references/provenance-watermark.md)，改进依据见[source-zero 审计](references/source-zero-audit.md)。

## 目录

```text
├── SKILL.md
├── README.md
├── agents/
├── references/
├── scripts/
├── organizations/
├── examples/
└── tests/
```

`organizations/` 与 `examples/` 中的历史内容不得作为新公众号的视觉输入。其他公众号应从空 organization pack 开始，新增独立组织证据、Ardot 品牌模式、底图家族和文章组件。

`article.json` 是内容源，Ardot 是视觉源；`wechat.html` 只是最终传输文件。

## 动态组件 A/B MVP

仓库内提供一个同输入对照实验：A 使用静态基线排版，B 只替换为无 JavaScript、无 ID、元素自身 `begin="click"` 的 SVG 揭开组件与 CSS 横向滑动，并保留语义哈希匹配的静态降级文件。主工作流进一步固定了创作层默认 2–3 个 semantic modules；transport marker 数量不等于 module 数量。入口见 [experiments/interaction-mvp/README.md](experiments/interaction-mvp/README.md)。候选生成成功不等于生产启用；保存回读和目标账号 iOS/Android 能力档案都通过后才可选择动态 payload。

## 安全边界

- Logo 和二维码只能来自用户或官方资料。
- 生成图像不能冒充真实人物、活动或项目成果。
- 组织包不存储 AppSecret、access token 或其他账号凭据。
- 正式发布始终需要一次独立确认。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 /path/to/skill-creator/scripts/quick_validate.py .
```
