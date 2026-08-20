# Endfield 配方树与知识库

一个基于《明日方舟：终末地》WIKI 数据的配方合成树和知识问答项目。

输入物品或设备名称，可以查看从基础资源到目标产物的纵向配方树；切换到知识问答后，可以查询干员、
任务、武器、地点和人物关系。页面还支持干员技能、天赋、潜能、档案、图片和语音展示。

## 主要功能

- 345 条真实配方，支持物品树、设备配方卡、名称歧义选择和无配方回退；
- 搜索框模糊联想，前缀匹配优先；
- 名称 + BM25 + 向量的混合 RAG，并带实体直取、枚举、mention 和关键词补充检索；
- 可追溯知识图谱，支持明确关系、正反向问法和最多三跳路径；
- 白色工业档案风格前端，包含纵向图片树、机械开场动画和响应式布局；
- RAG/图谱增量更新、深度健康检查、运行指标和 CI 质量门禁。

## 数据和请求流程

```text
WIKI 原始 JSON
  ├─ build_kb_all.py → endfield_kb/ → RAG 索引 + 知识图谱
  ├─ recipe_extract.py → output/recipes.json → 配方合成树
  └─ 媒体/干员提取 → 图片、音频和档案详情

浏览器 → FastAPI
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

### 本地 Python

项目使用 Python 3.12：

```powershell
pip install -r requirements.txt
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
python scripts/build_knowledge_graph.py
python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000
```

本地构建默认离线加载 `BAAI/bge-small-zh-v1.5`，需要提前把模型放入 Hugging Face 缓存。没有本地缓存时，
使用 Docker 构建更省事。

## 验证

```powershell
python -m unittest discover -s tests -v
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/quality_gate.py
```

当前固定评测结果：

- 单元测试：45 项；
- 检索集：71 条，Recall@5 100%，MRR 0.973；
- 图关系集：10/10；
- 关系正向、反向和是非问审查：1656/1656。

这些数字用于防止已知能力回退，不代表所有自然语言问题都能达到 100% 正确率。

## 项目目录

```text
scripts/       数据构建、检索、图谱、API 和评测工具
endfield_kb/   按分类整理的知识库
output/        配方、索引 manifest、图谱和评测结果
web/           单页前端、字体、角色素材和本地 D3
tests/         离线回归测试
```

## 继续阅读

- [项目当前状态](PROJECT_STATE.md)
- [开发说明](DEVELOPER_GUIDE.md)
- [知识库、RAG 与知识图谱总览](KNOWLEDGE_SYSTEM_ARCHITECTURE.md)
- [工具命令](scripts/README.md)
- [部署说明](DEPLOYMENT.md)
- [RAG 开发记录](RAG_DEVLOG.md)

## 数据与素材说明

项目数据来自《明日方舟：终末地》WIKI，仓库是非官方学习与展示项目。页面角色图片素材来自：呵纹Hevon，
画师：仓鼠饭团c。相关游戏名称、图像和内容权利归原权利方所有。
