# 项目审查与分阶段改造计划

日期：2026-09-08。状态：**审查与计划，尚未实施业务改造**。

建议先修正实体定位、索引增量一致性、流式完成判断和评测门禁，再优化检索热点；视觉改造先产出可比较的页面原型，再接回真实数据。现有 FastAPI、React SVG、SQLite 图谱都有保留价值，当前证据不支持整体推倒重写。

## 1. 版本与审查边界

- 当前分支：`codex/update`。
- 当前业务基线：`4a4ec99bb625340fbdb871b9f8e48016a8923af8`（2026-09-03，fix: prevent truncated and misrouted RAG answers）。
- 审查开始及报告整理时，Git 已跟踪文件无未提交修改。本轮新增内容只在 `output/audit_20260908/`；重跑构建更新了被忽略的 Web dist。
- 原有未跟踪目录包括设计工具包、官网离线页面和个人目录，不应使用 `git add .` 把它们一起提交。本轮没有创建新业务 commit，也没有改写历史。
- 已建立文件清单及指纹，检查 HTTP 入口、安全策略、配方链、在线检索/生成、图查询、索引构建/更新、评测和追踪、部署配置，以及 Web/小程序关键页面与请求逻辑。清单不等于逐行形式化验证；历史采集工具以数据流和入口检查为主。
- 已观察当前 Web 首页截图；没有完成小程序真机测试、公网部署验证、压力测试或新的在线 LLM 答案评测。没有据此声称“所有安全问题已排除”。
- 官网网页抓取失败，浏览器读取多次超时。已改用项目保存的官网 HTML/CSS/资源引用，结合其他官网与开源仓库资料。**没有证据证明官网触发了反爬，也没有测得官网动效帧率。**

证据与复现脚本：[output/audit_20260908/inventory.json](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/inventory.json>)、[output/audit_20260908/probe.py](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/probe.py>)。

## 2. 已测得的基线

| 检查 | 本轮结果 | 如何理解 |
|---|---|---|
| 后端基础测试 | 56/56 通过 | 现有自动测试通过，不覆盖本报告所有新发现 |
| 路由、安全、Trace、流式测试 | 61/61 通过 | 全部离线，不调用付费模型 |
| Web 测试 | 28/28 通过 | 首次因沙箱文件权限无法启动，获准重跑后通过 |
| 小程序测试 | 9/9 通过 | Node 模拟测试，不等于真机验收 |
| Web 生产构建 | 通过 | JS gzip 约 100.12 KB；CSS gzip 约 12.51 KB |
| 中文字体 | 17,772,300 bytes | 原始字体约 17.77 MB；不是实测网络传输量 |
| 现有质量门禁 | 通过，3 项警告 | 检索/路由/答案历史报告均缺少版本信息 |
| 10 条图问题 × 5 次 | 每题中位数约 5.5–24.7 ms | 包括连接与实体加载；单次最高约 84.4 ms |
| 三个问题的名称召回 | 每题中位数约 154–157 ms | 每题 3 次；名称分词是已测得的热点 |
| 同组 BM25 / 向量召回 | 中位数约 6.7–10.5 / 14.2–16.7 ms | 不含在线规划/生成；首轮存在额外初始化 |
| 两个普通问题的离线管线 | 单次约 796 / 813 ms | 各调用 4 次完整检索，存在重复查询 |
| 冷启动预热 | 本轮一次约 41.3 s | 含导入、模型和索引加载；不是稳定分位数 |

结论：**本轮测量不支持把主要瓶颈归因于 SQLite 图遍历**。名称召回与重复检索值得先优化；线上首字延迟中，语义规划模型占多少，需要阶段 Trace 再测。不能拿这些离线数字宣称线上已经提速。

原始记录：[output/audit_20260908/graph_probe.json](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/graph_probe.json>)、[output/audit_20260908/rag_probe.json](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/rag_probe.json>)、[output/audit_20260908/test_status.json](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/test_status.json>)、[output/audit_20260908/web_build.log](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/web_build.log>)。

## 3. 后端与安全：优先问题

优先级含义：P1 为下一批应处理的正确性、安全或发布可靠性问题；P2 为随对应模块改造处理的设计与体验问题。条件性风险不等于已发生攻击。

### P1：实体识别会把目标物品识别成短名称

**已复现**：“重息壤是什么”提取为“息壤”；“诀的信物是什么”提取为“诀”。`extract_kb_entity` 用最短命中作主实体，这个规则从干员衍生条目的特殊情况扩散到了所有条目。

影响：错误实体全文优先进入上下文，随后还会加权重搜错误实体；即使召回列表包含正确条目，最终答案仍可能偏题。

改法：建立统一 EntityResolver，保留 item_id、类型、名称和人工别名；完整目标名称优先，干员主档案与信物等派生物品按问题意图区分，多实体问题返回实体集合。用重叠名称、单字人名、衍生物品和双实体问题做回归，不能简单把“最短”改成“最长”就结束。

代码：[scripts/rag_ask.py:111](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:111>)。复现：[output/audit_20260908/correctness_probe.json](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/correctness_probe.json>)。

### P1：增量索引的删除集合不完整，更新过程也缺少整体发布边界

**代码确认的更新场景缺陷，尚未在真实索引上执行破坏性复现**。`build_rag` 只为完全删除的条目收集旧 chunk ID；原条目仍存在但正文缩短时，多出的旧 chunk 不在删除集合。旧向量可能留在 Chroma，而新 manifest/BM25 已无对应项；检索中的 `idx_map[cid]` 还可能报错。

另外，条目哈希未纳入实际 `max_chars` 和 embedding 模型；变更这些构建参数不能仅依赖内容 hash 决定是否重算。Chroma、manifest、BM25 依次原地更新，失败或服务并行读取时可能看到混合版本。

改法：按全体旧/新 chunk ID 差集清理；将切分参数、模型标识/版本和策略指纹纳入构建清单；在独立版本目录构建、审计成功后切换，保留上一版。失败必须非零退出。优先补“同条目 3 块缩到 1 块”“模型或切分参数变更”“中途写入失败”测试。

代码：[scripts/build_rag.py:80](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/build_rag.py:80>)、[scripts/build_rag.py:374](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/build_rag.py:374>)、[scripts/build_rag.py:427](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/build_rag.py:427>)、[scripts/rag_search.py:116](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_search.py:116>)。

### P1：流式正常 EOF 被当成答案完成

**离线模拟已复现**：模型只发一段正文，没有 finish_reason，随后结束响应，`chat_stream` 仍正常返回；上层可以发出成功 done。

改法：明确区分 complete / interrupted / cancelled / degraded。校验服务商协议要求的终止状态；EOF 本身不作为完成证据。保留半段文字但不缓存为完整答案，不允许用户误认为已答完。不同服务商的结束信号由适配器统一处理。

代码：[scripts/llm_client.py:296](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/llm_client.py:296>)、[scripts/rag_ask.py:1128](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:1128>)。

### P1：超时、取消和费用预算没有统一到整次请求

小程序请求固定 30 秒；后端 LLM 默认单次超时 60 秒并允许重试，开放问题还可能先规划、再生成、再续写。同步规划期间没有接收流式 abort，用户离开之后仍可能继续付费工作。每日请求次数限制已有，但请求次数不等于调用次数或 token 成本。

改法：传入统一 RequestContext，含 deadline、cancel、request_id 和调用预算；每个步骤只使用剩余时间。规划设独立短超时并确定性降级；取消贯穿检索与生成；统一前后端和代理时间预算。额度保护继续保留，补“未开始工作就因并发满而拒绝”的准入语义，避免无效扣次数。

代码：[miniprogram/utils/api.js:12](<C:/Users/28277/Desktop/ANY/Vibe Coding/miniprogram/utils/api.js:12>)、[scripts/llm_client.py:117](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/llm_client.py:117>)、[scripts/rag_ask.py:328](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:328>)、[scripts/api_server.py:574](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_server.py:574>)、[scripts/api_security.py:105](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_security.py:105>)。

### P1：SVG 媒体在本站域名下直接返回

**已用无害上游模拟验证策略**：`image/svg+xml` 被接受，返回 200，未附隔离 CSP 或下载响应头。

这是条件性风险：若允许的 CDN 路径能承载攻击者控制的主动 SVG，直接导航到本站代理地址会扩大同源内容风险。当前没有验证 CDN 的上传控制，也没有进行真实利用；普通 img 标签加载与顶层文档导航的行为不同，不能笼统说所有图片都会执行脚本。

改法：使用明确的图片/音频 MIME 白名单；不需要 SVG 就拒绝，确有需要则采用隔离来源或安全转换。保留现有 HTTPS 精确域名、路径、重定向禁用、大小和并发限制。

代码：[scripts/api_server.py:122](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_server.py:122>)。验证：[output/audit_20260908/correctness_probe.json](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/correctness_probe.json>)。

### P1：发布门禁对历史成绩的约束不足

当前门禁允许没有 metadata 的报告，仅产生警告；构建清单没有绑定检索/路由实现代码指纹。实现已变化，旧成绩仍可通过。现有 CI 还没有运行 API 安全、流式、Trace、Web 和小程序的完整回归组合。

改法：区分快速离线 CI 与正式发布门禁。正式发布必须关联代码、数据、索引、Prompt、配置和评测集版本，拒绝缺失或不匹配的报告。在线成绩需由明确的评测任务生成，普通 CI 不接触密钥、不自动付费。

代码：[scripts/quality_gate.py:33](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/quality_gate.py:33>)、[scripts/build_eval_manifest.py:43](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/build_eval_manifest.py:43>)、[.github/workflows/rag-quality.yml:1](<C:/Users/28277/Desktop/ANY/Vibe Coding/.github/workflows/rag-quality.yml:1>)。

### P2：安全职责、参数边界和部署配置仍可收敛

| 观察 | 建议 |
|---|---|
| 问答与管理员共用 API_ACCESS_TOKEN；双端请求都没有 Bearer 接入 | 管理权限与用户访问独立。公网匿名问答继续按预算保护；若启用私有访问，用明确会话机制，不能把共享管理密钥打包进前端 |
| CORS 对所有来源、方法、头开放 | 按环境配置允许来源；同源生产页面收紧。CORS 不能代替身份校验或防滥用 |
| synthesis 只检查 max_depth 非负，未限制上限；item 也无长度上限 | 按项目约束限制深度至 10，补树节点/工作量预算。保持基础资源叶子、最多两配方和循环剪枝 |
| GET synthesis 每次读配方、重建索引；KB 回退扫描 JSONL | 统一只读版本化 Repository，按 ID 查询、名称辅助解析；并发初始化只执行一次 |
| 静态站点缺失 dist 时自动托管 web 源码目录 | 开发与生产行为分开；生产缺构建产物应明确失败 |
| Dockerfile 未切换非 root 用户 | 增加非 root 运行及明确数据卷权限；已有 cap_drop/no-new-privileges 继续保留 |
| readiness 与 liveness 混用，预热失败仍报告基础健康 | 保留轻量存活检查，增加不反复扫描全库的就绪状态 |
| 媒体每次重新拉取，上游并发仅 2，名额占到客户端发送结束 | 加有容量上限的媒体缓存和同 URL 请求合并，评估慢客户端下隔离；不直接放大并发 |
| Trace 长期存储无明显保留期；每次连接做 schema 检查 | 迁移放到启动阶段，设置留存与清理策略；保留用户反馈隔离和正文最小化原则 |

相关代码：[scripts/api_security.py:120](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_security.py:120>)、[scripts/api_server.py:83](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_server.py:83>)、[scripts/api_server.py:206](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_server.py:206>)、[scripts/api_server.py:359](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_server.py:359>)、[scripts/api_server.py:730](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/api_server.py:730>)、[Dockerfile:1](<C:/Users/28277/Desktop/ANY/Vibe Coding/Dockerfile:1>)、[scripts/rag_trace.py:88](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_trace.py:88>)。

**已经做对，应保留**：额度库事务式准入及故障关闭、不直接相信任意转发头、严格媒体域名、禁重定向、大小/并发保护、普通 Trace 不存问答正文、反馈人工审核、React 文本节点渲染、离线模型加载、配方确定性直查。

## 4. RAG / GraphRAG 的性能和准确性计划

### 先处理已测得的重复工作

1. 名称正规化与分词改为索引加载时预计算，按独立条目计算后映射 chunk；避免每个查询对每个 chunk 的相同名称重新分词。
2. 向量 ID → metadata 映射及 collection 数量随索引快照缓存，避免每次重建。
3. 原问题、子查询、实体加权查询先去重；只在需要时进行加权补检索，已找到主实体时不要无条件再搜。
4. 确定性实体属性/关系直达可先于模型规划，但必须经困难集证明不会把复合、否定、比较问题误判成简单问题。
5. 去重与缓存完成后，再评估有界并行或批量 embedding。CPU 上并行模型调用可能增加竞争，不把“全开线程”作为默认提速方案。

代码：[scripts/rag_search.py:93](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_search.py:93>)、[scripts/rag_search.py:124](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_search.py:124>)、[scripts/rag_ask.py:384](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:384>)、[scripts/rag_ask.py:740](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:740>)、[scripts/rag_ask.py:984](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:984>)。

### 保留足够证据，避免“有命中就很可信”

- `multi_search` 按名称+分类去重，会保留首次 chunk、丢弃同源另一关键段落。改为先按 chunk/span 去重，再按来源限额和问题覆盖度聚合。
- 自动 keyword/mention/direct 命中被当作“人工确认”的相关内容并绕过拒答阈值。它们只能证明“匹配到”，不能证明“足够回答”。拆开 source_kind、检索分数、关系置信度、证据覆盖度。
- 图关系 hit 的名称是“关系路径1”，item_id 为空；生成来源又只保留名称和分类。前端点击它会当作物品名查询。用可追溯 EvidenceRef 贯穿图、生成和双端：真实 source_id、章节、原文位置、引用编号、打开方式。
- GraphRetriever 两实体路径搜索未使用已解析的 predicate 约束；已找到短路径后仍可能继续找更长路径。先查要求的直接关系，再按关系语义控制多跳；设展开节点/边预算，保留“图无证据 → 文本回退”。
- 图构建 hash 只看名称、分类和 full_text，但提取还读取 sections_struct、operator_details。将这些输入及规则版本纳入变更检测，避免相关结构改变但增量未刷新。
- 1800 字查询窗口有价值，但仍需验证跨段指代、数值表格与多子问覆盖。先保证可追溯块/位置，再做预算分配；不能靠不断扩大上下文掩盖检索错误。

代码：[scripts/rag_ask.py:399](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:399>)、[scripts/rag_ask.py:889](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/rag_ask.py:889>)、[scripts/graph_search.py:138](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/graph_search.py:138>)、[scripts/graph_search.py:186](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/graph_search.py:186>)、[scripts/build_knowledge_graph.py:38](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/build_knowledge_graph.py:38>)。

### 重新建立可信的质量评测

现有 71 条检索集 Recall@5=100%、MRR=97.3%，但它主要衡量候选条目命中；答案集仅 6 条，holdout/challenge 仍为空。答案 Judge 输入包含问题、必要词、答案和来源名称，**没有原文证据正文**，无法可靠判定忠实度。引用正则只证明出现编号，不证明编号有效、支持对应结论。

计划先建 60–100 条人工核对的核心集，另留 30–50 条冻结困难集，覆盖：重叠实体、信物/主档案、反向关系、否定问法、跨段指代、多子问、缺证拒答、末尾证据、数值聚合、来源点击和流式中断。

每题标注目标实体/子问题、必要事实、可接受原文与出处、允许的拒答范围。分别报告：实体正确率、证据覆盖率、答案事实正确率、完整性、引用支持率、正确拒答率、阶段延迟和调用成本。Judge 必须读到实际送给生成器的证据，并经过人工抽样校准。

只有这些评测证明排序仍是主要瓶颈，才试验小型 reranker；只有缺证覆盖仍是主要问题，才试验最多一次的受限补检索。暂不迁移 Neo4j、不引入开放 Agent Loop。

代码：[scripts/eval_answers.py:92](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/eval_answers.py:92>)、[scripts/eval_case.py:57](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/eval_case.py:57>)、[scripts/build_eval_manifest.py:61](<C:/Users/28277/Desktop/ANY/Vibe Coding/scripts/build_eval_manifest.py:61>)。
历史成绩快照：[output/audit_20260908/existing_evaluations.json](<C:/Users/28277/Desktop/ANY/Vibe Coding/output/audit_20260908/existing_evaluations.json>)。

## 5. 哪些能力应抽成接口

这里分清 **内部 Python 接口** 与 **对双端开放的 HTTP API**。共用函数不必全部变成网络调用。

| 能力 | 推荐边界 | 解决的问题 |
|---|---|---|
| 配方加载、选配方、构树、设备反查 | 内部 RecipeRepository + SynthesisService | API 与 RAG 重复实现及缓存不一致 |
| KB、干员、媒体、名称、别名 | 内部 CatalogRepository + EntityResolver | JSONL 扫描、最短名称误判、多个缓存各自为政 |
| graph / keyword / mention / vector / BM25 | 内部受类型约束的 Retriever 接口 | 统一 EvidenceRef、预算、trace，便于离线替换测试 |
| 规划、召回、证据筛选、生成 | AskService 编排，各步骤职责独立 | 缩小 rag_ask.py 的修改影响范围 |
| 普通 / 流式模型调用 | LLM Gateway，统一结束、重试、取消、usage | 避免两套完成语义和成本记录分叉 |
| API DTO、错误和流式事件 | Pydantic/OpenAPI 契约 + 双端适配器 | 当前大量可选字段、客户端手动猜分支 |
| 运行配置和环境加载 | 单一 Settings 入口 | 三处 dotenv 解析、魔法数字分散 |
| 版本信息、数量、公开能力 | 建议 GET /api/catalog/meta | 替换前端写死统计，不暴露管理员配置 |
| 条目与干员详情 | 建议 GET /api/items/{id}、/api/operators/{id} | 不再通过“查配方失败”获取完整档案 |
| 合成树 | 保留 /api/synthesis，逐步支持稳定 ID | 老客户端继续可用 |
| 问答 | 保留 /api/ask、/api/ask/stream | 同一编排、两种传输，不为改名破坏兼容 |

新响应使用清晰的 kind 与 version；旧响应经兼容层返回。客户端只拿展示所需数据，调试计划和详细检索分数放受控诊断出口。名称全量本地过滤在约两千条规模下合理，不必为了“接口化”让每次按键都请求后端。

## 6. Web：建议的视觉与交互方向

**推荐：“终末地工业档案工作台”。** 保留暖白、墨黑、工程黄、细结构线和少量切角，让搜索、合成树、原文证据成为主角。

已观察首页：大标题、统计卡、多层背景和贴纸共同占据首屏，搜索靠近首屏下部，结果还在下面。问题是视觉重点与查询任务的优先级不一致，而不是缺少更多装饰。

| 现状 | 改造方向 |
|---|---|
| 约 3.76 秒固定开场，每次挂载播放，进度不代表加载 | 搜索立即可操作；首次可跳过的短品牌演出，后续进入不阻塞 |
| Hero 占较大篇幅，树和问答共用大量装饰框架 | 首页压缩品牌区；查询后进入专注工作区，保留紧凑搜索和模式切换 |
| 黄、蓝阴影、多边形、网格和贴纸同时强调 | 黄色只突出主动作和选中态；蓝色如保留则明确用于证据链接；贴纸集中于空态或品牌区 |
| “100% Recall”“LOCAL INDEX ONLINE”等写死 | 移除营销式准确率暗示；数据量与更新时间来自公开元信息；故障状态真实显示 |
| 字体 17.77 MB | WOFF2 分包/子集，中文缺字有系统字体回退；检查实际网络瀑布，避免全量预加载 |
| App.tsx 混合请求、流式、缓存、页面和全局效果 | 抽 useAskSession、useSynthesisQuery、独立 view model 和小型状态机 |
| 问答内容与内部路由标签混杂 | 默认展示答案、证据与不足之处；诊断信息折叠 |
| 来源跳转占用当前结果 | 桌面原文侧栏/详情路由，返回恢复查询、滚动和树状态；URL 支持分享与浏览器后退 |
| 搜索 Enter 未检查中文输入组合状态；缺 combobox 语义 | 加 IME 保护、Escape、明确提交按钮、键盘/读屏联想状态 |
| CSS reduced-motion 已有，但 SVG 使用 JS Motion 动画 | MotionConfig/useReducedMotion 覆盖 JS 动画，取消非必要视差 |
| 树缩放主要改变 SVG 尺寸，首次适配仅执行一次 | 统一视口与 fit/reset 行为，响应容器尺寸变化，补键盘和移动交互 |

具体版式：桌面“紧凑顶栏 → 搜索与模式 → 大结果区 + 按需证据侧栏”；移动端单列结果，原文打开独立页面或底部面板。先做首页、配方结果、问答结果、干员详情四个关键状态，避免只把空首页做漂亮。

动效建议作为原型参数而非硬承诺：按钮反馈 120–180ms、面板切换 180–260ms、树展开约 220–320ms；优先 opacity/transform。品牌演出与日常操作使用不同强度。暂不对全站安装平滑滚动接管，也不为查询工具引入 WebGL 主场景。

代码：[web/src/App.tsx:34](<C:/Users/28277/Desktop/ANY/Vibe Coding/web/src/App.tsx:34>)、[web/src/components/Hero.tsx:1](<C:/Users/28277/Desktop/ANY/Vibe Coding/web/src/components/Hero.tsx:1>)、[web/src/components/EntryCurtain.tsx:1](<C:/Users/28277/Desktop/ANY/Vibe Coding/web/src/components/EntryCurtain.tsx:1>)、[web/src/components/SearchBox.tsx:49](<C:/Users/28277/Desktop/ANY/Vibe Coding/web/src/components/SearchBox.tsx:49>)、[web/src/components/SynTree.tsx:180](<C:/Users/28277/Desktop/ANY/Vibe Coding/web/src/components/SynTree.tsx:180>)。

## 7. 小程序：单独优化，不做缩小版网页

- 首页直接搜索、模式和历史；装饰动效更轻，优先真机输入和滚动稳定。
- 请求封装返回可取消的任务。onUnload 不只忽略旧结果，还要终止客户端请求；后端统一取消语义。
- 同一首页分别 loadNames/loadStats 重复请求 /api/names，应合并；onLaunch/onLoad/onShow 健康探测适度复用。
- onPageScroll 高频 setData 多个变换，改为节流或平台适合的动画方案；低性能设备关闭装饰视差。
- 30 秒统一超时改为按请求类型和服务端预算协商。研究 wx.request 分块能力及基础库/平台支持，验证后再接 SSE；当前 README“wx.request 不支持流式”不宜作为永久结论。官方文档本轮未成功打开，因此此项尚未核实，降级保留整包问答并提供明确等待/取消状态。
- 目前先按引用切答案、再分别解析 Markdown，可能截断表格/列表语法。共享答案结构/解析规范，各端独立渲染，补“表格中有来源编号”测试。
- 干员语音来源没有像 Web 一样还原所属干员；图路径来源同样不能当物品名跳转。以 EvidenceRef 的打开方式统一解决。
- Canvas 树与 Web 共用纯数据布局核心/不变量，不强行共享 DOM；渲染、手势、像素比、图片缓存按平台实现。补定时器与组件卸载清理。
- 开发/体验/正式的 API 基址通过环境配置管理，发布流程校验 HTTPS 和合法域名，不能依赖手改本机地址。
- 后续至少在 Android、iOS 真机验证长答案、图片/音频、后台切换、弱网、滚动与树手势；模拟器通过不代表这些体验已达标。

代码：[miniprogram/utils/api.js:6](<C:/Users/28277/Desktop/ANY/Vibe Coding/miniprogram/utils/api.js:6>)、[miniprogram/pages/index/index.js:48](<C:/Users/28277/Desktop/ANY/Vibe Coding/miniprogram/pages/index/index.js:48>)、[miniprogram/pages/ask/ask.js:63](<C:/Users/28277/Desktop/ANY/Vibe Coding/miniprogram/pages/ask/ask.js:63>)、[miniprogram/pages/ask/ask.js:278](<C:/Users/28277/Desktop/ANY/Vibe Coding/miniprogram/pages/ask/ask.js:278>)、[miniprogram/pages/ask/ask.js:336](<C:/Users/28277/Desktop/ANY/Vibe Coding/miniprogram/pages/ask/ask.js:336>)、[miniprogram/components/synth-tree/synth-tree.js:48](<C:/Users/28277/Desktop/ANY/Vibe Coding/miniprogram/components/synth-tree/synth-tree.js:48>)。

## 8. 设计参考与工具取舍

以下资料已在本轮搜索/打开；参考目的与适用边界明确区分。不把社区工具清单里的安装命令当作已验证事实。

| 来源 | 借鉴内容 | 在本项目的取舍 |
|---|---|---|
| [终末地官网](https://endfield.hypergryph.com/) | 工业品牌语汇、角色/媒体与章节组织 | 本轮主要据本地保存页面研究，动态浏览未完成；不照搬宣传站的重首屏到查询工具 |
| [Linear](https://linear.app/) | 围绕工作内容组织信息与操作 | 借鉴紧凑工作台和状态表达；不必改成通用深色 SaaS 模板 |
| [Stripe](https://stripe.com/) | 复杂产品的信息分层与渐进呈现 | 借鉴说明与交互示意，不复制配色 |
| [Motion](https://motion.dev/) / [无障碍动画说明](https://motion.dev/docs/react-accessibility) | React 状态变化、布局与减少动画 | 项目已经有 framer-motion，先完善现有使用方式，不为改名盲目升级 |
| [GSAP ScrollTrigger](https://gsap.com/docs/v3/Plugins/ScrollTrigger/) | 时间线和滚动关联演出 | 仅当选定品牌原型需要时用于独立区域 |
| [Lenis](https://github.com/darkroomengineering/lenis) | 平滑滚动实现 | 作为备选；树画布、表格与小程序默认保留原生滚动 |

建议工具组合：

1. **设计主 skill：Impeccable 或 Taste redesign 二选一。** [Impeccable](https://github.com/pbakaus/impeccable) 适合审美检查与迭代；[Taste Skill](https://github.com/Leonxlnx/taste-skill) 的 redesign 方向适合既有项目。你本地已有 Taste 工具包，可先核对版本后复用，不需要盲装多个审美 skill。
2. **工程补充：Vercel React Best Practices。** [官方仓库](https://github.com/vercel-labs/agent-skills) 可用于请求瀑布、组件与性能检查；只采用适用 React/Vite 的规则，不因其中有 Next.js 内容而迁移框架。
3. **浏览器验收：现有浏览器工具优先；必要时补 Playwright 或 Chrome DevTools MCP。** [Playwright MCP](https://github.com/microsoft/playwright-mcp) 用于交互回归；[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) 用于性能与网络分析。接入目的应是可重复的截图、网络和性能证据，不是增加工具数量。
4. Figma 插件在需要交付可编辑设计稿时再接；GitHub 插件在需要远程 PR 协作时再接。本轮本地 Git 和公开仓库搜索已足够，不需要这些连接才能继续。
5. 不安装清单型工具包里的全部工具。选定 skill/插件需核对来源、许可证、版本及执行内容，并遵守项目边界。当前未安装上述新增工具。

设计基础参考还包括 [Anthropic frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)。这是候选设计指导，不等于已在本轮安装或执行。

## 9. 实施顺序、提交和验收

| 阶段 | 工作 | 你能看到的结果 | 提交与放行条件 |
|---|---|---|---|
| S0 基线固定 | 保存本报告、代码/数据/模型指纹；补数据快照策略 | 当前版本可重复运行，基线表清晰 | 现有 4a4ec99 为起点；审查文档单独提交 |
| S1 正确性与安全 | 实体识别、增量删除/版本、流式终止、媒体策略、请求预算、评测绑定 | 同题前后结果与失败行为对照 | 每个问题独立 fix commit；针对性回归与旧测试通过 |
| S2 服务边界 | Repository、Resolver、EvidenceRef、Settings、LLM Gateway、DTO 兼容层 | 双端响应一致、来源可打开、模块可单独测试 | 小步 refactor；默认行为不变的契约回归 |
| S3 RAG 提速与质量 | 名称预计算、查询去重、受控快路由、证据聚合、困难集 | 阶段耗时/调用次数/正确率对照 | 数据与模型固定；逐项消融，正确率不退化 |
| S4 视觉原型 | 推荐工业档案方向，另给一版更克制的布局对照 | 四个关键页面的桌面/窄屏原型，含真实样例内容 | 原型独立于生产入口；明确设计选择后实现 |
| S5 Web 接入 | 字体、工作区、状态机、来源侧栏、可访问性、动效 | 可操作预览、固定视口截图和交互录像 | UI 独立提交；旧查询规则回归、构建通过 |
| S6 小程序与发布验收 | 平台请求、渲染、Canvas、环境配置、弱网与真机 | 双端同题对照、真机结果、回滚演练 | 独立提交；满足发布门禁后再部署 |

S2 不做一次性目录大搬家；按 S1/S3 涉及能力逐个抽出。视觉原型可以在后端修复期间独立制作，但不把两类变更塞进同一个 commit。

**前后对照必须保存的内容：**

- 代码 commit、数据/索引版本、Prompt、模型和评测集版本。
- 同组问题的原文证据、完整/中断/拒答状态、来源跳转结果。
- cold/warm 分开；受理、规划、检索、首个正文 token、完成时间分开；足够样本后再报 p50/p95。缓存命中不冒充检索提速。
- 同尺寸截图：1440×900、1280×720、390×844；小程序单独保存真机结果。
- 不只测首页，覆盖配方树、长答案、表格、干员档案、空态、错误、429、超时和取消。
- 树不变量：基础资源叶子、最多两配方、循环剪枝、深度≤10；不重建已废弃的空间规划功能。

**建议性能目标，属于待验收目标而非承诺：**

- 同机名称召回中位数较本轮至少下降 70%；避免原问题与相同子查询重复执行。
- 不依赖付费规划的明确查询，先达到本地 warm 检索 p95 <300ms，再根据正式硬件校准。
- UI 不以固定开场阻塞搜索；字体及媒体优化以实际传输量/LCP 改善验收。
- 正式 Web 以 LCP≤2.5s、INP≤200ms、CLS≤0.1 作为目标，按真实用户第75百分位评价；本地实验数据单列。指标口径参考 [Web Vitals](https://web.dev/articles/vitals)。
- 正确性以冻结集和必要事实/证据为准，不能用仅含六题的平均分宣布“回答准确率100%”。

**回退方案：**

正式改造前，从已确认基线建立 `codex/` 改造分支并标记基线；按阶段提交。预览新旧版本时使用不同目录/端口、匹配的数据快照，避免边运行边切换同一工作目录。回退使用上一版构建与索引，已共享提交采用 revert；不以破坏性 reset 清理用户工作。

Git commit 不保存被忽略的 Chroma、模型缓存、原始抓取或 .env，因此代码回退不等于完整运行状态回退。数据用只读快照/校验清单或可复现构建保存；SQLite 使用一致性备份方式，不直接复制正在写入的单个文件；密钥留在独立环境配置里。

未来修改小程序、部署、根目录配置或 CI 时，要将相应目录纳入那一阶段明确的修改范围；当前手册默认写入边界较窄，本轮仅输出审查材料。

## 10. 调查与工具失败时的降级规则

按你补充的偏好：质量优先，但不无限重连。

- 外站首次失败后最多进行一次有针对性的短重试；仍失败就用已有本地资料、其他官方来源或静态代码，并标记待核实项。网络正常再补，不阻塞其他工作。
- 浏览器不能稳定录制动效时，先交付源码检查与静态版式原型；不宣称已做帧率、触控或视觉回归验收。
- 在线模型不可用时，执行确定性检索与来源验证，报告降级状态；不能编造答案或新的准确率。
- 额外插件不能连接时，优先现有工具；只有缺失能力实际影响验收，才提出最小的接入需求。
- 长任务按模块交付短报告和保存点；每次明确完成、发现、未验证和下一步，不把重连当成持续进展。

**推荐下一步：先做 S1 中的实体定位与流式完成判断，独立提交并展示复现对照；随后补索引增量与评测门禁。同时进入 S4 的静态版式原型设计。**
