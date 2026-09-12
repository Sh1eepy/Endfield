# 测试、评测与质量门禁

## 分层策略

| 层级 | 验证内容 | 主要入口 |
|---|---|---|
| 单元与契约 | 配方不变量、路由、索引差异、API 参数、Trace、前端契约 | `unittest`、Vitest、Node test |
| Web 空间浏览器验收 | 视口、拾取、抽取/收回、等待反馈、触摸策略、上下文丢失 | `check_spatial_frontend.mjs` + Edge WebGL |
| 数据一致性 | KB、manifest、Chroma、BM25、mention、图谱 | `rag_audit.py`、`graph_audit.py` |
| 检索评测 | Recall@K、MRR、Precision@K | `eval_retrieval.py` |
| 路由评测 | 意图与实际 route | `eval_pipeline.py` |
| 答案评测 | 必要事实、引用、拒答、可选 judge | `eval_answers.py` |
| 发布门禁 | 版本、索引一致性和指标阈值 | `quality_gate.py --require-versioned-results` |
| 端侧验收 | 响应式、交互、弱网、媒体、触控 | 浏览器与微信真机 |

## 技术选型

- 后端用标准库 `unittest`（`tests/` 与 `scripts/test_*.py`）：零额外依赖、可离线运行、不加载付费模型；
- 前端用 Vitest + jsdom（`web/tests/`）：需要 DOM 环境验证流式状态机、markdown 渲染与请求封装；
- 3D 连续运动、真实拾取和 canvas 生命周期不能只靠 jsdom；使用现有 Playwright + Edge 运行本地浏览器验收，不安装额外 npm 依赖；
- 小程序用 `node --test`（`miniprogram/tests/`）：覆盖纯函数与请求封装，真机行为必须人工验收；
- 数据与指标靠脚本自证（`rag_audit.py`、`graph_audit.py`、`quality_gate.py`）：把"能不能发布"写成可执行断言；
- 默认全部离线：LLM、CDN、微信 API 一律打桩；只有显式 `--allow-llm` 或 `--judge` 才会产生在线调用与费用。

## 常用验证

```powershell
python -m unittest discover -s tests -v
python -m unittest scripts.test_query_routes scripts.test_api_security scripts.test_rag_trace scripts.test_ask_stream scripts.test_backend_remediation -v
python -m compileall -q scripts tests
python scripts/check_docs.py
node --test miniprogram/tests/ask.test.cjs
Set-Location web
npm test
npm run build
```

Web 空间改动另启动 Vite，然后运行 `node scripts/check_spatial_frontend.mjs <playwright包目录> output/frontend-spatial/recheck`。输出为可重建本地产物，默认不提交；结论必须同时报告视口、抽取/收回、拾取、触摸降级和未验证边界。

索引或问答改动再运行：

```powershell
python scripts/rag_audit.py --fail-on-error
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
python scripts/eval_pipeline.py
python scripts/graph_audit.py --fail-on-error
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/quality_gate.py
```

## 当前证据与解释

- 2026-09-08 构建报告记录 1,958 个来源、2,129 个图实体、9,358 条关系；
- 71 条严格检索集的整改后快照为 Recall@5 100%、MRR 98.36%、Precision@5 45.35%；
- 25 条离线路由集 route accuracy 为 92%；图专项固定集 10/10，自动关系问法审查 1,656/1,656；
- 答案黄金集只有 6 条，不能代表生产端到端正确率；
- 2026-09-08 后端整改报告记录基础、专项、组合回归和质量门禁通过；2026-09-09 Web 与小程序视觉改动已提交，但小程序真机与公网正式域名仍待验收。

`output/eval/final_reviewed.json` 与 `answer_result.json` 是缺少 manifest 元数据的历史基线。普通门禁允许它们带警告通过；严格发布门禁会拒绝。只有人工复核并按当前 manifest 重跑后，才能称为正式发布基线。

## 易误判问题

- Recall 100% 只说明固定查询的相关来源进入 Top-K，不说明回答事实、完整性或引用 100% 正确；
- Precision 较低可能包含 Gold 标注不完整，需人工区分噪声召回与漏标；
- 模拟 LLM、CDN 和微信 API 的离线测试不等于真实网络或真机验收；
- 单次或缓存后的毫秒数不能当 p95；冷启动、warm 请求和在线规划应分开记录；
- LLM judge 只能辅助金标，需要版本化 Prompt 和人工双标校准。

## 历史问题与对策

| 曾经的问题 | 对策 | 保护位置 |
|---|---|---|
| 实体被解析成更短的名称（"重息壤"→"息壤"） | 完整名称优先，并保留真实 `item_id` | `test_backend_remediation.py`（EntityTests） |
| 条目缩短后旧 chunk 残留在向量库 | `diff_chunks()` 比较新旧 chunk 全集差集后删除 | `test_backend_remediation.py`、`tests/test_build_rag.py` |
| 流式普通 EOF 被当成回答完成 | 只接受受支持 `finish_reason`；截断最多续写一次 | `test_ask_stream.py`、`test_backend_remediation.py` |
| 未执行的流式响应占住名额并扣额度 | 准入进入 ASGI 响应生命周期，响应层与 worker 只交接/释放一次 | `test_ask_stream.py` |
| 重试/续写突破时间上限 | 单次操作共享 `LLM_TOTAL_TIMEOUT`（默认 75s）预算 | `test_backend_remediation.py` |
| 普通 400 被误当作 JSON 格式不兼容并重发 | 只对明确的 `response_format/json_object` 不支持错误降级 | `test_ask_stream.py` |
| 评测用回答措辞猜拒答导致误判 | 当前结果严格使用 `rejected`，完整标准文案仅兼容旧产物 | `test_backend_remediation.py` |
| 模式切换自动提交草稿、流式 Markdown 重复解析 | 切换只恢复状态；流式纯文本，完成后一次解析 | `test_frontend_contract.py`、Vitest |
| 小程序引用拆坏表格或漏媒体/link | 表格整块解析，统一 inline 映射和媒体代理 | `miniprogram/tests/ask.test.cjs` |
| 媒体代理直接回传 SVG/HTML | MIME 白名单 + 拒绝重定向 + CSP | `test_api_security.py` |
| 门禁放行缺少 manifest 的历史成绩 | `quality_gate.py --require-versioned-results` | `quality_gate.py`、CI |
| 冷启动耗时被当作稳态性能 | 冷启动、warm 请求、在线规划分别记录 | 本文件「易误判问题」 |

## 新改动的最低验证

- 配方逻辑：全量树不变量 + API 测试；
- RAG/图谱：针对性单测 + 审计 + 固定评测 + manifest；
- SSE/LLM：正常结束、中断、长度截断、续写、超时、断开与降级；
- Web：Vitest + 生产构建 + 1440×900、390×844、减少动画、WebGL 降级；3D 变换还要验证拾取、轮廓、抽取与收回；
- 小程序：Node 测试 + Android/iOS 真机的长答案、媒体、后台切换、弱网和树手势；
- 部署：配置静态测试 + 容器健康 + 正式域名的配方、整包问答和 SSE 实测。
