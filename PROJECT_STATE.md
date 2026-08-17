# PROJECT_STATE.md — 项目状态交接（AI 继续工作前请先读本文件 + AGENTS.md）

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
| RAG 索引 | `output/rag/` | 当前 3032 chunks；ChromaDB 向量 + BM25 按分类分片 + chunks.json manifest |
| RAG 增量更新 | `build_rag.py --incremental` | 内容 hash 对比 → 只重 embedding 变更条目 → 只重建变更分类 BM25 分片 |
| 合成树 API | `api_server.py /api/synthesis` | 物品合成树 / 设备配方卡 / 歧义→候选列表 / 无配方→知识库信息；叶子=基础资源，配方≤2，深度≤10，循环剪枝 |
| 名称建议 | `api_server.py /api/names` | 全部名称（配方物品+设备+知识库条目，1908 个），前端模糊搜索联想 |
| 媒体结构库 | `output/item_media.json` | extract_media.py 提取：封面图 1957 / 正文图 2046 / 外链 291 / 引用 14693（含数量与链接样式） |
| 前端 | `web/index.html` | 深色工业 HUD，配方树/知识问答双模式；搜索联想、节点封面图、引用卡片与结构化知识卡 |
| 评测 | `eval_retrieval.py` | 71 条查询；当前 Recall@5=92.96%、MRR=89.48%（早期 6 条评测已废弃为基准） |

## 3. 关键文件地图
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
- `web/index.html` → 前端（双模式：配方合成树 + 知识问答，深色工业 HUD）
- `.env` → 可选（LLM 相关配置，私密勿提交）；`.gitignore` + `.env.example` → 密钥安全

## 4. 关键技术结论
- 合成树剪枝规则：叶子=基础资源（免费资源清水/惰气/息壤气 + 无产出配方矿物 + **种子类**）；每个物品最多 2 个配方（排除自循环）；循环/超深分支直接剪掉，不显示"已截断"；植物类（芽针/锦草等）正常展开种植机配方；**无配方物品回退知识库返回物品信息**
- RAG 增量：条目级 `content_hash`（md5）→ manifest 对比 → ChromaDB upsert/delete → BM25 按分类分片只重建变更分类
- 设备（如"天有洪炉"）走 `/api/synthesis` 的设备分支 → 配方卡片（原料/产物/耗时）

## 5. 收尾路线（执行中）
1. ✅ **阶段 1**：统一文档口径、审计敏感文件、建立 Git 基线
2. ⏳ **阶段 2**：补后端/API/合成树自动化测试并修复发现的问题
3. ⏳ **阶段 3**：合成树展开/收起、节点跳转、搜索历史与前端验证
4. ⏳ **阶段 4**：双实体召回优化、评测集人工抽检并记录新指标
5. ⏳ **阶段 5**：Docker 与部署配置、端到端验收

每个阶段的决策、验证方式和维护方法记录在 `PROJECT_PROGRESS.md`。

## 6. 环境与纪律提醒（详见 AGENTS.md）
- 终端 GBK 乱码 → 写 UTF-8 文件再读取；模型离线加载；浏览器用 127.0.0.1
- 边界：只改 `scripts/ web/ endfield_kb/ output/ logs/`
