# 前端设计与实现（web/）

> 更新日期：2026-09（增补流式问答输出）。本文合并原 `WEB_UI_PLAN.md`（设计语言与交互规则）与
> `output/OPERATOR_DETAIL_IMPLEMENTATION.md`（干员详情展示），按 React 组件视角重写维护重点。
> 技术栈：Vite + React 18 + TypeScript + framer-motion，构建产物 `web/dist` 由 FastAPI 托管。

## 1. 设计语言

**官网视觉全面重构（2026-09-09）**：全屏官方角色拼贴、固定导航、黑色底部操作区，
查询区采用官网子页的通栏黄色标题和白底信息布局。主色统一为 `#fffa00`，
正文使用 `#282828` / `#626262`，移除旧版大量异形卡片和蓝色投影。
桌面端使用固定左轨，移动端回到紧凑顶栏；装饰不得遮挡表格、媒体和按钮。
设计 token 集中在 `web/src/styles/tokens.css`。

素材位于 `assets/official/`，`sources.json` 记录原始 URL、字节数与 SHA256。
首页支持佩丽卡/管理员切换；选择示例后自动滚动至查询区。
官网素材原版权归原权利人，页面标明非官方社区工具。

动效取自终末地官网的运动语法：按钮/卡片反馈保持 0.2–0.4 秒，区块用 clip-path 单向揭示，
背景纹理才允许慢循环。开场约 1.25 秒且每会话只播放一次，并有 2 秒硬超时防止后台标签页永久遮挡。
直接页面研究与证据等级见 `../output/audit_20260909/OFFICIAL_UI_MOTION_RESEARCH.md`。

## 2. 页面结构与交互规则

| 区域 | 组件 | 说明 |
|---|---|---|
| 顶部 | `TopBar` | 品牌、后端连接状态、简短说明 |
| 搜索 | `SearchBox` | 配方树/知识问答双模式，各自独立保存 query |
| 结果 | `ResultPanel` + `AskResult`/`SynTree`/`KbCard`/`DeviceCards` | 纵向配方树、带来源的知识回答、结构化卡片 |
| 干员 | `OperatorDossier` | 章节导航、局部 Tab、图片/视频卡、音频、独立表格滚动条 |
| 首页 | `Hero` | 全屏角色拼贴、遮罩换人、文字错峰入场、操作区；图片本地加载 |
| 开场 | `EntryCurtain` | 会话首次进入的短机械开场（约 1.25s，2s 硬超时） |
| 页脚 | — | 图片素材与画师署名 |

核心交互规则（设计资产，勿随意打破）：

- 空 query 显示入口和示例，不默认查询某个物品；
- 搜索建议前缀优先，再做包含匹配；
- 模式切换不自动发送请求；相同知识问题优先读本次会话缓存；
- 宽表在自己容器内横向滚动，不依赖整页底部滚动条；
- 图片保持可辨认尺寸，视频/图库不塞进窄标题栏；
- 所有动画遵守 `prefers-reduced-motion`。

## 3. 问答答案与 markdown

`AskResult`/`AnswerMarkdown` 负责渲染 `/api/ask` 的答案：`**加粗**`、`*斜体*`、`` `代码` ``、列表、表格
转成 React 节点（防 XSS：全库无 `dangerouslySetInnerHTML`，渲染一律走受控节点），`[来源N]` 渲染为可点击角标。
小程序端有等价实现（`miniprogram/utils/markdown.js` → rich-text）。

### 3.1 流式输出（网页问答默认）

网页知识问答优先走 `POST /api/ask/stream`（SSE），事件序列：`phase`（受理/检索中）→ `meta`（意图 + 来源先亮）→
`delta`×N（回答逐段文字）→ `done`（完整结果，含 trace_id/feedback_snapshot）。

- `api.ts` 的 `fetchAskStream` 负责 SSE 解析（fetch + ReadableStream，无第三方依赖），支持 AbortSignal 中断；
- `App.tsx` 维护流式状态机：`meta` 一到就把来源渲染出来，`delta` 按约 80ms 节流合并重渲染（避免逐 token 全量解析 markdown）；
- `AskResult` 在流式期间显示阶段提示与光标，`done` 后进入与旧 `/api/ask` 完全一致的完整渲染（反馈按钮、来源跳转等）；
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
- **响应式**：新视觉效果同时检查 1280×720、窄屏和减少动态效果模式；
- **素材路径**：一律用 `/assets/...`，不要依赖开发机绝对路径（dev 由 vite 代理 `/assets`，build 拷贝进 dist）；
- **安全**：渲染 LLM/网络数据一律走 React 文本节点，禁止引入 `dangerouslySetInnerHTML`；
  请求 URL 用 `encodeURIComponent`；错误响应解析后端的 `detail` 展示给用户。

## 6. 相关文件

- 构建：`npm run build`（产物 `web/dist`，FastAPI 自动托管）；开发：`npm run dev`（5173，自动代理 `/api`）
- 组件与样式：`web/src/`；请求封装：`web/src/api.ts`；类型：`web/src/types.ts`
- 契约测试：`tests/test_frontend_contract.py`；组件测试：`web/tests/`
- 视觉规范参考：`deploy/API_SECURITY.md`（代理安全边界）
