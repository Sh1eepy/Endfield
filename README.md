# Endfield 配方树与知识库

一个基于《明日方舟：终末地》WIKI 数据的配方合成树和知识问答项目。

输入物品或设备名称，可以查看从基础资源到目标产物的纵向配方树；切换到知识问答后，可以查询干员、
任务、武器、地点和人物关系。页面还支持干员技能、天赋、潜能、档案、图片和语音展示。

## 主要功能

- 345 条真实配方，支持物品树、设备配方卡、名称歧义选择和无配方回退；
- 搜索框模糊联想，前缀匹配优先；
- 名称 + BM25 + 向量的混合 RAG，并带实体直取、枚举、mention 和关键词补充检索；
- 可追溯知识图谱，支持明确关系、正反向问法和最多三跳路径；
- 白色工业档案风格前端，包含纵向图片树、机械开场动画、响应式布局和问答答案 markdown 渲染；
- 微信小程序端，覆盖搜索联想、配方树、知识问答与干员档案；
- RAG/图谱增量更新、深度健康检查、运行指标和 CI 质量门禁。

## 数据和请求流程

```text
WIKI 原始 JSON
  ├─ build_kb_all.py → endfield_kb/ → RAG 索引 + 知识图谱
  ├─ recipe_extract.py → output/recipes.json → 配方合成树
  └─ 媒体/干员提取 → 图片、音频和档案详情

网页 / 微信小程序 → FastAPI
  ├─ /api/synthesis：配方、设备、知识库详情
  ├─ /api/ask：图检索/RAG + 可选 LLM 回答
  └─ /api/names、/api/health、/api/metrics
```

RAG 负责找原文和描述性内容，知识图谱负责明确关系和路径。图里没有证据时会回退文本检索，不会把
“图谱未命中”直接解释成“这个关系不存在”。

## 快速启动

### Docker（推荐）

Docker 构建会下载 embedding 模型，并在镜像内重建本地 RAG 索引：

```powershell
docker build -t endfield-synthesis .
docker run --rm -p 8000:8000 endfield-synthesis
```

浏览器打开：

```text
http://127.0.0.1:8000
```

如果需要在线 LLM 生成回答，先复制 `.env.example` 为 `.env` 并填写配置：

```powershell
Copy-Item .env.example .env
docker run --rm -p 8000:8000 --env-file .env endfield-synthesis
```

`.env` 已被 Git 忽略，不要提交真实 API Key。

已有 Linux 服务器和子域名时，使用仓库中的 `compose.yaml` 与 Nginx 模板上线；完整的 HTTPS、限流、更新、回滚和排障命令见
[自有服务器部署手册](deploy/README.md)。容器默认只监听宿主机 `127.0.0.1:8000`，公网入口由 Nginx 提供。

### 本地 Python

项目使用 Python 3.12（conda env `endfield`）：

```powershell
pip install -r requirements.txt
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
python scripts/build_knowledge_graph.py
# 前端（Vite + React + TS）构建产物由后端托管
cd web && npm install && npm run build && cd ..
python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000
```

前端开发时用 `cd web && npm run dev`（http://localhost:5173，自动代理 `/api` 到 8000）。
本地构建默认离线加载 `BAAI/bge-small-zh-v1.5`，需要提前把模型放入 Hugging Face 缓存。没有本地缓存时，
使用 Docker 构建更省事。

### 微信小程序

先用上面的命令启动后端，再在微信开发者工具中导入仓库里的 `miniprogram/` 目录。开发者工具模拟器默认访问
`http://127.0.0.1:8000`。真机调试时，`127.0.0.1` 指向手机自身，需要把
`miniprogram/app.js` 中的 `apiBase` 临时改为电脑的局域网地址，并确保手机和电脑在同一网络。

正式发布必须把 `apiBase` 改为线上 HTTPS 地址，并在微信公众平台配置 request 合法域名。个人开发者工具设置保存在
`project.private.config.json`，该文件已被 Git 忽略。完整步骤见 [小程序说明](miniprogram/README.md)。

## 验证

```powershell
python -m unittest discover -s tests -v
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/quality_gate.py
```

最新固定评测数字（防回退基准）见 [PROJECT_STATE.md](PROJECT_STATE.md) ——这些数字不代表所有自然语言问题都能达到 100% 正确率。

## 项目目录

```text
scripts/       数据构建、检索、图谱、API 和评测工具
endfield_kb/   按分类整理的知识库
output/        配方、索引 manifest、图谱和评测结果
web/           Vite+React+TS 前端（src 源码 + dist 构建产物；设计说明见 web/README.md）
miniprogram/   微信小程序端页面、组件、主题与本地素材
tests/         离线回归测试
```

## 继续阅读

- [项目当前状态](PROJECT_STATE.md)（成果、待办、发布边界）
- [知识系统架构总览](KNOWLEDGE_SYSTEM_ARCHITECTURE.md)（架构 + 路线图 + 门禁）
- [开发说明](DEVELOPER_GUIDE.md) / [工具命令](scripts/README.md)
- [部署总纲](DEPLOYMENT.md) / [自有服务器部署手册](deploy/README.md) / [API 安全](deploy/API_SECURITY.md)
- [前端设计与实现](web/README.md) / [微信小程序说明](miniprogram/README.md)
- [RAG 开发记录（踩坑）](RAG_DEVLOG.md) / [Agent 设计原理](AGENT_WORKFLOW_DESIGN.md)

## 数据与素材说明

项目数据来自《明日方舟：终末地》WIKI，仓库是非官方学习与展示项目。页面角色图片素材来自：呵纹Hevon，
画师：仓鼠饭团c。相关游戏名称、图像和内容权利归原权利方所有。
