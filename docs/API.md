# API 设计

FastAPI 实现在 `scripts/api_server.py`。接口服务 Web、微信小程序、离线评测和运维检查；输入边界、安全策略与业务路由保持分离。本文说明仓库实现与配置要求，不表示线上 Nginx、域名或防火墙已经配置完成。

## 1. 技术选型

- **FastAPI + Pydantic v2**：同一进程提供 JSON API、SSE 与静态托管，边界校验由模型声明，避免手写解析；
- **同步端点**：检索、图谱查询和 LLM 调用都是阻塞代码，交给 FastAPI 的 threadpool 执行，不阻塞事件循环；
- **SSE 而非 WebSocket**：只需服务端单向推送，可复用 HTTP 准入、限流、Trace 和反向代理链路，客户端实现也更简单；
- **限额与并发分离**：额度是跨请求的 SQLite 计数，并发是进程内信号量，两者都必须在取用付费资源前完成；
- **受控错误信息**：接口使用明确的 HTTP `detail`；LLM 上游错误正文由 `_safe_body()` 截至 300 字并替换 API Key。该函数只处理 LLM 上游响应，不是通用日志脱敏器。

## 2. 公开接口

| 方法与路径 | 用途 | 关键边界 |
|---|---|---|
| `GET /api/health` | 存活检查 | 不执行深度索引扫描 |
| `GET /api/names` | 全部可查询名称 | 客户端本地做前缀优先过滤 |
| `GET /api/synthesis` | 配方树、设备卡、知识库与干员详情 | `item` 最多 300 字，`max_depth` 为 0–10；配方索引与 KB 名称位置按进程缓存 |
| `POST /api/ask` | 整包知识问答 | `query` 1–300 字，`top_k` 1–10 |
| `POST /api/ask/stream` | SSE 知识问答 | 与整包接口共用路由、检索、额度和并发 |
| `POST /api/feedback` | 用户反馈隔离区 | 校验 trace、客户端、问题指纹和回答快照 |
| `GET /api/media` | WIKI 图片/音频代理 | HTTPS 域名/路径/MIME 白名单、25 MiB、禁重定向 |

- `/api/health/deep` 和 `/api/metrics` 只允许回环客户端或有效令牌访问，生产 Nginx 还应禁止公网路由；`/api/health`、`/api/names`、`/api/synthesis`、媒体和静态网页仍可公开访问，未添加用户注册/登录系统。

## 3. 流式协议

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

## 4. 准入顺序与额度

问答准入顺序固定为**令牌 → 输入校验 → 并发名额 → SQLite 次数额度**：

- 流式接口把后两步推迟到 ASGI 接管响应之后，并发已满仍返回 429；
- 未执行的流式响应、并发已满请求不扣次数；已获准的请求即使后续生成失败，次数也不退还；
- 每个 worker 同时执行最多 `ASK_MAX_CONCURRENCY=2` 个问答，所有问答请求（包括 `gen_answer=false`、结构化查询）均执行准入检查。

`/api/ask` 默认仍允许匿名访问，额度如下：

- 每 IP 每个固定分钟窗口最多 6 次、每 IP 每日 60 次、全站每日 200 次；
- 日窗口按 **UTC 00:00（北京时间 08:00）** 重置，不是滚动 24 小时；分钟边界也不是滑动窗口；
- 可用 `ASK_RATE_PER_MINUTE`、`ASK_IP_DAILY_LIMIT`、`ASK_DAILY_LIMIT` 调整，非正整数或无效值使用默认值，不能通过填 0 关闭保护；
- `/api/ask/stream` 与 `/api/ask` 共用同一准入检查、次数限制与 `ASK_MAX_CONCURRENCY` 并发名额，一次流式问答计一次准入；
- 次数超限返回 429 和 `Retry-After`；计数数据库不可用返回 503，不放行付费调用；
- `/api/feedback` 使用相同 SQLite 文件但独立计数，不占用问答额度：默认每 IP 每分钟 20 次、每日 200 次、全站每日 1000 次，可用 `FEEDBACK_RATE_PER_MINUTE`、`FEEDBACK_IP_DAILY_LIMIT`、`FEEDBACK_DAILY_LIMIT` 调整；
- `/api/health`、`/api/names`、`/api/synthesis`、媒体和静态网页不受问答额度约束；Nginx 模板另限合成查询为每 IP 平均 60 次/分钟、媒体为 120 次/分钟且同时最多 4 个连接；
- 这些是**请求次数上限，不是人民币或 token 预算**：一次问答可能产生多次 LLM 调用与重试，仍需设置模型服务商的预算上限/告警。

`scripts/api_security.py` 用 SQLite 事务同时检查并递增三个计数，多个 worker 同时准入也不会超发：

- 默认文件为 `logs/api-security/ask-budget.sqlite3`，必须位于有写权限的本地持久目录，重启进程继续沿用原计数，旧窗口记录在后续成功准入时清理；
- Compose 已设置命名卷 `api-security`，文件位于 `/var/lib/endfield-security/ask-budget.sqlite3`，正常重建、更新和重启保留计数；
- **不要执行 `docker compose down -v` 或删除该卷**，否则次数会被重置；修改 Compose 项目名也会使用另一份卷；
- 手动 `docker run` 必须挂载命名卷并设置 `ASK_BUDGET_DB`，Railway 等平台须自行挂载持久卷并把 `ASK_BUDGET_DB` 指向卷内路径，不能依赖容器临时文件系统（示例见 [DEPLOYMENT.md](DEPLOYMENT.md)）；
- 同一主机上的 worker 必须使用同一文件；当前不是跨主机的分布式限流器，多主机部署需统一计数服务，不能各自使用独立 SQLite 或把它放到不可靠的网络文件系统。

## 5. 鉴权与访问控制

默认匿名：`/api/ask`、`/api/ask/stream` 和 `/api/feedback` 可直接调用，受上述额度与并发约束。在后端运行环境设置独立随机 `API_ACCESS_TOKEN`（不要复用 `LLM_API_KEY`）后进入可选私有模式，这三个接口必须携带：

```http
Authorization: Bearer <你的访问令牌>
```

- 缺失/错误令牌返回 401，正确令牌仍受次数与并发限制；该令牌也可访问管理接口，不要分发给匿名访客；
- 当前网页和小程序**不会自动携带这个令牌**，配置后它们的问答会返回 401，直到接入有身份验证的受信任网关或客户端；
- 不要把固定令牌写入 Vite 环境变量、网页源码、小程序包或 URL，也不要让公开 Nginx 无条件代填令牌，那不等于用户鉴权；
- 公开展示时可保持 `API_ACCESS_TOKEN` 为空，接受上述有限额匿名服务的边界；公网调用必须使用 HTTPS。

匿名服务仍可能被恶意用户耗尽当天可用次数；IP 轮换可以绕过单 IP 限制，但不能突破同一计数库的全站上限。需要身份隔离时使用私有模式或接入真正的登录系统。

## 6. 代理与网络边界

- 应用只使用 ASGI 的客户端地址，不自行解析 `X-Forwarded-For`、`X-Real-IP`；Uvicorn 是否采信代理头由**启动进程环境变量** `FORWARDED_ALLOW_IPS` 控制，不要填 `*`，也不要允许不可信客户端网段；
- Compose 默认将它设为空，最保守地不信任任何转发头，因此同一 Nginx 后面的访客会暂时共享应用层 IP 限额，Nginx 本身仍按真实访客 IP 限流；
- 上线前应从实际连接/访问日志核实**容器看到的 Nginx 对端地址**（常见为 Docker 网桥网关，不一定是 127.0.0.1），仅将这个受信任地址加入 `.env` 的 `FORWARDED_ALLOW_IPS`，再重建容器配置；不经 Docker、Nginx 和 Uvicorn 同机运行时，按实际连接填写 `127.0.0.1` 或 `::1`；
- 直接运行 uvicorn 时要在启动前设置该进程环境变量，不能依赖应用导入后才读取的 `.env` 来配置 Uvicorn；
- 模板 Nginx 用 `$remote_addr` **覆盖**转发头，不保留访客自带的伪造链；如上游有 CDN，应先严格配置 CDN 的可信 `real_ip` 范围；
- 必须保持 Docker 的 8000 端口仅绑定宿主机回环地址，并确保其他不可信容器无法冒用受信任的代理来源。

Docker 下宿主机 `127.0.0.1:8000` 的请求，在容器内不一定显示为回环地址；无令牌的深度检查推荐进入容器执行：

```bash
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/deep').read().decode())"
```

将路径改为 `/api/metrics` 可查看进程指标。不进入容器时可使用令牌访问管理接口，但不要把真实令牌提交或打印到日志。

## 7. 媒体代理安全

- 只接受无用户信息、默认/443 端口的 `https://bbs.hycdn.cn/image/…` 或 `/audio/…`；
- 不跟随任何重定向，收到 3xx 直接返回 502，绝不请求 `Location` 中的地址；
- `Content-Length` 超过 25 MiB 时不读取正文；没有长度或长度不可信时，按 64 KiB 分块读取并累计，超过上限立即停止、关闭上游连接并返回 413；
- 请求 `identity` 编码，拒绝其他压缩编码，避免自动解压在大小检查前大量分配内存；
- 只返回图片/音频，不支持的类型返回 415；上游 I/O 超时 25 秒，读取过程中另检查总读取时长；
- 每个 worker 最多 `MEDIA_MAX_CONCURRENCY=2` 个下载/发送中的媒体响应；页面图片突发最多等待 5 秒获取名额，仍繁忙则返回 429；上游读取结束后仍持有名额，直到发送完成或断开连接，避免慢客户端积累大量已下载的内存缓冲；
- 模板已为 `/api/media` 配置独立频率与连接限制，不要让它继续落入无约束的通用 `location /`；应用内媒体下载仍受全局并发上限保护。

这是**有上限的分块下载后返回**，不是下载无限大文件再检查，也不是零缓冲转发。内存仍包含最多 25 MiB 的单响应缓冲及转换开销，提高 worker 或媒体并发数会增加总内存，不能把并发设置得过大。不承诺防御所有流量攻击；公网仍需要入口连接限制、监控与网络出站策略。

## 8. 隐私与数据保留

- 计数库 `ask-budget.sqlite3` 只保存限额计数，不存问题、答案或令牌；普通问答链路只以 `trace_id` 与问题指纹等最小字段关联，回答正文只随 `/api/feedback` 进入隔离区；
- `/api/feedback` 与问答使用同一可选 Bearer 令牌，并校验 `trace_id`、客户端、问题指纹和后端生成的回答快照，不能凭空写入反馈库。

## 9. 测试问题与对策

| 曾出现的问题 | 对策 | 覆盖位置 |
|---|---|---|
| 客户端断开后仍在付费生成 | 生成循环检查中止信号并在 chunk 边界退出，释放并发名额 | `test_ask_stream.py`、`api_security.py` 并发测试 |
| 流式响应已构造但正文未开始导致名额泄漏 | 准入推迟到响应执行期，响应层与生成线程明确交接且只释放一次 | `test_ask_stream.py` |
| 并发已满却已扣次数 | 准入顺序固定为“令牌 → 校验 → 并发 → 计数” | `test_api_security.py` |
| 流式没有 `done` 也被当成功 | 只有受支持 `finish_reason` 才算完成，普通 EOF 进入错误路径 | `test_ask_stream.py`、`test_backend_remediation.py` |
| 参数边界回退 | `query` 1–300 字、`top_k` 1–10、`max_depth` 0–10 有显式用例 | `tests/test_api_server.py`、`tests/test_frontend_contract.py` |
| 契约漂移（后端加字段、前端没跟上） | 字段变化必须同步 `web/src/types.ts`、`miniprogram/utils/api.js` 与契约测试 | 契约测试 + 前端 Vitest |
| 媒体代理被当作通用代理 | 域名/路径/MIME 白名单、禁重定向、大小与并发上限 | `test_api_security.py` |
| 任意 HTTP 400 触发 JSON 兼容重发 | 只有错误明确指出不支持 `response_format/json_object` 才去参重试 | `test_ask_stream.py` |

离线验证（模拟上游响应、私网重定向、超大流和 LLM，不访问真实 CDN/私网，不产生模型费用）：

```bash
python -m unittest scripts.test_api_security -v
node --test miniprogram/tests/ask.test.cjs
```

上线后仍需核实真实代理 IP、持久卷、HTTPS 和正常图片/音频，不要把本地模拟测试当作线上验收。

## 10. 兼容与扩展

- 新响应字段应可选并带 schema/version；旧字段通过兼容层保留；
- 后端字段变化需同步 `web/src/types.ts`、`web/src/api.ts`、`miniprogram/utils/api.js` 和契约测试；
- 来源应逐步统一为 `EvidenceRef`：`source_id`、条目 ID、章节或 span、来源类型和打开方式；
- 管理令牌与未来用户身份应拆分，固定管理密钥不得进入 Web 或小程序包；
- 多实例部署前，应将 SQLite 限额和进程内指标替换为共享服务与集中监控。
