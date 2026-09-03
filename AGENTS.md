# AGENTS.md — AI 工作手册（进入本项目的 AI 请先读我）

> 本项目从「明日方舟：终末地」官方 WIKI 抓取数据，构建 **配方合成树** 应用。
> 早期「生产流水线空间规划」方向已废弃（算法文件与文档均已删除），**不要再重建**。

## 0. 接手流程
1. 先读本文件了解项目背景与纪律
2. 再读 `PROJECT_STATE.md` 获取最新状态
3. 查看 `scripts/README.md` 工具清单（避免重写工具）
4. RAG 问答相关改动前先读 `KNOWLEDGE_SYSTEM_ARCHITECTURE.md`（架构 + 路线图 + 门禁一体）
   与 `RAG_DEVLOG.md`（决策/踩坑记录）

## 1. 项目一句话
用户输入物品/设备名（**搜索框带模糊联想**，如输入"中"弹出所有"中"开头选项）→
前端 **配方合成树**（纯 React SVG，已不依赖 d3）展示完整配方链（叶子收敛到基础资源：清水/矿物/气体矿物/种子）；
无配方物品回退知识库显示其信息。

## 2. 数据流（完整链路）
```
endfield_wiki_full_*.json (147MB, 1958条, 块式富文本)
  → scripts/build_kb_all.py          按 22 个子分类提取
  → endfield_kb/{分类}.jsonl + .md + _catalog.json
  → scripts/build_rag.py             构建/增量更新 RAG 索引
  → output/rag/  (ChromaDB 向量 + bm25/{分类}.pkl 分片 + chunks.json manifest)
  → scripts/extract_media.py         提取 图片/链接/引用（封面图 1957 / 外链 291 / 引用 14693）
  → output/item_media.json           供 /api/synthesis 返回 cover + refs
  → scripts/api_server.py (FastAPI)
      GET  /api/synthesis?item=重息壤   合成树（物品树 / 设备配方卡 / 歧义→候选列表 / 无配方→知识库信息 + 封面图/相关引用）
      GET  /api/names                   全部名称（前端模糊搜索联想）
      GET  /api/health                  健康检查
      POST /api/ask/stream              流式知识问答（SSE：phase→meta→delta→done，网页端默认走此接口）
  → web/ 前端（Vite+React+TS，`npm run build` 出 dist 由后端托管；白色工业制图；纵向图片配方树 + 知识问答双模式）
```

## 3. 环境（重要，已确认）
- Windows / PowerShell；Python 3.12（conda env `endfield`）；Node 24
- ⚠️ 终端中文输出 GBK 乱码 → **所有中文/结果一律写 UTF-8 文件再读取**
- ⚠️ `sys.stdout.reconfigure` 前必须 `if sys.stdout:` 容错（后台运行时 stdout 可能为 None）
- ⚠️ 模型必须离线加载：`HF_HUB_OFFLINE=1` + `local_files_only=True`（联网检查 HF 会超时/失败）
- ⚠️ Windows `localhost` 解析到 IPv6，uvicorn 绑 `0.0.0.0` 只听 IPv4 → 浏览器请用 **`http://127.0.0.1:8000`**
- 根目录 `.env` 可选（LLM 相关配置备用）；`.env` 勿提交公开仓库
- `start_server.py` 单进程默认预热 embedding 模型与索引（冷启动移进健康检查 start_period）；内存极紧可 `RAG_PREWARM=0` 关闭

## 4. 目录约定
```
项目根/
├─ AGENTS.md / PROJECT_STATE.md / DEVELOPER_GUIDE.md
├─ scripts/          # 工具（勿重写，先查 README）
├─ endfield_kb/      # 按分类提取的知识库（build_kb_all 产物）
├─ output/           # RAG 索引、recipes.json、评测结果
├─ web/              # 前端（Vite+React+TS；src 源码 + dist 产物）
├─ .env              # 可选（LLM 相关配置备用，私密）
└─ endfield_wiki_full_*.json / endfield_devices.* / endfield_items.*  # 历史数据（只读）
```
- **边界**：只修改 `scripts/`、`web/`、`endfield_kb/`、`output/`、`logs/`；根目录既有数据文件只读勿删

## 5. 工作纪律
1. **先查 `scripts/` 再动手**，重复功能沉淀进 `scripts/` 并更新 `scripts/README.md`
2. 输出落盘 UTF-8 文件再读取，别依赖终端回显
3. 数据必须真实，抓不到如实报告，禁止编造
4. 复杂命令写 `.py` 脚本执行，不拼超长 PowerShell 单行
5. 涉及合成树算法，**叶子必须是基础资源**（清水/矿物/气体矿物/种子类），配方 ≤2、循环剪枝——见 `DEVELOPER_GUIDE.md`

## 6. 常用命令
```bash
# 全量分类提取
python scripts/build_kb_all.py
# RAG：首次全量 / 之后增量（只重 embedding 变更条目 + 变更分类 BM25 分片）
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --incremental
# 启动服务（推荐 start_server.py：单进程默认预热 embedding/索引；RAG_PREWARM=0 关闭预热）
python scripts/start_server.py
# 或直接 uvicorn（无预热，首个问答会现场加载模型）
python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000
# 浏览器 http://127.0.0.1:8000
```

## 7. 关键技术结论（不要再重新侦察）
- WIKI 是 React SPA；数据在 `zonai.skland.com` 接口（强制登录+签名），用 `wiki_collector.js` 浏览器采集；详情是块式富文本文档（`documentMap.blockMap`，块类型 text/list/table）
- 合成树数据源 = `output/recipes.json`（`recipe_extract.py` 提取的 345 个配方，**不做激进清洗**：设备制造/容器"盛装"/矿机/原木配方全保留，供"怎么造"完整展示），不是知识库
- RAG 增量更新：条目 `content_hash`（md5）→ 对比 manifest → 只 upsert 变更 chunk → 只重建变更分类 BM25 分片
- 前端搜索联想：`/api/names` 返回全部名称（配方物品+设备+知识库条目），前端本地过滤（前缀优先+包含匹配）
- 流式问答：`/api/ask/stream`（SSE）与 `/api/ask` 共用路由/检索，仅生成阶段改增量（phase→meta→delta→done），`done` 与整包返回等价；流式改善“感知延迟”，不减少最后一个字的完成时间（首字前等待主要是语义规划那一次 LLM 调用）
- 网页问答默认走流式接口；小程序与评测/门禁继续用旧 `/api/ask`（改动流式前先读 `RAG_DEVLOG.md` 对应条目）
