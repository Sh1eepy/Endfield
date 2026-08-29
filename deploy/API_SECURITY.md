# API 访问与费用保护

此文说明仓库实现和配置要求，不表示线上 Nginx、域名或防火墙已经配置完成。

## 默认行为

- `/api/ask`：默认仍允许匿名访问，但每 IP 每个固定分钟窗口最多 6 次、每 IP 每日 60 次、全站每日 200 次。
  日窗口按 **UTC 00:00（北京时间 08:00）**重置，不是滚动 24 小时；分钟边界也不是滑动窗口。
  可用 `ASK_RATE_PER_MINUTE`、`ASK_IP_DAILY_LIMIT`、`ASK_DAILY_LIMIT` 调整，非正整数或无效值使用默认值，不能通过填 0 关闭保护。
- 每个 worker 同时执行最多 `ASK_MAX_CONCURRENCY=2` 个问答。所有问答请求（包括 `gen_answer=false`、结构化查询）均执行准入检查。
  已准入的请求即使后续失败、参数校验失败或并发满，也不退还次数；未授权或超过次数限制的请求不扣次数。
- 次数超限返回 429 和 `Retry-After`；计数数据库不可用返回 503，不放行付费调用。
- `/api/health/deep`、`/api/metrics`：应用层仅允许回环客户端或有效访问令牌；Nginx 继续禁止公网访问。
- `/api/feedback`：使用相同 SQLite 文件但独立计数，不占用问答额度；默认每 IP 每分钟 20 次、每日 200 次、
  全站每日 1000 次，可用 `FEEDBACK_RATE_PER_MINUTE`、`FEEDBACK_IP_DAILY_LIMIT`、`FEEDBACK_DAILY_LIMIT` 调整。
  它与问答使用同一可选 Bearer 令牌，并校验 `trace_id`、客户端、问题指纹和后端生成的回答快照，不能凭空写入反馈库。
- `/api/health`、`/api/names`、`/api/synthesis`、媒体和静态网页仍可公开访问，未添加用户注册/登录系统。

这些是**请求次数上限，不是人民币或 token 预算**。一次问答可能产生多次 LLM 调用、重试，仍需设置模型服务商的预算上限/告警。
匿名服务仍可能被恶意用户耗尽当天可用次数，IP 轮换可以绕过单 IP 限制，但不能突破同一计数库的全站上限；需要身份隔离时使用下方私有模式或接入真正的登录系统。

## 可选私有模式

在后端运行环境设置独立随机 `API_ACCESS_TOKEN`（不要复用 `LLM_API_KEY`）。之后调用 `/api/ask` 和
`/api/feedback` 必须携带：

```http
Authorization: Bearer <你的访问令牌>
```

缺失/错误令牌返回 401，正确令牌仍受次数与并发限制。此令牌也可访问管理接口；不要分发给匿名访客。
当前网页和小程序**不会自动携带这个令牌**，配置后它们的问答会返回 401，直到接入有身份验证的受信任网关或客户端。
不要把固定令牌写入 Vite 环境变量、网页源码、小程序包或 URL；也不要让公开 Nginx 无条件代填令牌，那不等于用户鉴权。
公开展示时可保持 `API_ACCESS_TOKEN` 为空，接受上述有限额匿名服务的边界。公网调用必须使用 HTTPS。

## 持久计数与多 worker

`scripts/api_security.py` 使用 SQLite 事务同时检查并递增三个计数，不会因多个 worker 同时准入而超发。
默认文件为 `logs/api-security/ask-budget.sqlite3`，不存问题、答案或令牌。重启进程会继续使用原计数。
旧窗口记录会在后续成功准入时清理。SQLite 文件必须位于有写权限的本地持久目录。

- Compose 已设置命名卷 `api-security`，文件位于 `/var/lib/endfield-security/ask-budget.sqlite3`；正常重建、更新和重启保留计数。
- **不要执行 `docker compose down -v` 或删除该卷**，否则次数会被重置。修改 Compose 项目名也会使用另一份卷。
- 手动 `docker run` 必须挂载命名卷并设置 `ASK_BUDGET_DB`，示例见根目录 `DEPLOYMENT.md`。
- Railway 等平台须自行挂载持久卷并将 `ASK_BUDGET_DB` 指向卷内路径，不能依赖容器临时文件系统。
- 同一主机上的 worker 必须使用同一文件。当前不是跨主机的分布式限流器；多主机部署需统一计数服务，不能各自使用独立 SQLite 或把它放到不可靠的网络文件系统。

## 代理 IP 与管理员检查

应用只使用 ASGI 的客户端地址，不自行解析 `X-Forwarded-For`、`X-Real-IP`。
Uvicorn 是否采信代理头由**启动进程环境变量** `FORWARDED_ALLOW_IPS` 控制；不要填 `*`，也不要允许不可信客户端网段。

Compose 默认将它设为空，最保守地不信任任何转发头。因此同一 Nginx 后面的访客会暂时共享应用层 IP 限额，Nginx 本身仍按真实访客 IP 限流。
上线前应从实际连接/访问日志核实**容器看到的 Nginx 对端地址**（常见为 Docker 网桥网关，不一定是 127.0.0.1），仅将这个受信任地址加入 `.env` 的 `FORWARDED_ALLOW_IPS`，再重建容器配置。
不经过 Docker、Nginx 和 Uvicorn 同机运行时，按实际连接填写 `127.0.0.1` 或 `::1`。
直接运行 uvicorn 时要在启动前设置该进程环境变量，不能依赖应用导入后才读取的 `.env` 来配置 Uvicorn。

模板 Nginx 用 `$remote_addr` **覆盖**转发头，不保留访客自带的伪造链；如上游有 CDN，应先严格配置 CDN 的可信 `real_ip` 范围。
必须保持 Docker 的 8000 端口仅绑定宿主机回环地址，并确保其他不可信容器无法冒用受信任的代理来源。

Docker 下宿主机 `127.0.0.1:8000` 的请求，在容器内不一定显示为回环地址；无令牌的深度检查推荐进入容器执行：

```bash
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/deep').read().decode())"
```

将路径改为 `/api/metrics` 可查看进程指标。不进入容器时可使用令牌访问管理接口，但不要把真实令牌提交或打印到日志。

## 媒体代理边界

- 只接受无用户信息、默认/443 端口的 `https://bbs.hycdn.cn/image/…` 或 `/audio/…`。
- 不跟随任何重定向，收到 3xx 直接返回 502，绝不请求 `Location` 中的地址。
- `Content-Length` 超过 25 MiB 时不读取正文；没有长度或长度不可信时，按 64 KiB 分块读取并累计，超过上限立即停止、关闭上游连接并返回 413。
- 请求 `identity` 编码，拒绝其他压缩编码，避免自动解压在大小检查前大量分配内存。
- 只返回图片/音频；不支持的类型返回 415。上游 I/O 超时 25 秒，读取过程中另检查总读取时长。
- 每个 worker 最多 `MEDIA_MAX_CONCURRENCY=2` 个下载/发送中的媒体响应；页面图片突发最多等待 5 秒获取名额，仍繁忙则返回 429。
  上游读取结束后仍持有名额，直到发送完成或断开连接，避免慢客户端积累大量已下载的内存缓冲。

这是**有上限的分块下载后返回**，不是下载无限大文件再检查，也不是零缓冲转发。
内存仍包含最多 25 MiB 的单响应缓冲及转换开销；提高 worker 或媒体并发数会增加总内存，不能把并发设置得过大。
不承诺防御所有流量攻击；公网仍需要入口连接限制、监控与网络出站策略。

## 离线验证

```bash
python -m unittest scripts.test_api_security -v
node --test miniprogram/tests/ask.test.cjs
```

测试模拟上游响应、私网重定向、超大流和 LLM，不访问真实 CDN/私网，不产生模型费用。
上线后仍需核实真实代理 IP、持久卷、HTTPS 和正常图片/音频，不要把本地模拟测试当作线上验收。
