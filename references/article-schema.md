# Article specification

The compiler accepts UTF-8 JSON:

```json
{
  "schema_version": 1,
  "article_id": "example-article-slug",
  "organization_id": "example-organization",
  "article_type": "recruitment",
  "title": "Article title",
  "summary": "Optional draft summary",
  "route": "approved-route-selected-at-startup",
  "production_preferences": {
    "status": "confirmed",
    "confirmed_by": "user",
    "micro_component_count": 2,
    "use_svg": true,
    "style_route": "approved-route-selected-at-startup",
    "generate_backgrounds": false
  },
  "storyboard": {
    "status": "approved",
    "chapters": [
      {
        "id": "opening",
        "label": "Opening",
        "thesis": "One reader-facing idea",
        "composition": "image-led-opening",
        "visual_intent": "A concrete subject enters from open space",
        "density_intent": "Intentional hero pause; body sections return to compact-editorial density",
        "block_indices": [0]
      }
    ]
  },
  "visual_kit": {
    "status": "approved",
    "selected_roles": ["floating-spot", "inline-explainer"],
    "direction": "Short article-specific visual direction",
    "assets": [
      {
        "id": "spot.example-a",
        "asset_sha256": "<64 lowercase hex characters from the approved cutout>",
        "role": "floating-spot",
        "storyboard_chapter": "opening",
        "source_text": "One exact sentence copied from the article",
        "concrete_subject": "A named organization object",
        "action": "enters along the reading direction",
        "composition_role": "anchor",
        "placement": "lead right edge",
        "ardot_component": {
          "file_url": "https://ardot.example/current-organization",
          "node_id": "12:34",
          "name": "WeChat/Ornament/FloatingSpot/Current Mode"
        }
      }
    ]
  },
  "typography": {
    "status": "approved",
    "moments": [
      {
        "role": "hero-title",
        "storyboard_chapter": "opening",
        "source_text": "Main title",
        "treatment": "stacked-title",
        "editable_text": true,
        "font_source": "licensed-or-system",
        "fallback_text_style": "Display/Hero/Fallback",
        "ardot_text_style": {
          "file_url": "https://ardot.example/current-organization",
          "node_id": "14:7",
          "style_id": "13:2",
          "name": "Type/Display/Stacked/Current Mode"
        }
      },
      {
        "role": "statement",
        "storyboard_chapter": "opening",
        "source_text": "Supporting statement",
        "treatment": "mixed-weight",
        "editable_text": true,
        "font_source": "licensed-or-system",
        "fallback_text_style": "Display/Statement/Fallback",
        "ardot_text_style": {
          "file_url": "https://ardot.example/current-organization",
          "node_id": "14:8",
          "style_id": "13:3",
          "name": "Type/Display/MixedWeight/Current Mode"
        }
      }
    ]
  },
  "visual_review_file": "article-visual-review.json",
  "blocks": [
    {
      "type": "hero",
      "component": "core.hero",
      "eyebrow": "OPTIONAL LABEL",
      "title": "Main title",
      "subtitle": "Supporting statement"
    }
  ]
}
```

`article_id` is a stable lowercase slug for this exact article. `organization_id` must match the organization pack. `article_type` must exist in `organization.json`. `route` is explicit because the chosen style is part of the startup intake.

## Startup production preferences

Before source reading or image generation, ask once for four related choices and record the answer in `production_preferences`: micro-component count (`0`–`4`), whether this article authors SVG interaction candidates, which approved organization style route to use, and whether to generate raster backgrounds. `status: confirmed` plus `confirmed_by: user|editor` is required downstream; a missing object is not silently replaced by defaults.

`visual_kit.selected_roles` contains exactly `micro_component_count` distinct roles chosen for the article from `floating-spot`, `section-transition`, `inline-explainer`, and `closing-motif`. The planner chooses the semantically useful roles after the storyboard, but may not change the confirmed count without asking again. With count `0`, use `visual_kit: {"status":"not-requested","selected_roles":[],"assets":[]}` and omit micro-component layout evidence. Every selected component still needs its own article-grounded provider original, final RGBA8 cutout, lineage, asset SHA, and native Ardot component evidence.

`use_svg: true` requires a `dynamic-default` plan with 2–3 semantic modules. `use_svg: false` requires `authoring_mode: static-selected`, `target_module_count: 0`, and no modules; this is a normal startup choice, not an editorial exception. `style_route` must equal `article.route`. `generate_backgrounds: false` uses continuous Ardot-native surfaces, gradients, and open vectors and creates no raster background family; `true` requires the calibrated generated family and its pixel/watermark gates.

This JSON drives semantic validation and Ardot assembly. It does not drive final WeChat layout. After visual approval, only a frozen `ardot-current-root-layer-export-v1` from the current root may drive delivery HTML; the article-JSON adapter is an explicit non-delivery preview. Ardot is the visual source of truth. A block may set optional `variant`; otherwise the selected route supplies the variant and `ardot.json` maps it to an exact native component.

## Interaction plan

当启动选择 `use_svg: true` 时，文章必须在 `article.json` 中使用 `dynamic-default` 规划 2–3 个创作层 semantic modules。module 是一个连续区域和一个读者任务；一个 module 可以包含多个实际 transport instances。例如四个部门分别点击展开，仍是一个 module，但需要四个逐项 key/hash。选择 `use_svg: false` 时使用零 module 的 `static-selected`。完整规则见 [interaction-composition.md](interaction-composition.md)。

```json
{
  "interaction_plan": {
    "status": "approved",
    "authoring_mode": "dynamic-default",
    "target_module_count": 2,
    "article_root_node_id": "51:2",
    "ardot_revision_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "modules": [
      {
        "id": "department-reveal",
        "pattern": "tap-reveal-group",
        "candidate_modes": ["svg-smil-self", "horizontal-swipe"],
        "storyboard_chapter": "identity",
        "source_block_indices": [2],
        "placement_band": "early",
        "purpose": "让读者按需展开并比较各部门职责",
        "instances": [
          {
            "id": "planning-department",
            "source_texts": ["策划部负责把问题变成任务。"],
            "fallback_key": "planning-department",
            "semantic_hash": "sha256:3e5e57411939ee4b8c192740dd0fa5166cdd655788a8d1b2ce1510cffd68d63f"
          },
          {
            "id": "technical-department",
            "source_texts": ["技术部负责把任务变成原型。"],
            "fallback_key": "technical-department",
            "semantic_hash": "sha256:8d1a08ef940420c6b54387e58f60cd16546bc03cf3110586afef31c1bfd45706"
          }
        ],
        "ardot_component": {
          "file_url": "https://ardot.example/current-organization",
          "name": "WeChat/Interaction/DepartmentReveal/Current Mode",
          "revision_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "covered_instance_ids": ["planning-department", "technical-department"],
          "covered_semantic_hashes": [
            "sha256:3e5e57411939ee4b8c192740dd0fa5166cdd655788a8d1b2ce1510cffd68d63f",
            "sha256:8d1a08ef940420c6b54387e58f60cd16546bc03cf3110586afef31c1bfd45706"
          ],
          "states": {
            "closed": {"node_id": "60:1", "screenshot": "qa/department-closed.png", "sha256": "<actual file SHA-256>"},
            "open": {"node_id": "60:2", "screenshot": "qa/department-open.png", "sha256": "<actual file SHA-256>"},
            "fallback": {"node_id": "60:3", "screenshot": "qa/department-fallback.png", "sha256": "<actual file SHA-256>"}
          }
        }
      },
      {
        "id": "process-reveal",
        "pattern": "process-reveal",
        "candidate_modes": ["svg-smil-self"],
        "storyboard_chapter": "process",
        "source_block_indices": [4],
        "placement_band": "middle",
        "purpose": "让读者分步理解原型推进过程",
        "instances": [
          {
            "id": "process-steps",
            "source_texts": ["按准备、试做、验证三个阶段推进。"],
            "fallback_key": "process-steps",
            "semantic_hash": "sha256:591c57e57577764ad3c4d993a90ec931a3267bbbd580107f437a8b289325c708"
          }
        ],
        "ardot_component": {
          "file_url": "https://ardot.example/current-organization",
          "name": "WeChat/Interaction/ProcessReveal/Current Mode",
          "revision_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "covered_instance_ids": ["process-steps"],
          "covered_semantic_hashes": ["sha256:591c57e57577764ad3c4d993a90ec931a3267bbbd580107f437a8b289325c708"],
          "states": {
            "closed": {"node_id": "61:1", "screenshot": "qa/process-closed.png", "sha256": "<actual file SHA-256>"},
            "open": {"node_id": "61:2", "screenshot": "qa/process-open.png", "sha256": "<actual file SHA-256>"},
            "fallback": {"node_id": "61:3", "screenshot": "qa/process-fallback.png", "sha256": "<actual file SHA-256>"}
          }
        }
      }
    ]
  }
}
```

`build_ardot_manifest.py` 在装配前只校验 module 数量、分布、source block 落点、instance key/hash 与静态例外；此时三态节点可以尚未完成。作者预览才从 article JSON 渲染，必须显式加 `--authoring-preview`，不得导入公众号。两档投递都只接受当前 article root 的冻结图层 export 和独立 fresh reread：无 signer 时使用 `compile_wechat.py --transport-fidelity ... --live-root-export ... --session-draft --check`，产生 `wechat-candidate.html` / `candidate-report.json` 并固定 `portable_audit_verified: false`；有宿主 Ed25519 attestor 时可使用带 `--live-root-receipt` 的 `portable-signed-audit`，其 receipt 额外绑定 runtime/trusted bundle 与 intended HTML path。transport 本身同时绑定 root/revision、连续 chapter geometry、完整 source-node/font/render-style/body-asset census、独立资产，以及每个 module 的 `closed/open/fallback` 节点与 tree hash。两档都只能创建/验证草稿，不授权正式发表或群发。

新文章在启动时明确选择不用 SVG，应使用 `authoring_mode: static-selected`、`target_module_count: 0` 与空 `modules`；`production_preferences` 已记录这次选择，不再重复要求例外说明。`static-exception` 只用于迁移旧记录，或在已确认动态后因材料只有 0–1 个合理机会而发生的编辑例外，并写入允许的 `category`、至少 12 字的具体 `reason` 与 `confirmed_by: user|editor`。目标账号暂无能力档案不属于创作例外；它只让投递层选静态等价版。

Before visual authoring, validate the 4–10 chapter storyboard:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_storyboard.py" article.json \
  --output output/<organization-id>/<slug>/storyboard-plan.json
```

Then generate and complete the article-specific visual-kit decision. The record is mandatory, but it is intentionally empty when the confirmed component count is zero:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_visual_kit.py" article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/visual-kit-plan.json
```

The selected roles are an exact subset of `floating-spot`, `section-transition`, `inline-explainer`, and `closing-motif`. Every selected entry must bind to exact article copy and one approved storyboard chapter, with a specific subject/action and a composition role of `anchor`, `motion`, `connector`, or `punctuation`. Use `min(3, selected count)` different composition roles and the same number of distinct derived assets as selected components. On the only supported execution host, Codex Desktop, `build_visual_kit.py` defaults each source request to `chatgpt-web-image-route-v1`: Codex operates ChatGPT only through the built-in Browser, asks for an article-specific provider original, downloads the original, and uses native Alpha or a controlled-key cutout route according to that real asset. The synthetic startup image is gone; the first selected article component is the route's real quality test. A future harness port must preserve this acquisition/output contract, but no alternate harness is supported by this release. Each registered article-micro asset must bind its raw source, prompt/provider route, processor/config, derivation report, and final SHA; pass the final RGBA8/robust-Alpha/tight-crop/no-matte/no-halo/no-debris gate; record its exact derivative `asset_sha256`; and record its native Ardot component file URL, node ID, and exact name. Then generate the Ardot assembly manifest:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/build_ardot_manifest.py" article.json \
  --org organizations/<organization-id> \
  --output output/<organization-id>/<slug>/ardot-manifest.json
```

Every storyboard chapter must declare `density_intent`; ordinary chapters default to `compact-editorial`, while intentional open space is reserved for Hero, transition, or ending moments. After assembly, create a separate screenshot-backed schema-v3 visual review and store its path in `visual_review_file`. It must cover five distinct Ardot nodes, include five density samples, and provide a hashed `ardot-article-instance-inventory` plus one hashed `ardot-node-properties` export for every actual visual-kit instance. The validator derives micro image/component widths, horizontal offsets, text enclosure, and primary-copy font scale from these node exports and the screenshot-bound density samples. It must cover repeated role instances, not four hand-picked exemplars, and pass every check in [visual-review.md](visual-review.md). A Boolean, ratio, or count written inside the article cannot self-approve the design.

When organization calibration chooses `expressive-native`, `typography.moments` must contain at least two grounded display moments (up to the organization maximum) across at least two semantic roles and treatments. Each moment references an approved `recipe_id` and contains a `construction` object with at least two allowed non-font techniques, the recipe's full technique set, unique `native_text_node_ids` / `accent_node_ids`, 1–4 lines, and `scale_ratio >= 1.15` when scale contrast is used. Its primary Ardot text node must appear in that construction. Each moment uses licensed/system fonts, stays editable, has a standard fallback, and records file/node/style/name evidence. A font swap alone fails. See [expressive-typography.md](expressive-typography.md). Do not reference an image or asset ID for display copy.

## Supported blocks

- `hero`: `title`, optional `subtitle`, `eyebrow`, `background`, `background_alt`, `cta`.
- `lead`: `paragraphs`.
- `section`: `title`, optional `number`, `kicker`.
- `text`: `paragraphs`.
- `statement`: `title`, optional `label`, `body`.
- `metrics`: `items` with `value`, `label`, and required `source_id` for final checks.
- `timeline`: `items` with `label`, `description`, optional `source_id`.
- `gallery`: `images` with `src`, `alt`, optional `caption`, `source_id`.
- `case`: `name`, `problem`, `approach`, `output`, optional `evidence`, `source_id`.
- `roles`: `items` with `name`, `description`.
- `quote`: `text`, `attribution`, and required `source_id` for final checks.
- `steps`: ordered `items`; each item may be a string or `{title, description}`.
- `image`: `src`, `alt`, optional `caption`, `source_id`.
- `cta`: `title`, optional `body`, `steps`, `button`; optional `qr` requires `src`, `alt`, and `origin` of `user-supplied` or `official`.
- `references`: `items` with `label` and `source_id`.
- `footer`: optional `name`, `tagline`, `logo`, and `credits`.

The repository workflow attribution is not an article block and cannot be overridden by `footer`, article data, or an organization pack. Ardot and transport must append exactly one final visible native-text credit: `感谢拓浙 AI 生态提供本篇内容生产工作流支持。` (`policy_id: tuozhe-ai-ecosystem-workflow-v1`). A user-authored `footer` appears before this reserved terminal component.

Relative image paths resolve from the article JSON. The compiler copies local images into the output `assets/` directory. Remote WeChat URLs remain unchanged.

Asset registry IDs such as `visual.hero-example` resolve from the organization pack for both Ardot upload and final transport. Keep generated visuals text-free; copy remains editable in Ardot text nodes.

When a resolved asset is an eligible generated opaque background or raster
cover, Ardot and the compiler consume the already marked registered derivative;
they never embed the first mark. The Ardot manifest and compile report carry its
public `local_verified` evidence, authenticate the current pixels with the
external key, independently rerun the fixed full-frame transport simulation,
and verify that copied bytes still match `marked_sha256`. Missing key material
is a blocking error, even if a JSON report claims success. The WeChat publisher must then detect the actual hosted body or
cover derivative before changing that asset to `transport_verified`. No raw
watermark ID or secret is permitted in an article, manifest, HTML, or report.

## Evidence checks

- Every `source_id` must exist in the organization pack’s `sources.json`.
- A metric without `source_id` blocks `--check`.
- A quote without attribution or `source_id` blocks `--check`.
- Placeholders such as `待补充`, `待确认`, `TBD`, and `PLACEHOLDER` block `--check`.
- Missing local images block `--check`.
- An eligible generated background/cover without bound public watermark evidence,
  a preserved source, independently verified PSNR, matching final/report hashes,
  or authenticated detection blocks `--check` when the organization policy is
  `required`.
- Missing any selected visual-kit role, fewer distinct current-article derived micro assets than the confirmed count, missing original-download/derivation lineage, RGB or all-opaque pseudo-RGBA, failed final Alpha/aspect/halo/debris/matte validation, a raw source referenced by Ardot, or missing native Ardot component evidence blocks `--check`.
- A missing organization/route calibration, incomplete storyboard, ungrounded visual subject, or failed `visual_review_file` blocks `--check`.
- A missing, changed, duplicated, hidden, rasterized, or non-terminal reserved workflow attribution blocks transport and handoff.
- Missing expressive typography recipe/construction evidence, fewer than two non-font techniques or editable layers, a font-swap-only moment, a baked title image, an unlicensed font, or an ungrounded display phrase blocks `--check` when the organization uses `expressive-native`.
- A QR image that is not explicitly official or user-supplied blocks `--check`.
