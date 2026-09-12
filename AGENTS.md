# AGENTS.md — 项目协作约束

本项目从《明日方舟：终末地》WIKI 数据构建配方合成树与知识问答。早期“生产流水线空间规划”已经废弃，禁止重建。

## 接手顺序

1. 阅读 [当前状态](docs/PROJECT_STATE.md)；
2. 阅读 [整体架构](docs/ARCHITECTURE.md)；
3. 查看 [工具清单](docs/TOOLS.md)，避免重复实现；
4. 修改 RAG 前读 [RAG 设计](docs/RAG.md) 与 [决策记录](docs/DECISIONS.md)；
5. 按改动范围阅读 [测试与质量](docs/TESTING.md)。

## 不可破坏的业务约束

- 配方树唯一事实源是 `output/recipes.json`，不得用 RAG 猜配方；
- 叶子必须收敛到基础资源：清水、矿物、气体矿物或种子类；
- 每个物品最多展示 2 个配方，必须处理自循环并限制深度为 10；
- 名称歧义返回候选，不自动猜测；无配方物品回退知识库；
- 知识图谱的确定关系必须带来源和证据；图未命中不能解释为关系不存在；
- LLM 只根据检索证据生成，不能直接修改正式知识库或图谱。

## 前端空间层不变量

- 双螺旋阵列中的档案载体只是展示载体，不得与知识条目、配方或编号建立数据绑定；内容一律来自现有后端结果；
- 触摸设备保持页面原生纵向滚动：不得用 `touch-action` 接管纵向手势（历史缺陷：`pan-x` 会吃掉查询区上方的滑动）；

## 数据和文件边界

- 业务代码：`scripts/`、`web/`、`miniprogram/`；
- 文档：`docs/`，根目录只保留 `README.md` 与本文件作为入口；
- 生成数据：`endfield_kb/`、`output/`、`logs/`；
- 根目录 `endfield_wiki_full_*.json`、`endfield_devices.*`、`endfield_items.*` 等历史数据只读，不删；
- `.env` 和任何密钥不得提交；未抓到的数据必须如实报告，禁止编造。

## 环境约束

- Windows / PowerShell，Python 3.12（conda `endfield`），Node.js 24；
- 中文输出可能受 GBK 影响，重要结果写入 UTF-8 文件后读取；
- `sys.stdout.reconfigure` 前必须判断 `sys.stdout`；
- embedding 使用 `HF_HUB_OFFLINE=1` 和 `local_files_only=True`；
- 后端在 `0.0.0.0` 监听时，本机访问使用 `http://127.0.0.1:8000`；
- `start_server.py` 默认单 worker 并预热索引；内存紧张可用 `RAG_PREWARM=0` 关闭。

## 工作纪律

- 先查 `scripts/` 和 [工具清单](docs/TOOLS.md)，已有能力直接复用；
- 复杂操作沉淀成可复用脚本，并同步更新工具文档；
- 修改接口时同步更新 Web 类型、小程序封装和契约测试；
- 修改索引、路由、图谱或 Prompt 时保存版本信息并运行对应门禁；
- 不把固定评测集成绩表述成所有自然语言问题的正确率；
- 文档应说明当前实现、测试证据和已知边界，不把计划写成已完成。

常用命令与验证矩阵分别见 [工具清单](docs/TOOLS.md) 和 [测试与质量](docs/TESTING.md)。
