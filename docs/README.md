# 项目文档

这里集中保存项目的重要说明。文档按职责拆分：总览只解释边界，专项文档负责实现、测试、问题与扩展点，历史报告不作为当前事实来源。

## 建议阅读路径

| 目标 | 文档 |
|---|---|
| 了解目前做到哪里 | [PROJECT_STATE.md](PROJECT_STATE.md) |
| 理解全局结构和模块关系 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 开始本地开发 | [DEVELOPMENT.md](DEVELOPMENT.md) |
| 查脚本和命令 | [TOOLS.md](TOOLS.md) |
| 修改配方树 | [SYNTHESIS.md](SYNTHESIS.md) |
| 修改数据构建 | [DATA_PIPELINE.md](DATA_PIPELINE.md) |
| 修改知识问答 | [RAG.md](RAG.md) 与 [GRAPH.md](GRAPH.md) |
| 修改接口 | [API.md](API.md) |
| 修改 Web 或小程序 | [WEB.md](WEB.md)、[FRONTEND_EXPERIENCE.md](FRONTEND_EXPERIENCE.md)、[FRONTEND_SPATIAL_ACCEPTANCE.md](FRONTEND_SPATIAL_ACCEPTANCE.md) / [MINIPROGRAM.md](MINIPROGRAM.md) |
| 新增素材、核对来源与免责声明 | [ASSETS.md](ASSETS.md)：素材清单、字体许可、数据来源、使用边界与免责声明 |
| 编写或运行测试 | [TESTING.md](TESTING.md) |
| 准备上线 | [DEPLOYMENT.md](DEPLOYMENT.md)、[API_SECURITY.md](API_SECURITY.md)、[SERVER_RUNBOOK.md](SERVER_RUNBOOK.md) |
| 评估后续能力 | [EXTENSIBILITY.md](EXTENSIBILITY.md) |
| 查看变更原因 | [CHANGELOG.md](CHANGELOG.md) 与 [DECISIONS.md](DECISIONS.md) |

## 文档职责

- `PROJECT_STATE.md` 保存当前快照，不承载详细实现；
- `ARCHITECTURE.md` 保存稳定的整体边界、技术选型总览和数据流；
- 专项设计文档按"职责与技术选型 → 不变量与实现 → 测试问题与对策 → 扩展接口"组织，便于单独阅读某一块设计；
- `CHANGELOG.md` 记录已经完成的重要改进；
- `FRONTEND_EXPERIENCE.md` 记录当前 Web 空间层实现，`FRONTEND_SPATIAL_ACCEPTANCE.md` 保存对应验收数据与边界；
- `DECISIONS.md` 记录仍会影响维护的取舍和理由（ADR）；
- `archive/` 保存阶段审查证据，只描述当时状态。

业务行为发生变化时，至少更新状态、对应专项文档和变更记录；接口、测试或部署受影响时再更新相应文档。数字必须能在代码、构建报告或评测产物中找到来源。

文档移动、改名或新增后运行 `python scripts/check_docs.py`，它会检查全部 Markdown 中的本地相对链接（不访问网络）。
`archive/` 下的报告是当时的审查证据，不作为当前事实来源；若与专项文档冲突，以专项文档和代码为准。
