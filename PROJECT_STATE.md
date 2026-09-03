# 项目状态

> 2026-09 更新（增补流式问答与启动预热）。项目 = **《明日方舟：终末地》配方合成树**。
> 早期「生产流水线空间规划」已整体移除（算法/产物/文档全删），不要重建。
> RAG 知识问答已在 2026-08 重新完成并接入前端，与配方合成树组成双模式应用。

## 1. 一句话概况
用户输入物品/设备名（搜索框模糊联想）→ D3 配方合成树（叶子收敛到清水/矿物/气体矿物/种子）；
无配方物品回退知识库显示其信息。

## 2. 当前成果（已完成并验证）
| 成果 | 位置 | 说明 |
|---|---|---|
| 全量分类知识库 | `endfield_kb/` | 1958 条按 22 子分类提取 jsonl+md（干员/武器/装备/设备/物品/任务/档案…） |
| 配方库 | `output/recipes.json` | **345 个配方**（recipe_extract.py 提取，不做激进清洗：含设备制造/容器/矿机/原木），合成树数据源 |
| RAG 索引 | `output/rag/` | 当前 7319 chunks（含 2373 条中文干员语音）；ChromaDB 向量 + BM25 按分类分片 + chunks.json manifest |
| RAG 增量更新 | `build_rag.py --incremental` | 内容 + sections + 索引策略版本 hash → 只重 embedding 变更条目 → 只重建变更分类 BM25 分片 |
| 合成树 API | `api_server.py /api/synthesis` | 物品合成树 / 设备配方卡 / 歧义→候选列表 / 无配方→知识库信息；叶子=基础资源，配方≤2，深度≤10，循环剪枝 |
| 名称建议 | `api_server.py /api/names` | 全部名称（配方物品+设备+知识库条目，1908 个），前端模糊搜索联想 |
| 媒体结构库 | `output/item_media.json` | extract_media.py 提取：封面图 1957 / 正文图 2046 / 外链 291 / 引用 14693（含数量与链接样式） |
| 前端 | `web/` | **Vite + React 18 + TS + framer-motion** 组件化前端（2026-08 重构）：白色工业档案风、纵向图片配方树（纯 React SVG，不再依赖 d3）、知识问答、干员详情、机械开场动效；`npm run build` 产物 `web/dist` 由 FastAPI 自动托管。后续体验优化见下方「前端体验优化」小节 |
| 微信小程序 | `miniprogram/` | 首页联想与历史、配方/问答独立查询、Canvas 合成树、知识问答证据与干员档案；问答答案经轻量 markdown 渲染（`utils/markdown.js` → rich-text，避免 `**`、`*` 等原始符号暴露）；静态检查已通过，待开发者工具和真机验收 |
| 干员详情库 | `output/operator_details.json` | 31 名干员；基本信息、富文本颜色、技能/天赋/潜能/档案多 Tab、图片与多语种语音 |
| 轻量 GraphRAG | `output/knowledge_graph/graph.db` | 2,129 实体 / 9,358 条可追溯关系；覆盖人物/任务/地点/物品/设备/配方与明确亲属关系，支持解释性关系混合取证、增量更新与问法对称门禁 |
| 评测 | `eval_retrieval.py` | 71 条查询；当前 Recall@5=100%、MRR=97.3%（`final_reviewed.json`） |
| 可观测性与坏例闭环 | `rag_trace.py` / `review_bad_cases.py` / `replay_bad_cases.py` | 脱敏 Trace、用户反馈隔离审核、批准样本回放与建议归因；Web/小程序均有反馈入口 |
| 流式问答输出 | `api_server.py /api/ask/stream` + `web/` | 网页答案 SSE 增量（phase→meta→delta→done，来源先亮、逐字流式）；与 `/api/ask` 同路由同检索，`done` 与整包返回等价；旧接口保留给小程序与评测/门禁 |
| 启动预热 | `start_server.py` | 单进程默认预热 embedding 模型与 RAG/配方索引，冷启动移进健康检查 start_period；`RAG_PREWARM=0` 关闭 |

## 2.1 前端体验优化（2026-08，web/ + miniprogram/）
- **问答答案 markdown 渲染**：`**加粗**`/`*斜体*`/`` `代码` ``/列表/表格渲染（Web 由 `AskResult.tsx` 调用 `AnswerMarkdown.tsx` 生成 React 节点；小程序端 `utils/markdown.js` → rich-text）。Web 表格支持列对齐与横向滚动，`[来源N]` 在段落/列表/表格内部保持可点击；原始 HTML 不执行。
- **审查回归修复（2026-08-28）**：恢复树节点名称点击；重复点击当前模式不清空；旧请求响应不覆盖新结果；答案来源打开详情（语音打开所属干员），返回问答复用缓存。54 项原有测试 + 7 项检索编排测试 + 13 项 Web 交互/渲染测试通过，生产构建通过；测试未调用在线 LLM。
- **合成树**：节点封面走 `/api/media` 代理（绕防盗链）、X 轴紧凑间距、树自动适配容器、树布局单位/px 爆炸修复
- **进场动效**：开场进度条动画、进场锁定滚动、恢复滚动视差与 reveal-on-scroll、吉祥物贴纸层级（z-index）与间距
- **视觉细节**：clip-path 圆角内侧留白（边缘文字完整可见）、SVG clip id 修复、封面图兜底、干员技能动态图放大与图文并排布局

## 3. 关键文件地图
- `KNOWLEDGE_SYSTEM_ARCHITECTURE.md` → 知识系统统一入口（架构 + 路线图 + 门禁一体，含监控评测工具表与结果快照）；`RAG_DEVLOG.md` → 开发决策/踩坑记录
- `scripts/build_kb_all.py` → WIKI 全量 JSON → `endfield_kb/`（22 分类 jsonl+md）
- `scripts/recipe_extract.py` → 全量 JSON → `output/recipes.json`（配方）
- `scripts/recipe_index.py` → 配方索引工具（load_recipes/build_item_index/find_item_ids_by_name）
- `scripts/extract_media.py` → 全量 JSON → `output/item_media.json`（封面图/正文图/外链/引用）
- `scripts/build_rag.py` → RAG 构建/增量（--reset 全量 / --incremental 增量）
- `scripts/rag_search.py` → 混合检索（向量+BM25 分片 → RRF）
- `scripts/api_server.py` → FastAPI（/api/synthesis、/api/names、/api/ask、/api/ask/stream（SSE 流式）、/api/health + 静态托管）
- `scripts/llm_client.py` → 在线 LLM 统一客户端（OpenAI 兼容，密钥走 .env；chat / chat_json / chat_stream）
- `scripts/intent_router.py` → 意图识别分层（L1 规则 + L3 LLM 兜底）
- `scripts/rag_ask.py` → 问答路由（枚举/结构化直查/多路检索/实体直取 → LLM 生成）；`ask_stream()` 输出 `/api/ask/stream` 的 SSE 事件，`prepare_generation()` 让流式/非流式共用拒答与上下文逻辑
- `scripts/start_server.py` → 统一启动入口（单进程默认预热 embedding/索引；`WEB_CONCURRENCY`、`RAG_PREWARM` 可调）
- `scripts/gen_eval_set.py` → 评测集自动生成；`scripts/eval_retrieval.py` → 检索评测
- `scripts/build_eval_manifest.py` → 固化评测集/索引/参数/Prompt 版本；`scripts/rag_trace.py` → 脱敏 Trace 与反馈存储
- `scripts/review_bad_cases.py` / `scripts/replay_bad_cases.py` → 反馈隔离审核、批准坏例回放和建议归因
- `scripts/gen_jieba_dict.py` + `scripts/dict_zh.txt` → 游戏专有名词词典
- `output/eval/` → 评测集与历次评测结果；`output/mention_index.json` → mention 反查索引
- `web/` → 前端（Vite+React+TS；`npm run dev` 开发 / `npm run build` 出 `dist`）；`web/vendor/` 旧 d3 已弃用
- `miniprogram/` → 微信小程序端；`miniprogram/README.md` 记录开发、真机与发布方法
- `.env` → 可选（LLM 相关配置，私密勿提交）；`.gitignore` + `.env.example` → 密钥安全

## 4. 关键技术结论
- 合成树剪枝规则：叶子=基础资源（免费资源清水/惰气/息壤气 + 无产出配方矿物 + **种子类**）；每个物品最多 2 个配方（排除自循环）；循环/超深分支直接剪掉，不显示"已截断"；植物类（芽针/锦草等）正常展开种植机配方；**无配方物品回退知识库返回物品信息**
- RAG 增量：条目内容、sections 与索引策略版本共同生成 hash → manifest 对比 → ChromaDB 分批 upsert/delete → BM25 按分类分片只重建变更分类
- 设备（如"天有洪炉"）走 `/api/synthesis` 的设备分支 → 配方卡片（原料/产物/耗时）
- 知识问答不是开放式 Agent：当前为确定性强规则 + 一次受约束语义检索规划 + 可选答案生成。
  开放问题通常 2 次 LLM（规划、回答），图关系通常 1～2 次，结构化直查可 0 次；规划器不能直接提供事实。
- 长条目生成不再固定截取开头，使用 `focus_long_context()` 从全文分散选择覆盖各子问题的证据窗口。
- HTTP 问答会返回 `trace_id`；普通 Trace 只保留查询指纹，用户主动反馈才保存正文。反馈先隔离审核，批准且补齐 Gold 后才能回放，不能自动进入质量门禁。

## 5. 当前发布边界

- 仓库已经具备可复现 Dockerfile、Compose、自有服务器 Nginx/HTTPS/限流模板、Railway 配置、依赖锁定和部署说明；2026-08-21 已完成本地 Docker 镜像构建与容器运行验证。
- 2026-08-29 API 安全加固：问答可选令牌鉴权、每 IP 频率/每日次数与全站每日次数限制（共享 SQLite、Compose 持久卷）；管理接口仅限本机或令牌；媒体拒绝重定向、分块下载至多 25 MiB 并限制下载/发送并发。默认保留有限额匿名问答，不代表已接入用户登录。部署注意事项见 `deploy/API_SECURITY.md`。
- 已有服务器时按 `deploy/README.md` 使用 Compose + Nginx 发布；Railway 仅作为无自有服务器时的可选方案。
- 小程序主体功能已接入同一套 FastAPI；模拟器默认访问本机，正式发布前还需配置线上 HTTPS API 域名并完成真机验收。

## 6. 待办与已知限制

- 答案黄金集仍小（仅 6 条），需继续收集真实困难问题，扩充 holdout/challenge 集；
- reranker 与受限 Agent Loop 均须先由困难评测证明收益，再决定是否引入（见架构文档路线图）；
- 公网部署需要对应平台权限，上线后仍需正式域名复核；
- 检索 Recall@5=100% 不代表端到端正确率 100%；Precision@5≈42% 含 Gold 标注不完整因素，需人工抽查区分。

## 7. 环境提醒（详见 AGENTS.md）

终端 GBK 乱码（写 UTF-8 文件再读取）、模型离线加载、浏览器用 `http://127.0.0.1:8000`；
业务代码边界 `scripts/ web/ miniprogram/`，生成数据 `endfield_kb/ output/ logs/`。
