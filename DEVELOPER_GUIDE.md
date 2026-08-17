# 开发者文档 — 终末地配方合成树

> 面向接手项目的开发者。本文档讲清楚系统每一层"在做什么、怎么做、为什么这样做"。
> 所有内容以当前仓库真实代码为准。

## 0. 一分钟看懂

这个项目做一件事：**基于《明日方舟：终末地》官方 WIKI 的 1958 条数据**，
给用户一个网页——顶部**搜索框带模糊联想**（输入"中"弹出"中"开头选项），
下方 **D3 配方合成树** 展示一个物品怎么一步步造出来（叶子收敛到基础资源）。

```
WIKI 全量 JSON（块式富文本）
  → 按分类提取（build_kb_all）→ endfield_kb/*.jsonl
  → RAG 索引（build_rag）→ output/rag/
  → 后端（api_server.py）：/api/synthesis 合成树 + /api/names 搜索联想
  → 前端（web/index.html）：白色工业制图，纵向图片配方树 + 知识问答双模式
```

## 1. 数据层：从 WIKI 到结构化知识

### 1.1 `wiki_collector.js`（了解即可）
WIKI 是网页应用，接口强制登录+签名。采集脚本在你已登录的浏览器控制台运行，
借站内已认证 API 拿数据，凭证不离开浏览器。产物是 `endfield_wiki_full_*.json`。

### 1.2 `build_kb_all.py` — 按分类提取（核心）
把块式富文本文档渲染成可读文本，按 `subTypeId` 分组，每个分类输出：
- `endfield_kb/{分类}.jsonl`：RAG 输入，格式 `{item_id, name, category, sections, full_text}`
- `endfield_kb/{分类}.md`：人类可读
- `endfield_kb/_catalog.json`：22 个分类清单

渲染要点：`documentMap.blockMap` 里块类型有 `text / list / table / image`，
inline 元素 `text / entry(物品引用,含数量count与样式showType) / link(外链) / image`，递归渲染成文本。
- entry → `名称×数量`（多个 entry 用空格分隔，避免粘连）
- link → 链接文本（不丢外链）；image 块 → `[图片](url)`（不丢图片位置）
- 同时输出 **`sections_struct`**（结构化块：text/table/image/entry），供前端渲染**真表格/真图片/可点击物品卡片**（jsonl 多一个字段，`full_text` 不变，RAG 无需重建）

### 1.3 `recipe_extract.py` → `output/recipes.json`
从设备条目的"相关配方"表格提取配方（原料/产物/耗时秒数），**不做激进清洗**——
设备制造/容器"盛装"/矿机/原木配方全保留（共 345 个），供合成树完整展示"怎么造"。
合成树算法的剪枝规则（自循环排除/循环剪枝/种子叶子）负责保证树干净。
**合成树的数据源就是它**。

### 1.4 `recipe_index.py` — 配方索引工具
`load_recipes / build_item_index / find_item_ids_by_name` 三个通用函数，
供 `api_server.py` 与 `eval_rag.py` 复用（从 recipes.json 构建物品→配方索引、按名查 ID）。

### 1.5 `extract_media.py` → `output/item_media.json`
WIKI 原始 JSON 里的结构信息（此前被 build_kb_all/recipe_extract 丢弃）：
- 条目封面图 `brief.cover`（1957 条）+ 配图 `document.extraInfo.illustration`
- 正文图片块 `blockMap.image`（2046 个，bbs.hycdn.cn）
- 外链 `inline link`（291 个，url+text）
- 物品引用 `inline entry`（14693 条，含数量 count 与链接样式 showType=card-big/link-imgText）
`/api/synthesis` 用它在响应顶层附加 `cover` 与 `refs`，前端据此展示封面图与可点击引用卡片。

## 2. RAG 层：语义检索

### 2.1 构造（`build_rag.py`）
- 读 `endfield_kb/*.jsonl` → 每条切 chunk（短条目整条；超长按 sections 拆，512 字上限）
- **embedding**：`BAAI/bge-small-zh-v1.5`（512 维）→ 写 ChromaDB（cosine 空间）
- **BM25 按分类分片**：`output/rag/bm25/{分类}.pkl`（每分类一个倒排索引，互不影响）
- `chunks.json` 是 **manifest**：每条含 `id/text/meta/hash`（hash = 条目 full_text 的 md5），供增量对比

### 2.2 检索（`rag_search.py`）
- 双路召回：向量 top-N + BM25 跨分片 top-N → **RRF 融合**（score = Σ 1/(k+rank)）→ 取 top-k
- 每条命中带 `meta（分类/名称/ID）/text/score/vector_sim/bm25_score`

### 2.3 增量更新（推荐做法，`--incremental`）
**为什么需要**：全量重建要重 embedding 几千 chunk（分钟级）+ 占用资源；实际数据每次只变一点点。

**做法（三步）**：
1. 每条记录算 `content_hash`（md5(full_text)）写入 manifest
2. `--incremental` 时对比新旧 manifest：只有 hash 变化的条目才重新 embedding（几十条 vs 几千条）
3. ChromaDB 只 `upsert` 变更 chunk / `delete` 删除条目；**BM25 只重建变更条目所属分类的分片**

实测：全量 2914 chunks 约 3 分钟；改 1 条 → 只重 embedding 1 chunk + 只重建 1 个分类分片。

## 3. 合成树：配方链可视化

### 3.1 算法（`api_server.py /api/synthesis`）
从目标物品递归展开配方树，四条关键规则（**改这些要小心**）：
1. **叶子 = 基础资源**（`_is_base`）：清水/惰气/息壤气（免费资源）、无产出配方的矿物、**种子类**（种植循环终止点）；植物类（芽针/锦草等）正常展开种植机配方
2. **配方选择**（`_pick_producers`）：排除自循环配方，按（输入数少、输入含基础资源多）排序，**最多 2 个**
3. **剪枝**：循环（物品出现在当前路径）或超深（**深度上限 10**）的**分支直接剪掉**，保证叶子必然是基础资源，不显示"已截断"
4. **歧义匹配**：名称匹配多个（如"灼铜"→气态灼铜/灼铜块/...）→ 返回 `ambiguous+candidates` 候选列表，前端让用户选择；**无配方物品回退知识库**返回物品信息

**为什么这样设计**：早期版本把每个物品的所有配方都展开、遇环标"已截断"，
导致树指数爆炸、出现大量截断和"重息壤⇄重息壤气"这类奇妙分支。现在收敛到基础资源，树干净可读。

### 3.2 两种返回
- **物品**（有产出配方）→ 树：`{name, recipes:[{machine, duration, inputs:[子物品树]}]}`
- **设备**（如"天有洪炉"）→ 配方卡片：`{name, kind:'device', recipes:[{machine, inputs, outputs}]}`
- 所有成功响应均带 `cover`（封面图 URL）与 `refs`（相关引用卡片，前端点击站内跳转），数据来自 `output/item_media.json`

## 4. 名称建议（`/api/names`）
返回全部名称（配方物品 + 设备 + 知识库条目，约 1908 个），首次加载后缓存。
前端在输入时本地模糊过滤：**前缀匹配优先 + 包含匹配**，下拉联想（支持键盘上下/Enter）。

## 5. 前端（`web/index.html`）
- **白色工业制图 v3**：白/灰/工业黄高对比视觉，大标题首屏 + 终端式搜索 + 档案侧栏 + 配方树/知识问答工作区
- 背景与装饰均为 CSS 原创网格/几何线/警示构件，不依赖官网图片；首屏、模式、结果和滚动带动效，并尊重 `prefers-reduced-motion`
- 桌面为侧栏+主工作区，850px 以下折叠侧栏，520px 以下进一步精简状态文字与搜索前缀
- D3 树：物品和设备均为固定尺寸切角图片卡片，边上标 `×数量`，hover 显示耗时/数量。
- 点击非叶子物品卡片可展开/收起；点击物品名称可直接查询该物品。折叠状态只属于当前树。
- 最近 8 条配方/问答查询保存在浏览器 `localStorage`（键 `endfield-search-history-v1`），不上传后端。
- v3 配方树为自上而下布局，物品和设备均显示 `item_media.json` 的真实封面；设备封面由后端写入 recipe 节点的 `cover`。
- 节点保持固定尺寸，超宽树在 `#syn-tree` 内横向滚动；工具栏支持全树展开/收起和 70%–135% 缩放。
- 默认不发起查询，使用 `renderEmptyState()` 提供可点击示例；不要恢复硬编码默认物品。
- 物品与设备节点使用 `item_media.json` 的真实封面；结果区顶部显示目标物品封面大图。
- 结果区显示**相关引用卡片**（`refs`，含数量角标，点击即切换该物品的合成树）
- 知识库卡用 **`sections_struct` 结构化渲染**：图片显示为真图、表格显示为真表格、物品 entry 变成可点击卡片（跳转合成树）
- 设备查询 → 配方卡片列表；无配方物品 → 知识库信息卡
- D3 从本地 `web/vendor/d3.min.js` 加载（离线可用）

## 6. 启动与验证
```powershell
python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000
# 浏览器 http://127.0.0.1:8000（不要用 localhost，见 AGENTS.md）
curl "http://127.0.0.1:8000/api/synthesis?item=重息壤"
curl http://127.0.0.1:8000/api/names
```

## 7. 已知注意事项 / 坑
- 前端 JS 修改后用 `node --check` 验证（提取 `<script>` 内容）
- 合成树"奇妙分支"= 配方选择/剪枝被改动；叶子必须保持基础资源
- `build_rag.py --incremental` 首次需要先 `--reset` 建基线 manifest
- `.env` 含密钥，勿提交公开仓库
- ⚠️ **bbs.hycdn.cn 有 Referer 防盗链**：非白名单 Referer（如 `http://127.0.0.1:8000`）返回 403（图片显示"损坏"）
  → 前端所有图片加载必须设 `referrerpolicy="no-referrer"`（`<img>` 和 SVG `<image>` 都要）
- 表格单元格里的"超链接图片"= `entry` 元素（showType=card-big/link-imgText），渲染时必须输出名称（带 ×数量）并用空格分隔多个 entry
