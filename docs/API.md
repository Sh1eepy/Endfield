# API 设计

FastAPI 实现在 `scripts/api_server.py`。接口服务 Web、微信小程序、离线评测和运维检查；输入边界、安全策略与业务路由保持分离。

## 技术选型

- **FastAPI + Pydantic v2**：同一进程提供 JSON API、SSE 与静态托管，边界校验由模型声明，避免手写解析；
- **同步端点**：检索、图谱查询和 LLM 调用都是阻塞代码，交给 FastAPI 的 threadpool 执行，不阻塞事件循环；
- **SSE 而非 WebSocket**：只需服务端单向推送，可复用 HTTP 准入、限流、Trace 和反向代理链路，客户端实现也更简单；
- **限额与并发分离**：额度是跨请求的 SQLite 计数，并发是进程内信号量，两者都必须在取用付费资源前完成；
- **受控错误信息**：接口使用明确的 HTTP `detail`；LLM 上游错误正文由 `_safe_body()` 截至 300 字并替换 API Key。该函数只处理 LLM 上游响应，不是通用日志脱敏器。


## 公开接口

| 方法与路径 | 用途 | 关键边界 |
|---|---|---|
| `GET /api/health` | 存活检查 | 不执行深度索引扫描 |
| `GET /api/names` | 全部可查询名称 | 客户端本地做前缀优先过滤 |
| `GET /api/synthesis` | 配方树、设备卡、知识库与干员详情 | `item` 最多 300 字，`max_depth` 为 0–10；配方索引与 KB 名称位置按进程缓存 |
| `POST /api/ask` | 整包知识问答 | `query` 1–300 字，`top_k` 1–10 |
| `POST /api/ask/stream` | SSE 知识问答 | 与整包接口共用路由、检索、额度和并发 |
| `POST /api/feedback` | 用户反馈隔离区 | 校验 trace、客户端、问题指纹和回答快照 |
| `GET /api/media` | WIKI 图片/音频代理 | HTTPS 域名/路径/MIME 白名单、25 MiB、禁重定向 |

`/api/health/deep` 和 `/api/metrics` 只允许回环客户端或有效令牌访问，生产 Nginx 还应禁止公网路由。

## 流式协议

`/api/ask/stream` 使用 UTF-8 SSE：

```text
phase → meta → delta × N → done
                         └→ error（失败）
```

- `meta` 先返回意图和来源；`delta` 只传答案增量；`done` 包含完整结果；
- 后端仅在模型给出受支持的 `finish_reason` 时标记正常完成；普通 EOF 不算成功；
- 并发名额、次数额度和 Trace 在 ASGI 真正开始响应时创建；只构造而未执行的响应不占名额、不扣次数；
- 客户端断开会在可检查的生成边界触发终止并释放并发名额；
- Web 在旧服务返回 404/405 时回退 `/api/ask`；小程序当前固定使用整包接口。

## 准入顺序

问答先验证令牌和输入，再尝试取得进程并发名额，成功后才写入 SQLite 次数额度。流式接口把后两步推迟到 ASGI 接管响应之后，并发已满仍返回 429。未执行的流式响应、并发已满请求不扣次数；已获准的请求即使后续生成失败，次数也不退还。

## 测试问题与对策

| 曾出现的问题 | 对策 | 覆盖位置 |
|---|---|---|
| 客户端断开后仍在付费生成 | 生成循环检查中止信号并在 chunk 边界退出，释放并发名额 | `test_ask_stream.py`、`api_security.py` 并发测试 |
| 流式响应已构造但正文未开始导致名额泄漏 | 准入推迟到响应执行期，响应层与生成线程明确交接且只释放一次 | `test_ask_stream.py` |
| 并发已满却已扣次数 | 准入顺序固定为"令牌 → 校验 → 并发 → 计数" | `test_api_security.py` |
| 流式没有 `done` 也被当成功 | 只有受支持 `finish_reason` 才算完成，普通 EOF 进入错误路径 | `test_ask_stream.py`、`test_backend_remediation.py` |
| 参数边界回退 | `query` 1–300 字、`top_k` 1–10、`max_depth` 0–10 有显式用例 | `tests/test_api_server.py`、`tests/test_frontend_contract.py` |
| 契约漂移（后端加字段、前端没跟上） | 字段变化必须同步 `web/src/types.ts`、`miniprogram/utils/api.js` 与契约测试 | 契约测试 + 前端 Vitest |
| 媒体代理被当作通用代理 | 域名/路径/MIME 白名单、禁重定向、大小与并发上限 | `test_api_security.py` |
| 任意 HTTP 400 触发 JSON 兼容重发 | 只有错误明确指出不支持 `response_format/json_object` 才去参重试 | `test_ask_stream.py` |

## 兼容与扩展

- 新响应字段应可选并带 schema/version；旧字段通过兼容层保留；
- 后端字段变化需同步 `web/src/types.ts`、`web/src/api.ts`、`miniprogram/utils/api.js` 和契约测试；
- 来源应逐步统一为 `EvidenceRef`：`source_id`、条目 ID、章节或 span、来源类型和打开方式；
- 管理令牌与未来用户身份应拆分，固定管理密钥不得进入 Web 或小程序包；
- 多实例部署前，应将 SQLite 限额和进程内指标替换为共享服务与集中监控。

安全细节见 [API_SECURITY.md](API_SECURITY.md)。
