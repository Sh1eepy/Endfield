# GraphRAG 专项说明

> 统一流程见 [`KNOWLEDGE_SYSTEM_ARCHITECTURE.md`](../KNOWLEDGE_SYSTEM_ARCHITECTURE.md)。这里专门说明图谱部分。

## 它解决什么

RAG 擅长找原文，知识图谱擅长找明确关系和路径。项目把两者组合起来：

```text
关系问题 → 图检索 → 路径和证据 → LLM 整理
图未命中 → 文本 RAG 回退
主观问题 → 原文证据，不把模型判断写成事实边
```

知识图谱本身不等于 GraphRAG；只有图检索参与问答，并与原文证据协作时，才构成这里的混合 GraphRAG。

## 图里有什么

- 实体：人物、任务、地点、组织、物品、设备、配方等；
- 关系：隶属、任务参与者、任务地点、前后置、生产、消耗、推荐、获取、明确亲属和管理关系；
- 证据：每条边保存来源条目、原文片段、置信度、提取方法和审查状态；
- 别名：只保存审定过的名称映射，不把模糊相似词自动当别名。

当前产物位于 `output/knowledge_graph/graph.db`，全量结果为 2129 个实体、9358 条关系、1958 个来源。

## 怎么构建和更新

`build_knowledge_graph.py` 从规范化知识库和配方数据中按白名单规则提取关系。同场出现只作为检索线索，
不会自动生成事实边。更新时比较来源哈希；来源变化后先删除它产生的旧关系，再重新提取。

```powershell
python scripts/build_knowledge_graph.py --reset
python scripts/build_knowledge_graph.py --incremental
```

## 查询规则

- 明确关系词或两个实体触发图查询；
- 默认最多 3 跳，避免路径爆炸；
- 正向、反向和是非问应该返回同一证据；
- 图中无路径不能解释成关系不存在；
- “关系怎么样、是否喜欢、性格如何”回到原文证据。

例如“武陵的领袖是谁”会查管理关系；回答仍保留原文“管代/管理负责人”的含义，不扩大成没有证据的
政治职务。“陈千语和诀的关系”可通过共同任务路径回答，同时把任务原文交给模型说明。

## 审查和门禁

```powershell
python scripts/graph_audit.py
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/quality_gate.py
```

检查内容包括悬空端点、缺失来源、非法自环、关系证据、固定问题路径，以及各关系类型的正向、反向、
是非问。当前图评测 10/10，自动关系审查 1656/1656。

这些数字只说明现有规则和固定数据没有回退。新增剧情关系前仍应补人工金标，尤其是别名、冲突、三跳和拒答。
