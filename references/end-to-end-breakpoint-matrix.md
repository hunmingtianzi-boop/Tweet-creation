# 端到端断点矩阵

本表是跨组织公众号工作流的故障边界，不是人工自报清单。每个 `machine gate` 都必须重新读取其绑定的字节、宿主响应或图像像素；报告中自写的 `passed: true` 不是证据。

| 阶段 | 常见断点 | machine gate | 允许的恢复或降级 | 严禁误报 |
| --- | --- | --- | --- | --- |
| 安装 | 仓库已更新，当前 harness 仍载入旧 Skill | `release_skills.py verify-installed` 及 `build-census` 逐字节校验三个 Skill | 按 release manifest 临时组包、备份、原子替换后重建 census | “已 commit/push”不等于“当前会话已安装” |
| 平台 | OS/Python/wheel 与锁定字节不一致 | `secure_runner.py --platform-audit` 核对 `platform-support.json` 和依赖分发文件 | 仅生成 candidate，经独立审查后才能更新信任锁 | CI 或未知平台不得自动晋升为 trusted |
| 启动 | 不知道需要哪些 Skill、工具、链接、登录或密钥 | `build-census` 从已验证安装包与 host registry 生成能力快照；`init-profile` 只接收紧凑 target，并分开草稿 API、宿主 current-session authority、portable signer 与 UI live route | 按报告的有序 `host_setup_actions` 预备，只在真实登录/2FA 阻断时请用户一次处理 | 手填 `loaded/available`、带 token URL、Cookie 或密钥值不得入档；`wechat.draft` 不等于 live publish authority |
| 迁移 | 其他 harness 只有部分工具，或把 shell 当成生图/Browser | 稳定语义能力绑定 + 中性 RGBA 路由实测 + 三底检查 | 可以更换具体 provider，但必须继续满足同一输出合同 | 本地像素报告不能冒充宿主生成/下载事件 |
| 审计等级 | 缺 `host.receipt.attest`、`host.migration.finalize` 或 `filesystem.access.lease` | 报告分开 `operational_ready` / `phase_ready` / `portable_audit_verified` | 同一可见宿主会话可继续；只是不得声称 host-enforced 或 portable signed audit | 这些缺失不是登录错误，也不得单独阻断当次发布 |
| source-zero | 旧稿、其他组织、examples 或 output 污染视觉 | 真实路径/父级 symlink/字节 SHA 白名单，中英文旧稿目录排除 | 只使用当次 `inputs/current` 与本组织 pack；明确风格参考只提取抽象 grammar | 不得打开旧推文“找感觉”；release 不打包历史目录 |
| 组织迁移 | 只换 Logo/颜色，或复用上一公众号的设计 | `orgs.py validate` 检查组织事实、视觉校准、Ardot root 和资产归属 | 从 provisional pack 与 2–3 组小样重新校准 | 旧 organization pack 不得作为新组织的品牌依据 |
| 资产职责 | 用 AI 图冒充活动证据，或把真实照片当装饰底图 | `asset_role_policy.py` 强制单一 role、origin 与使用场景 | 真照片只承担纪实证据；AI 只承担抽象底图或明确的插画/解释职责 | 生成/派生图永远不得标成 documentary photo |
| RGBA 源 | provider 宣称透明，实际是 RGB、假棋盘或整片白底 | Browser 原图 create-once 摄取固定源 SHA/bytes；`prepare_micro_cutout.py --require-native-alpha` 检查真 Alpha | 原生 Alpha 失败时，只允许当前 slot 再生成一张受控键色源并本地转 RGBA | 不使用截图、预览 canvas、剪贴板图或远程 URL |
| 正式生图采集 | 操作者手写 provider ledger/route/host trace，或把 Python callback 冒充宿主签名 | acquisition v2 绑定 verified release census、adapter route、完整同会话 migration、每次 canonical request、create-once ingestion/raw SHA+bytes 和 RGBA 像素链；prepare/register/pack/ready 全部重验 | current-session 可 operational accept，但固定 operator/harness-trusted、`host_attested=false`、`portable=false`；可选 callback 只能 veto；portable 由受保护 Ed25519 双签名升级 | 旧 v1、伪 route、raw/像素篡改、callback 否决仍阻断；`lambda True` 绝不得产生鉴真或可携带宣称 |
| 抠图 | 透明通道存在，但边缘有白边/色 halo/烟雾/碎片，或底板仍在 | RGBA8、非零 Alpha、紧裁切、open-edge、matte/halo/debris 与三底像素验收 | 重生成一次受控源；不能降低门槛修补 | “看起来透明”不等于可进 Ardot |
| 四类微组件 | 组件少于四类、重复、带底板或变成一张通栏大图 | 四个 distinct derived SHA + `floating-spot` / `section-transition` / `inline-explainer` / `closing-motif` 的 Ardot node/asset 证据 | 拒绝进入全文装配，先重做缺失的组件 | 装饰、艺术字或交互子实例不得凑数 |
| 微组件排版 | 小组件占满横版，有字就打框，文字不突出 | 390 px 截图重算宽度、偏移、尺度、关系、native text node 与强调技法 | 保留主体透明、部分宽度、左右错落和非框强调 | 任一组件超 82%、图超 72% 或含框文字均阻断 |
| 底图家族 | 同文混用黑/白/大色块，纹理、主色或光向断裂 | 家族 master/companion 的空间频率、纹理、光向、surface mode 及色调连续性 | 回到小样阶段重生成同一家族；正文字独立 | 纯色 CSS 块不得伪装成 Ardot 底图导出 |
| 可读性 | 底图与正文颜色重合，或安全区明暗波动过大 | 对实际合成像素重算 copy-safe zone、4.5:1 对比度与亮度偏差 | 更换文字色、安全区或同家族 companion 后重验 | 提示词中写“高对比”不是证据 |
| 艺术字 | 只换字体，艺术字不够，或 AI 把字烙进图 | expressive-native 需 2–4 个高影响位置、2 套构成 recipe，每套至少 2 种非字体技法和 2 个可编辑节点 | 只在标题/章节/收尾使用，正文继续紧凑易读 | 字图、无授权字体、单纯 font swap 不计艺术字 |
| 信息密度 | 空白过多、卡片堆叠、框架感强，或 HTML 重排稀释 Ardot | schema-v3 五类 390 px 截图的密度样本、major gap、line-height、箱体占比 | 在 Ardot 修改并重截图，不在 HTML 中“润色” | compact-editorial 大间隔超出 24–40 px 或偶然空区 >20% 阻断 |
| Ardot 母版 | HTML 根据观感二次改写，丢坐标、遮罩、裁切、字体和组件 | 当前 root 端导出的节点、几何、层、文字、asset SHA 和逐章参考截图 | 回到 Ardot 修订，再用 `export_ardot_handoff.py` 一次性冻结 | 截屏+手写 HTML+重绘 SVG 的混合体不得交付 |
| 动态组件 | JS 被清洗，SVG 状态丢失，或 2–3 个模块被误计为实例数 | 无 ID 自触发 SVG/SMIL 或 CSS 横滑，每实例绑定唯一 fallback key/语义 SHA 和 Ardot 三态证据 | 编译同一 revision 的 dynamic/static 双 payload；证据不足自动选 static | 结构回读通过不等于手机端能运行 |
| 手机验证 | 只看编辑器，没有精确草稿的 iOS/Android 证据 | mobile profile 绑定目标账号、draft ID、revision 和字节；current-session 由宿主 live authority 现场捕获/消费，签名版才可携带 | 当前会话的双端实测可选 dynamic；无实测则更新同一草稿为 static | 本地 `host-trace.json` 不能自证当前会话；不得复用历史账号/草稿能力档案 |
| 微信素材 | 本地路径进正文、封面与正文混用上传链路、超官方限制 | API 事务台账按 source SHA 去重；正文 `uploadimg` URL 映射；封面永久素材 `thumb_media_id` | 替换所有本地路径后再编译；超限资产回到导出阶段处理 | 预检只能证明可读端点，写能力只由真实上传/草稿事务证明 |
| 草稿 | 编辑器中看到内容就误报“交付成功” | publisher 只接受冻结 handoff + upload map + compile report；保存后用 `draft/get` 捕获 raw response、CDN 图、逐章截图与内容 SHA | 回读不一致就更新同一草稿或停止 | 预览、粘贴、封面选择不证明已保存，也不证明已发布 |
| 隐藏水印 | 把水印强制用在真照片/透明组件，或没有 carrier 也要求 secret | carrier census 先重算 eligible 不透明生成底图/封面；有 carrier 才要求外部密钥和 CDN 再验证 | 零 carrier 显式标记 `not-applicable`；运输丢失则阻断发布 | 自报 authentication JSON 或本地源 SHA 不证明水印经过微信 |
| 正式发布 | 草稿被误当发布，确认过期/重放，或 submit 成功被误报为已上线 | 当次显式确认绑定 account/revision/draft/report SHA 且有时效 nonce；current-session 还要由宿主 live authority 现场消费用户事件并重读 Ardot/账号/草稿；submit 前再 `draft/get`；轮询 `freepublish/get` | 超时保持 `unknown/publishing`，只读恢复，不重复 submit；无 live authority 时选 portable signed 或明确 UI live route | CLI 加一个“确认 JSON”不能启用 current-session API 发布；只有 status `0` 且返回 article URL 才能报“已发布” |
| 证据携带 | 在另一机器上复制 JSON 就声称当时真实读写过 Ardot/微信 | portable 模式验证宿主 Ed25519 receipt、保护的公钥信任库和精确字节绑定 | 无 signer 时只在当前可见宿主轨迹中声称当次验证 | `portable_audit_verified: false` 不影响当次操作，但必须保留这个语义 |
| CI/前向测试 | 测试偷用历史 example 而非新输入，或只测单个函数 | portable contract CI + 受支持本机全量 unittest + 独立代理的 source-zero 合成前向测试 | 其他平台先 fail-closed，独立审查锁文件后才扩展 | 历史 `examples/` 只是回归夹具，不是新稿的视觉或数据源 |

## 交付语义

- `binding_ready: true`：仅表示本地安装、路径和能力绑定成立，不表示已登录或已执行宿主操作。
- `operational_ready: true`：表示当前可见宿主会话已完成所需路由实测；该证据不可离开当前会话冒充签名事实。
- `phase_ready: true`：只用于通过真实宿主 finalizer 的可携带迁移结果。
- `draft-saved`：只表示精确账号中存在绑定 revision 的草稿；不表示已群发或已上线。
- `published`：只在官方 `freepublish/get` 返回终态成功且含文章 URL 时使用。

任何未列明的外部前置（真实账号权限、登录/2FA、精确 Ardot file/root、微信 AppID/AppSecret 授权、真机 iOS/Android 验证）都应由启动报告事先列出，而不是等到交付末端才暴露。
