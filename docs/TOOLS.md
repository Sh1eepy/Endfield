# 工具与命令

命令均从项目根目录执行。先复用现有工具；新增脚本后在对应类别补一行职责和最小用法。

## 数据构建

| 工具 | 职责 | 常用命令 |
|---|---|---|
| `wiki_collector.js` | 在已登录 WIKI 页面内采集块式数据 | 浏览器控制台运行，凭据不离开浏览器 |
| `build_kb_all.py` | 全量 JSON → 22 分类 JSONL/Markdown | `python scripts/build_kb_all.py` |
| `build_kb.py` | 旧版单分类构建，兼容保留 | `python scripts/build_kb.py --help` |
| `recipe_extract.py` | 提取完整配方库 | `python scripts/recipe_extract.py` |
| `recipe_index.py` | 配方加载、物品索引与名称解析库 | 由服务和评测导入 |
| `extract_media.py` | 提取封面、正文媒体、外链和引用 | `python scripts/extract_media.py` |
| `build_operator_details.py` | 生成干员结构化详情和语音 | `python scripts/build_operator_details.py` |
| `gen_jieba_dict.py` | 从条目名生成游戏专名词典 | `python scripts/gen_jieba_dict.py` |
| `remove_edge_background.py` | 指定素材的边缘连通底色透明化 | `python scripts/remove_edge_background.py --help` |

`inspect_wiki_entry.py` 用于检查单条 WIKI 数据；`search_chunks.py` 与 `extract_module.py` 只用于历史 SPA 逆向排查。

## RAG 与图谱

```powershell
# RAG 首次全量 / 日常增量
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --incremental

# 检索探针
python scripts/rag_search.py "天有洪炉需要什么材料" --top-k 5

# 图谱全量 / 增量 / 查询
python scripts/build_knowledge_graph.py
python scripts/build_knowledge_graph.py --incremental
python scripts/graph_search.py "陈千语和诀的关系"
```

| 模块 | 职责 |
|---|---|
| `rag_config.py` | embedding 和检索参数的单一来源 |
| `rag_prompts.py` | 生产 Prompt 与内容哈希版本 |
| `rag_search.py` | 名称、BM25、向量和 RRF 融合 |
| `intent_router.py` | 强规则意图识别与可选 LLM 兜底 |
| `rag_ask.py` | 枚举、结构化直查、语义规划、多路检索、生成与降级 |
| `llm_client.py` | OpenAI 兼容客户端、受限重试、续写、流式完成校验和操作预算；JSON 去参重试只处理明确的不支持错误 |
| `build_knowledge_graph.py` | 白名单关系提取、来源哈希与增量替换 |
| `graph_search.py` | 实体、关系和最多三跳证据路径 |
| `graph_aliases.json` | 人工审定别名 |

mention 反查由 `rag_ask.build_mention_index()` 懒构建并缓存到 `output/mention_index.json`，当前没有独立构建脚本。

## 服务与客户端

```powershell
# 推荐：单进程默认预热
python scripts/start_server.py

# 仅本地调试、无启动预热
python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000

# Web
Set-Location web
npm ci
npm test
npm run build
npm run dev
```

- `api_server.py`：FastAPI、静态托管、SSE、媒体代理和健康接口；
- `api_security.py`：令牌、SQLite 次数额度、代理客户端地址与管理接口保护；
- `start_server.py`：`.env` 预加载、worker、端口、代理信任和单进程预热；
- Web 说明见 [WEB.md](WEB.md)，小程序说明见 [MINIPROGRAM.md](MINIPROGRAM.md)。

## 审计、评测与反馈

```powershell
python scripts/rag_audit.py --fail-on-error
python scripts/graph_audit.py --fail-on-error
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
python scripts/eval_pipeline.py
python scripts/eval_answers.py
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/build_eval_manifest.py
python scripts/quality_gate.py
python scripts/quality_gate.py --require-versioned-results
```

`eval_rag.py` 和 `test_rag_semantic.py` 是早期或专项探针；正式回归以 `eval_retrieval.py`、`eval_pipeline.py`、`eval_answers.py` 和版本化门禁为准。

线上坏例闭环：

```powershell
python scripts/review_bad_cases.py list
python scripts/review_bad_cases.py approve <feedback_id> --route rag --facts "必要事实" --sources "可接受来源"
python scripts/replay_bad_cases.py --mode retrieval
python scripts/replay_bad_cases.py --mode pipeline --allow-llm
python scripts/replay_bad_cases.py --mode answer --allow-llm
```

- `rag_trace.py` 保存脱敏阶段数据和反馈隔离区；
- `rag_monitor.py` 汇总进程内请求与延迟指标；
- `eval_case.py` 统一固定评测和 Replay 的 Gold schema；
- `--allow-llm` 与 `eval_answers.py --judge` 会产生在线模型调用，普通离线测试不使用密钥。

完整测试矩阵和指标边界见 [TESTING.md](TESTING.md)。

文档移动或改名后运行 `python scripts/check_docs.py`，检查仓库 Markdown 中的本地相对链接；该工具不访问网络。

## 前端空间验收

`check_spatial_frontend.mjs` 使用现有 Playwright 与 Edge 对本地 5173 页面执行两种视口的截图、指针拾取、抽取/收回、几何坐标、等待反馈和上下文丢失检查。最小用法：`node scripts/check_spatial_frontend.mjs <playwright包目录> output/frontend-spatial/recheck`；不安装新依赖，查询响应仅在浏览器内模拟。证据与边界见 [空间升级验收](FRONTEND_SPATIAL_ACCEPTANCE.md)。

## 官方素材

`fetch_official_design_assets.py` 从公开官网 CDN 下载选定图片到 `web/assets/official/`，记录 URL、大小和 SHA256。它只下载图片，不执行官网脚本；运行需要网络权限。使用与版权边界见 [ASSETS.md](ASSETS.md)。
