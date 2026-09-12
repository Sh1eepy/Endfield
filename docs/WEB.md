# Web 前端设计

> 更新日期：2026-09-12。本文按 React 组件视角记录 Web 的技术选择、交互不变量、测试边界和扩展准备。
> 技术栈：Vite + React 18 + TypeScript + framer-motion + Three.js，构建产物 `web/dist` 由 FastAPI 托管。

## 1. 设计语言

**官网视觉全面重构（2026-09-09）**：全屏官方角色拼贴、固定导航、黑色底部操作区，
查询区采用官网子页的通栏黄色标题和白底信息布局。主色统一为 `#fffa00`，
正文使用 `#282828` / `#626262`，移除旧版大量异形卡片和蓝色投影。
桌面端使用固定左轨，移动端回到紧凑顶栏；装饰不得遮挡表格、媒体和按钮。
设计 token 集中在 `web/src/styles/tokens.css`。

素材位于 `assets/official/`，`sources.json` 记录原始 URL、字节数与 SHA256。
首页支持佩丽卡/管理员切换；选择示例后自动滚动至查询区。
官网素材原版权归原权利人，页面标明非官方社区工具。

日常按钮/卡片反馈保持 0.2–0.4 秒，区块使用单向揭示；品牌开场与日常交互区分强度。当前开场约 6 秒、8 秒硬超时，每会话默认一次并可跳过/重播。Home 与 Query 共享一个按需 Three.js 双螺旋空间，具体边界见 [Web 空间体验](FRONTEND_EXPERIENCE.md)；早期页面研究见 [2026-09-09 动效研究](archive/2026-09-09-MOTION.md)。

## 2. 页面结构与交互规则

| 区域 | 组件 | 说明 |
|---|---|---|
| 顶部 | `TopBar` | 品牌、后端连接状态、简短说明 |
| 搜索 | `SearchBox` | 配方树/知识问答双模式，各自独立保存 query |
| 结果 | `ResultPanel` + `AskResult`/`SynTree`/`KbCard`/`DeviceCards` | 纵向配方树、带来源的知识回答、结构化卡片 |
| 干员 | `OperatorDossier` | 章节导航、局部 Tab、图片/视频卡、音频、独立表格滚动条 |
| 首页 | `Hero` | 全屏角色拼贴、遮罩换人、文字错峰入场、操作区；图片本地加载 |
| 空间 | `ArchiveExperience` + `archiveScene` | Home/过渡/Query 共用 canvas；双螺旋、玻璃档案、中央环、抽取与降级 |
| 等待 | `RetrievalStatus` | 真实 SSE 阶段、不确定进度、等待秒数与停止入口 |
| 开场 | `EntryCurtain` | 会话首次进入的分段开场（约 6s，8s 硬超时） |
| 页脚 | — | 图片素材与画师署名 |

核心交互规则（设计资产，勿随意打破）：

- 空 query 显示入口和示例，不默认查询某个物品；
- 搜索建议前缀优先，再做包含匹配；
- 模式切换不自动发送请求；相同知识问题优先读本次会话缓存；
- 宽表在自己容器内横向滚动，不依赖整页底部滚动条；
- 图片保持可辨认尺寸，视频/图库不塞进窄标题栏；
- 所有动画遵守 `prefers-reduced-motion`。
- 3D 展示载体不绑定知识条目；WebGL 失败不得影响查询与结果；触摸端保持浏览器原生纵向滚动。

## 3. 问答答案与 markdown

`AskResult`/`AnswerMarkdown` 负责渲染 `/api/ask` 的答案：`**加粗**`、`*斜体*`、`` `代码` ``、列表、表格
转成 React 节点（防 XSS：全库无 `dangerouslySetInnerHTML`，渲染一律走受控节点），`[来源N]` 渲染为可点击角标。
小程序端有等价实现（`miniprogram/utils/markdown.js` → rich-text）。

### 3.1 流式输出（网页问答默认）

网页知识问答优先走 `POST /api/ask/stream`（SSE），事件序列：`phase`（受理/检索中）→ `meta`（意图 + 来源先亮）→
`delta`×N（回答逐段文字）→ `done`（完整结果，含 trace_id/feedback_snapshot）。

- `api.ts` 的 `fetchAskStream` 负责 SSE 解析（fetch + ReadableStream，无第三方依赖），支持 AbortSignal 中断；
- `App.tsx` 维护流式状态机：`meta` 一到就把来源渲染出来，`delta` 按约 80ms 节流合并重渲染；
- 流式期间正文按安全纯文本增量显示，不反复解析增长中的完整 Markdown；`done` 后一次性转为完整 Markdown、来源跳转和反馈视图；
- 结果面板在 loading→首段正文时不重新挂载，避免入场动画遮住首 token；生成期间可主动停止并保留当前内容；
- 旧后端没有 `/api/ask/stream` 时抛 `StreamUnavailableError`，自动回退整包 `/api/ask`；小程序仍走旧接口（`wx.request` 不支持流式读取）。

## 4. 干员详情展示规则

数据来自 `scripts/build_operator_details.py` → `output/operator_details.json`，
经 `/api/synthesis?item=干员名` 的知识库结果附带 `operator_detail`，由 `OperatorDossier` 渲染。
保留：基本信息与带色/粗细富文本、精英化/技能/天赋/潜能/档案章节 Tab、材料/武器图片、
展示图/技能动态图/视频链接、多语种语音。

- 章节和同类多段内容用局部按钮切换；
- WIKI 颜色 token 映射为前端样式，主/副能力保持视觉区别；
- 表格外层是独立横向滚动容器 + 可拖动状态条；
- 媒体用完整图库卡片，不塞进标题区；
- 音频当前页按钮播放、再点暂停，加载失败显示明确状态（不空白）；
- 远程 WIKI 媒体走受限代理（`/api/media`），失败有兜底提示。

## 5. 维护重点（改前端前必读）

- **组件位置**：源码在 `web/src/`（`App.tsx` 编排 + `components/` 组件 + `styles/` CSS + `api.ts` 请求）；
  改 DOM 结构/交互前先跑 `tests/test_frontend_contract.py`（前端契约测试）与 `web/tests/`；
- **媒体代理**：`/api/media` 只允许可信 WIKI 域名（`bbs.hycdn.cn`），禁止放开白名单；
- **空间层**：Three.js 只改 `scene/` 与 `ArchiveExperience` 桥接，不把业务事实写入 `userData`；新增资源必须纳入 `dispose()`；
- **响应式**：新视觉效果至少检查 1440×900、390×844、窄屏触摸、上下文丢失和减少动态效果；
- **素材路径**：一律用 `/assets/...`，不要依赖开发机绝对路径（dev 由 vite 代理 `/assets`，build 拷贝进 dist）；
- **安全**：渲染 LLM/网络数据一律走 React 文本节点，禁止引入 `dangerouslySetInnerHTML`；
  请求 URL 用 `encodeURIComponent`；错误响应解析后端的 `detail` 展示给用户。

## 6. 测试问题与对策

- 请求竞态：新请求必须中止或隔离旧响应，旧结果不能覆盖新问题；
- 流式渲染：`delta` 约 80 ms 合并一次，生成中用纯文本、完成后解析 Markdown；缺少 `done` 不能缓存成完整答案；
- 模式切换：只保存/恢复草稿和已缓存知识回答，不得调用查询接口；
- Markdown 安全：只生成 React 节点，不执行原始 HTML；表格、列表内来源编号保持可点；
- 动画可用性：`prefers-reduced-motion` 同时覆盖 CSS 与 JS 动画，开场有硬超时；
- 空间交互：页面滚动缓慢带动阵列但不捕获滚轮；手机 pointer 不驱动 3D，`touch-action` 保持 `pan-y`；拾取、轮廓、抽取起点和收回姿态需要浏览器实测；
- 等待反馈：`phase`/`meta` 不得提前结束进度提示，不确定过程不能显示伪百分比；结果展开后提示不得覆盖正文；
- 树与宽表：分别使用内部滚动容器，检查 resize、窄屏、节点点击和来源返回状态；
- 官网素材本地加载，网络媒体统一走 `/api/media`，失败显示明确兜底。

## 7. 扩展准备

- 将 `App.tsx` 的问答与配方请求逐步抽为独立 session hook 和小型状态机；
- 来源详情统一消费后端 `EvidenceRef`，桌面可用侧栏，移动端用详情页；
- URL 保存模式、稳定实体 ID 和视图状态，支持分享和浏览器后退；
- 数据量、更新时间和运行状态由 API 元信息提供，避免界面写死；
- 配方树布局抽成纯数据模块后，可用于 SVG、Canvas 和图片导出。

## 8. 相关文件

- 构建：`npm run build`（产物 `web/dist`，FastAPI 自动托管）；开发：`npm run dev`（5173，自动代理 `/api`）
- 组件与样式：`web/src/`；请求封装：`web/src/api.ts`；类型：`web/src/types.ts`
- 空间实现与证据：[FRONTEND_EXPERIENCE.md](FRONTEND_EXPERIENCE.md) / [FRONTEND_SPATIAL_ACCEPTANCE.md](FRONTEND_SPATIAL_ACCEPTANCE.md)
- 契约测试：`tests/test_frontend_contract.py`；组件测试：`web/tests/`
- 媒体和接口安全边界：[API_SECURITY.md](API_SECURITY.md)
