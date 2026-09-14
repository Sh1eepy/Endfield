# 测试、评测与质量门禁

> 本文汇总分层测试策略、可执行验证命令、当前评测证据、前端验收结论与已知边界。
> 变更原因与批次摘要见 [CHANGELOG.md](CHANGELOG.md)，提交级细节见 [CHANGELOG_DETAIL.md](CHANGELOG_DETAIL.md)。

## 1. 分层策略

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

## 2. 技术选型

- 后端用标准库 `unittest`（`tests/` 与 `scripts/test_*.py`）：零额外依赖、可离线运行、不加载付费模型；
- 前端用 Vitest + jsdom（`web/tests/`）：需要 DOM 环境验证流式状态机、markdown 渲染与请求封装；
- 3D 连续运动、真实拾取和 canvas 生命周期不能只靠 jsdom：使用现有 Playwright + 本机 Edge 做浏览器验收，不安装额外 npm 依赖；
- 小程序用 `node --test`（`miniprogram/tests/`）：覆盖纯函数与请求封装，真机行为必须人工验收；
- 数据与指标靠脚本自证（`rag_audit.py`、`graph_audit.py`、`quality_gate.py`）：把"能不能发布"写成可执行断言；
- 单元测试与检索/路由/图评测默认离线，LLM、CDN、微信 API 一律打桩；`eval_answers.py` 在本地配置 LLM 时会生成在线答案，`--judge` 还会增加裁判调用，执行前必须得到明确授权。

## 3. 常用验证

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

索引或问答改动再运行：

```powershell
python scripts/rag_audit.py --fail-on-error
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
python scripts/eval_pipeline.py
python scripts/graph_audit.py --fail-on-error
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/quality_gate.py
python scripts/quality_gate.py --require-versioned-results
```

Web 空间改动另启动 Vite，然后运行 `node scripts/check_spatial_frontend.mjs <playwright 包目录> output/frontend-spatial/recheck`。输出为可重建本地产物，默认不提交；结论必须同时报告视口、抽取/收回、拾取、触摸降级和未验证边界。

## 4. 当前证据与解释

- 2026-09-14 构建报告记录 2,229 个来源、2,405 个图实体、10,076 条关系；增量构建与全量重建逻辑等价；
- 71 条严格检索集快照为 Recall@5 98.59%、MRR 97.89%、Precision@5 45.35%（`final_reviewed.json` 的 `overall`）；唯一未命中为多系列任务比较困难样本；
- 25 条离线路由集 route accuracy 为 92%；图专项固定集 10/10，自动关系问法审查 1,662/1,662；
- 当前 manifest 下的在线答案黄金集 6 条：拒答正确率、必要事实覆盖、引用/结构化溯源均为 100%，来源重合 66.67%；未启用可选 LLM judge，样本量不足以代表生产端到端正确率；
- 2026-09-14 后端更新通过 64 项主测试、85 项后端专项测试、图固定集 10/10、关系问法 1,662/1,662；严格版本门禁 `--require-versioned-results` 通过，0 失败、0 警告。随后文档分层调整新增 9 项详细日志脚本测试，当前主测试为 **73 项**，后端专项仍为 85 项；
- `output/eval/final_reviewed.json`、`pipeline_result.json`、`answer_result.json` 与 `graph_result.json` 已按当前 manifest 重跑，四份结果的 `manifest_id` 一致。HTTP 冒烟验证无资料问题返回标准拒答且 `rejected=true`，新干员"提弗洛斯"可生成带引用答案。

以上证据的逐条命令、原始返回、manifest 绑定与服务状态快照见 §5。

## 5. 最近一轮更新证据（2026-09-14）

本轮覆盖 WIKI 快照更新、生成门槛校准、严格门禁与在线验证；公网部署与真机验收仍未进行。

### 5.1 输入、产物与增量对照

- 新快照 `endfield_wiki_full_2026-09-14.json`（SHA256 `72290993EEFD05EEB97AC640B9F568F087B00A07692691E666C2F6DC0BD70A27`）：目录 2,229 条 / 详情 2,229 条、`detail_failed=0`、稳定 ID 无缺失或重复；
- 相对 2026-08-07 快照：新增 284、下线 13、变化 1,040、改名 30、跨分类移动 0；差分由 `scripts/diff_wiki_snapshots.py` 生成（`output/update_20260914/wiki_delta.json`）；
- 产物规模：规范化知识库 22 类 2,229 条、配方 345 条（忽略内部流水号后业务内容无变化）、干员详情 33 名、RAG 4,764 个来源记录（含 2,535 条中文干员语音）与 8,300 chunks、mention 1,950 个被提及实体与 13,809 条反向提及关系、图谱 2,405 实体 / 1 别名 / 10,076 关系 / 2,229 来源；
- RAG 增量重新 embedding 2,136 个 chunk、删除 17 个旧 chunk；与空目录全量重建的 chunk ID、文本、元数据、BM25 分片一致，向量库最大绝对差约 `2.09e-7`（浮点重算噪声）；
- 图谱首次对照发现增量版残留 13 个已下线来源的实体；修复"来源下线只删关系不删实体"后，依赖它的现存来源一并重建，`entities`、`aliases`、`relations`、`manifest` 四张逻辑表与全量版一致；
- mention 反查缓存改为保存规范化知识源指纹，旧格式或指纹不符时自动重建，RAG 审计不再把"文件存在"误判为"缓存新鲜"。

### 5.2 生成门槛校准（0.30 → 0.45）

`prepare_generation()` 在调用生成前判定拒答：实体直取命中，或命中片段含关键词/mention/直取/关系证据等人工确认上下文时不拒答；其余情况 top-1 向量相似度低于 `GENERATION_MIN_VECTOR_SIM=0.45`（`scripts/rag_config.py` 单一来源）即返回标准拒答文案。

| 问题 | top-1 向量相似度 | 0.30 门槛（旧基线） | 0.45 门槛（当前） |
|---|---:|---|---|
| 资料里完全没有的火星城市什么时候开放？ | 0.4113 | **误放行**：`rejected=false` 进入生成（旧基线同题 top-1 为 0.419） | `rejected=true` 标准拒答 |
| 不存在的材料量子香蕉怎么合成？ | 0.0（首条命中） | 拒答（低于两个门槛，未被误放） | `rejected=true` 标准拒答 |

校准前对照取自 `output/update_20260914/baseline/answer_result.json`（旧索引、旧门槛、在线生成）：只有"火星城市"一条因首条相似度高于 0.30 进入生成，另两条拒答案例在旧门槛下已正确拒答。`output/update_20260914/answer_result_offline.json` 是无 LLM 配置时的离线产物，不产生生成结果，其拒答正确率 66.67%、引用覆盖 33.33% 反映降级链路而非门槛，不作为校准依据。

### 5.3 在线答案验证（当前 manifest，6 条）

| 问题 | 路线 | top-1 相似度 | `rejected` | 判定 |
|---|---|---:|---|---|
| 重息壤是什么？ | rag / rule | 1.0 | false | 必要事实、引用、来源重合通过 |
| 佩丽卡怎么玩？ | rag / semantic_fallback | 1.0 | false | 必要事实、引用通过；来源重合未通过 |
| 解锁武陵需要做什么任务？ | rag / semantic_fallback | 0.85 | false | 必要事实、引用通过；来源重合未通过 |
| 终末地目前有哪些主线任务？ | enum（确定性） | — | false | 结构化枚举，按结构化溯源评测 |
| 不存在的材料量子香蕉怎么合成？ | rag | 0.0 | true | 标准拒答，未伪造引用 |
| 资料里完全没有的火星城市什么时候开放？ | rag | 0.4113 | true | 标准拒答，未伪造引用 |

汇总（`output/eval/answer_result.json`）：`refusal_correct=1.0`、`required_terms_coverage=1.0`、`citation_present=1.0`、`source_overlap=0.6667`、`judge_coverage=0.0`、`n=6`。本轮未启用可选 LLM judge；确定性枚举/结构直查按结构化溯源评测，不伪造引用角标。

### 5.4 严格门禁、测试复核与回滚材料

```powershell
python scripts/quality_gate.py --require-versioned-results   # {"passed": true, "failures": [], "warnings": []}
python -m unittest discover -s tests                         # Ran 64 tests — OK（该轮次快照）
python -m unittest scripts.test_query_routes scripts.test_api_security scripts.test_rag_trace scripts.test_ask_stream scripts.test_backend_remediation
                                                            # Ran 85 tests — OK
```

- 检索、路由、答案、图四份结果绑定同一 manifest：`eval_manifest.json` 的 `manifest_id = sha256:83b170c9fe0378a24db652be2583b4d6f4c3440ea012463a5ce10c55386e98d4`，索引 `index_manifest_sha256 = 04585f547f018b079fb75e58a74d724e6a4cbebbeeb8f412b349599ae7a11540`，`final_reviewed.json`、`pipeline_result.json`、`answer_result.json`、`graph_result.json` 的元数据均与之一致；
- 回滚材料在 `output/update_20260914/`：`baseline/`（更新前正式产物备份）、`official_rag_pre_publish/`（发布前 RAG）、`rag_full/`（全量对照 RAG）、`graph_incremental/` 与 `graph_full/`（图谱对照）；当前评测产物在 `output/eval/`、`output/rag/audit_report.json`、`output/knowledge_graph/audit_report.json`；
- `output/update_20260914/` 是本机过程产物，约 282 MB / 369 个文件（向量库约 120 MB），被 `.gitignore` 的 `output/update_*/` 整体忽略；需要时按本节命令重新生成，不要用 `git add -f` 强行入库。

### 5.5 当前服务状态（复核快照）

| 项目 | 值 |
|---|---|
| 启动方式 | `python scripts/start_server.py`，单 worker，预热 embedding 与索引 |
| 监听 | `0.0.0.0:8000`（本机访问用 `http://127.0.0.1:8000`） |
| 进程 | PID 118244，启动于 2026-09-14 18:35:42 |
| `GET /api/health` | `{"status": "ok", "service": "endfield-wiki-agent"}` |
| `GET /api/health/deep` | `consistent=true`、`issues=[]`、`checked_at 2026-09-14T10:41:45Z` |
| 索引 | `index_built_at 2026-09-14T09:30:25Z`、`source_fingerprint e93019dd…`、manifest 4,764 条 / 8,300 chunks、Chroma 8,300、BM25 无不一致分类 |
| 图谱 | 2,405 实体、1 别名、10,076 关系、2,229 来源 |
| LLM | `deepseek-v4-flash`，密钥已配置，单次超时 60s、单操作总预算 75s |

HTTP 冒烟记录在 `logs/server_20260914.stdout.log`：`/api/names`、`/api/synthesis`（提弗洛斯、喽切娜、重息壤）与 3 次 `POST /api/ask` 均返回 200。这是本机开发服务，不是公网部署。

## 6. 前端验收证据

### 6.1 空间层实现（2026-09-12）

- 开场主时间轴 6 秒后释放遮罩，8 秒安全超时；支持 Esc、跳过、重播、会话一次与减少动态效果；
- Home、200px 桌面 / 130px 手机过渡区与 Query 共享一个 sticky canvas，滚动进度驱动取景和纹理显露，不劫持页面滚动；页面原生上下滚动以每屏 0.22 rad 驱动缓慢旋转；
- 56 个档案展示载体组成双螺旋，载体、骨架与连线使用同一连续波形，骨架为可更新折线；中段半径 6.4 的主金属环与两条辅环静止，螺旋在共同父级中心旋转；指针映射 yaw ±0.58、pitch ±0.13 rad，复用原有 5/s 平滑；
- 档案玻璃主体 3.2 × 1.6 × 0.42、边框深度 0.46；EffectComposer 使用最高 4x MSAA 渲染目标；选中轮廓挂在载体本地坐标，抽取锁定真实世界位置与旋转，收回接续载体世界姿态；
- 查询后立即出现不确定进度条与已等待秒数（使用现有 `phase_text`，不编造完成百分比），SSE 阶段消息不会提前停止等待反馈，保留停止按钮；内容展开时不显示"档案内容已就绪"，跳过抽取按钮在 extraction ≥ 0.64 后隐藏，静态与减少动态效果也隐藏；
- 可见且未展开内容时阵列持续轻微运动，稳定阅读后停止渲染，滚动/尺寸/模式变化补画；离屏、后台、静态、上下文丢失和减少动态效果保留降级路径，未声称降低固定功耗百分比；
- 手机不响应触摸指针及阵列拖动，保留 `pan-y`，用 ↑↓ 按钮浏览；桌面继续支持鼠标拖动和拾取；档案载体不与知识条目、配方或编号建立数据绑定，编号只表示展示对象。

### 6.2 视觉细化与轮播（2026-09-13 / 2026-09-14 增补）

- 首页五位角色（佩丽卡、管理员、莱万汀、陈千语、艾尔黛拉）每 8 秒循环切换；手动选择（含重复点击当前角色）重新计时，固定按钮变黄并暂停，取消固定后重新等待 8 秒；固定期间仍可手动换人且固定状态保持，后台标签页暂停轮播、返回后重新计时，固定状态不跨刷新；素材来源与哈希见 [ASSETS.md](ASSETS.md)；
- Query 使用独立官方轨道展示图（配方模式 22% 上限正片叠底、问答模式 16% 上限滤色，跟随章节进度淡入）；标题用本地 Noto Sans SC，英文标识与数字用 Oxanium，正文 16px、表格 14px、辅助文字 11–13px；
- 干员信息、技能表、物品结构表采用黄灰底色、细边框、交替行底色与一致滚动条；三环共享指针及页面滚动微移，每环另有不同频率与幅度的轻微摆动；档案盒沿高度错相波动（径向 0.32、纵向 0.22 世界单位），骨架与横向连接线同步更新。

### 6.3 自动测试与浏览器证据

- `npm run build` 通过，保留既有 Three.js 动态包超过 500 kB 的提示；`npm test` 9 文件 42 项通过，`python -m unittest tests.test_frontend_contract` 10 项通过；
- 2026-09-14 轮播增补后前端测试 44/44、生产构建通过；新增测试覆盖五人循环、手动重新计时、固定/取消固定、固定中换人、后台暂停及卸载清理；
- 浏览器证据用现有 Playwright + 本机 Edge headless、真实 WebGL 渲染，视口 1440×900 与 390×844；截图与 JSON 为可重建本地产物，不进入普通 Git 历史；

| 检查 | 1440×900 | 390×844 |
|---|---|---|
| canvas / 页面异常 / 横向溢出 | 1 / 0 / 无 | 1 / 0 / 无 |
| 查询等待条 | 可见 | 可见 |
| 页面抽取 → 收回 | 1.000 → 0.000 | 1.000 → 0.000 |
| 稳定阅读 600ms 内帧数变化 | 0 | 0 |
| 环在 -0.58 / 0 / +0.58 yaw 下投影边界 | 均在视口内 | 均在视口内 |
| 固定姿态抽取起点 / 收回起点误差 | 均为 0 | 均为 0 |
| 收回后可见载体 / 位置恢复误差 | 56 / 0 | 56 / 0 |
| WebGL 上下文丢失 | canvas 清理 | canvas 清理 |

- 场景内三个角度对载体中心做 raycast：桌面每档 15/15/16 个中心命中自身，手机 36/33/34（背面可能被前排遮挡，不是所有中心都应命中自身）；真实桌面 UI 另以鼠标点击确认选中编号改变、轮廓随盒子朝向贴合；
- 手机触摸事件前后 pointerX 均为 0、`touch-action` 为 `pan-y`（浏览器触摸仿真）；固定按钮底色为 `rgb(255, 250, 0)`；浏览器内直查样例覆盖莱万汀详情、能力扩延、属性与精英化材料表，以及协议圆盘的知识库来源/用途卡。

### 6.4 前端验证边界

- 查询动画验证使用浏览器拦截的延迟 SSE 示例，显式标注为测试内容、不是实际知识答案，未调用付费模型，不代表真实 LLM 首字时延或答案质量；空间脚本同样使用模拟查询响应；
- 触摸结论来自浏览器触摸仿真，不是 Android/iOS 真机手感验证；内置浏览器连接真实后端的检查仅限上述直查样例，未评估在线 LLM 回答质量；
- 固定姿态世界坐标验证与页面交互测试分开记录，没有把几何单测当作完整页面点击测试；无 WebGL 与减少动态效果有组件测试，浏览器本轮主要验证上下文丢失后的降级与偏好切换；
- 未测硬件 GPU 功耗、长期显存变化、60fps 保证、手机真机、离屏/后台调度的全组合；
- 仍使用已有约 17.8 MB 中文字体，未新增字体、模型或第三方依赖，未修改 API、配方 JSON、知识库及图谱。

## 7. 易误判问题

- 高 Recall 只说明固定查询的相关来源进入 Top-K，不说明回答事实、完整性或引用正确；本轮 Recall@5 98.59% 且唯一未命中是多系列任务比较困难样本，仍不能外推为自然语言问题的正确率；
- Precision 较低可能包含 Gold 标注不完整，需人工区分噪声召回与漏标；
- 模拟 LLM、CDN 和微信 API 的离线测试不等于真实网络或真机验收；
- 单次或缓存后的毫秒数不能当 p95；冷启动、warm 请求和在线规划应分开记录；
- LLM judge 只能辅助金标，需要版本化 Prompt 和人工双标校准；
- 临时目录不可写（受限沙箱、磁盘满、权限收紧）时，依赖 SQLite 临时库的额度与 Trace 用例会报 `unable to open database file`，表现为大面积失败；先确认临时目录可写（升级权限或把 `TEMP`/`TMP` 指向可写目录），再判断是否为代码回归。

## 8. 历史问题与对策

| 曾经的问题 | 对策 | 保护位置 |
|---|---|---|
| 实体被解析成更短的名称（"重息壤"→"息壤"） | 完整名称优先，并保留真实 `item_id` | `test_backend_remediation.py`（EntityTests） |
| 条目缩短后旧 chunk 残留在向量库 | `diff_chunks()` 比较新旧 chunk 全集差集后删除 | `test_backend_remediation.py`、`tests/test_build_rag.py` |
| 来源下线后图谱实体或依赖关系残留 | 删除来源实体，并重建仍引用它的现存来源 | `tests/test_graph_rag.py` |
| mention 缓存存在但对应旧知识库 | 缓存保存知识源指纹，审计校验新鲜度 | `tests/test_graph_rag.py`、`rag_audit.py` |
| 流式普通 EOF 被当成回答完成 | 只接受受支持 `finish_reason`；截断最多续写一次 | `test_ask_stream.py`、`test_backend_remediation.py` |
| 未执行的流式响应占住名额并扣额度 | 准入进入 ASGI 响应生命周期，响应层与 worker 只交接/释放一次 | `test_ask_stream.py` |
| 重试/续写突破时间上限 | 单次操作共享 `LLM_TOTAL_TIMEOUT`（默认 75s）预算 | `test_backend_remediation.py` |
| 普通 400 被误当作 JSON 格式不兼容并重发 | 只对明确的 `response_format/json_object` 不支持错误降级 | `test_ask_stream.py` |
| 评测用回答措辞猜拒答导致误判 | 当前结果严格使用 `rejected`，完整标准文案仅兼容旧产物 | `test_backend_remediation.py` |
| 普通向量召回相关度弱却进入生成 | `GENERATION_MIN_VECTOR_SIM=0.45` 在调用生成前拒答，确定性来源不受影响 | `test_ask_stream.py` |
| 模式切换自动提交草稿、流式 Markdown 重复解析 | 切换只恢复状态；流式纯文本，完成后一次解析 | `test_frontend_contract.py`、Vitest |
| 小程序引用拆坏表格或漏媒体/link | 表格整块解析，统一 inline 映射和媒体代理 | `miniprogram/tests/ask.test.cjs` |
| 媒体代理直接回传 SVG/HTML | MIME 白名单 + 拒绝重定向 + CSP | `test_api_security.py` |
| 门禁放行缺少 manifest 的历史成绩 | `quality_gate.py --require-versioned-results` | `quality_gate.py`、CI |
| 冷启动耗时被当作稳态性能 | 冷启动、warm 请求、在线规划分别记录 | 本文件「易误判问题」 |

## 9. 新改动的最低验证

- 配方逻辑：全量树不变量 + API 测试；
- RAG/图谱：针对性单测 + 审计 + 固定评测 + manifest；
- SSE/LLM：正常结束、中断、长度截断、续写、超时、断开与降级；
- Web：Vitest + 生产构建 + 1440×900、390×844、减少动画、WebGL 降级；3D 变换还要验证拾取、轮廓、抽取与收回；
- 小程序：Node 测试 + Android/iOS 真机的长答案、媒体、后台切换、弱网和树手势；
- 部署：配置静态测试 + 容器健康 + 正式域名的配方、整包问答和 SSE 实测。

## 10. 未验证边界

1. 在线答案集只有 6 条，只验证固定链路与已知拒答边界，不能作为生产回答准确率；
2. 本轮未启用 LLM judge，忠实度没有独立裁判证据；
3. 公网 HTTPS 域名下的健康检查、配方、整包问答、SSE、代理 IP 与持久卷仍未验收；
4. 微信小程序真机（长答案、图片/音频、弱网、后台切换、Canvas 手势）仍未验收；
5. 前端侧未验证项见 §6.4：真机触摸手感、GPU 功耗/显存长时行为、60fps 保证与在线 LLM 回答质量均无证据。
