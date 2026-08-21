# 项目状态

> 2026-08 更新。项目 = **《明日方舟：终末地》配方合成树**。
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
| RAG 索引 | `output/rag/` | 当前 3402 chunks；ChromaDB 向量 + BM25 按分类分片 + chunks.json manifest |
| RAG 增量更新 | `build_rag.py --incremental` | 内容 hash 对比 → 只重 embedding 变更条目 → 只重建变更分类 BM25 分片 |
| 合成树 API | `api_server.py /api/synthesis` | 物品合成树 / 设备配方卡 / 歧义→候选列表 / 无配方→知识库信息；叶子=基础资源，配方≤2，深度≤10，循环剪枝 |
| 名称建议 | `api_server.py /api/names` | 全部名称（配方物品+设备+知识库条目，1908 个），前端模糊搜索联想 |
| 媒体结构库 | `output/item_media.json` | extract_media.py 提取：封面图 1957 / 正文图 2046 / 外链 291 / 引用 14693（含数量与链接样式） |
| 前端 | `web/index.html` | 白色工业档案风格：纵向图片配方树、干员详情、机械开场和响应式布局 |
| 微信小程序 | `miniprogram/` | 首页联想与历史、配方/问答独立查询、Canvas 合成树、知识问答证据与干员档案；静态检查已通过，待开发者工具和真机验收 |
| 干员详情库 | `output/operator_details.json` | 31 名干员；基本信息、富文本颜色、技能/天赋/潜能/档案多 Tab、图片与多语种语音 |
| 轻量 GraphRAG | `output/knowledge_graph/graph.db` | 2,129 实体 / 9,358 条可追溯关系；覆盖人物/任务/地点/物品/设备/配方与明确亲属关系，支持解释性关系混合取证、增量更新与问法对称门禁 |
| 评测 | `eval_retrieval.py` | 71 条查询；当前 Recall@5=100%、MRR=97.3%（`final_reviewed.json`） |

## 3. 关键文件地图
- `KNOWLEDGE_SYSTEM_ARCHITECTURE.md` → RAG、知识图谱、结构化查询、LLM 调用与质量门禁总览
- `RAG_UPGRADE_PLAN.md` → RAG 优化计划与进度；`RAG_DEVLOG.md` → 开发决策/踩坑记录
- `scripts/build_kb_all.py` → WIKI 全量 JSON → `endfield_kb/`（22 分类 jsonl+md）
- `scripts/recipe_extract.py` → 全量 JSON → `output/recipes.json`（配方）
- `scripts/recipe_index.py` → 配方索引工具（load_recipes/build_item_index/find_item_ids_by_name）
- `scripts/extract_media.py` → 全量 JSON → `output/item_media.json`（封面图/正文图/外链/引用）
- `scripts/build_rag.py` → RAG 构建/增量（--reset 全量 / --incremental 增量）
- `scripts/rag_search.py` → 混合检索（向量+BM25 分片 → RRF）
- `scripts/api_server.py` → FastAPI（/api/synthesis、/api/names、/api/ask、/api/health + 静态托管）
- `scripts/llm_client.py` → 在线 LLM 统一客户端（OpenAI 兼容，密钥走 .env）
- `scripts/intent_router.py` → 意图识别分层（L1 规则 + L3 LLM 兜底）
- `scripts/rag_ask.py` → 问答路由（枚举/结构化直查/多路检索/实体直取 → LLM 生成）
- `scripts/gen_eval_set.py` → 评测集自动生成；`scripts/eval_retrieval.py` → 检索评测
- `scripts/gen_jieba_dict.py` + `scripts/dict_zh.txt` → 游戏专有名词词典
- `output/eval/` → 评测集与历次评测结果；`output/mention_index.json` → mention 反查索引
- `web/index.html` → 前端（纵向图片配方树 + 知识问答 + 干员详情）
- `miniprogram/` → 微信小程序端；`miniprogram/README.md` 记录开发、真机与发布方法
- `.env` → 可选（LLM 相关配置，私密勿提交）；`.gitignore` + `.env.example` → 密钥安全

## 4. 关键技术结论
- 合成树剪枝规则：叶子=基础资源（免费资源清水/惰气/息壤气 + 无产出配方矿物 + **种子类**）；每个物品最多 2 个配方（排除自循环）；循环/超深分支直接剪掉，不显示"已截断"；植物类（芽针/锦草等）正常展开种植机配方；**无配方物品回退知识库返回物品信息**
- RAG 增量：条目级 `content_hash`（md5）→ manifest 对比 → ChromaDB upsert/delete → BM25 按分类分片只重建变更分类
- 设备（如"天有洪炉"）走 `/api/synthesis` 的设备分支 → 配方卡片（原料/产物/耗时）
- 知识问答不是开放式 Agent：当前为确定性路由 + 可选查询改写/生成。开放问题通常 2 次 LLM，
  图关系通常 1 次，结构化直查可 0 次；是否增加补检索循环由困难集收益决定。
- 长条目生成不再固定截取开头，使用 `focus_long_context()` 从全文分散选择覆盖各子问题的证据窗口。

## 5. 当前发布边界

- 仓库已经具备可复现 Dockerfile、Railway 配置、依赖锁定和部署说明。
- 2026-08-21 已完成本地 Docker 镜像构建与容器运行验证，服务可正常启动。
- GitHub remote 已连接到 `https://github.com/Sh1eepy/Endfield.git`。
- Railway 尚未配置项目权限。下一步按 `DEPLOYMENT.md` 本地验镜像或发布。
- 小程序主体功能已接入同一套 FastAPI；模拟器默认访问本机，正式发布前还需配置线上 HTTPS API 域名并完成真机验收。

每个阶段的决策、验证方式和维护方法记录在 `PROJECT_PROGRESS.md`。

## 6. 环境提醒（详见 AGENTS.md）
- 终端 GBK 乱码 → 写 UTF-8 文件再读取；模型离线加载；浏览器用 127.0.0.1
- 边界：业务代码位于 `scripts/ web/ miniprogram/`，生成数据位于 `endfield_kb/ output/ logs/`
