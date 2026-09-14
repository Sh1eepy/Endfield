# 部署与运维

> 更新日期：2026-09-14。本文是部署入口总纲与自有服务器运维手册：推荐架构、关键设计决策、完整命令序列、验收、更新、回滚与排障。
> 鉴权模式、限流额度、可信代理与额度持久化细节见 [API.md](API.md)。

## 1. 推荐架构与路径选择

```text
子域名 → Nginx/HTTPS → 127.0.0.1:8000 → Docker Compose → FastAPI + Web + RAG
```

网页使用相对路径访问 `/api/*`，任何部署都不需要拆分前端服务。三条路径：自有服务器 + 子域名（正式生产，推荐，见第 3~8 节）、本地 Docker（本机验证/离线开发）、Railway（无自有服务器）。

**本地 Docker**（需 Docker Desktop）：不传 `.env` 时配方树/设备卡/知识库回退仍可用，在线 LLM 回答才需要注入 `LLM_API_KEY` 等。启动后打开 `http://127.0.0.1:8000`，`curl http://127.0.0.1:8000/api/health` 验证。

```powershell
docker build -t endfield-synthesis .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -e ASK_BUDGET_DB=/var/lib/endfield-security/ask-budget.sqlite3 -v endfield-api-security:/var/lib/endfield-security endfield-synthesis
```

**Railway**：推仓库到 GitHub 并建项目选该仓库（`railway.json` 选 Dockerfile 构建）；设置 LLM 环境变量 + `ASK_MAX_CONCURRENCY=2`，首次 `WEB_CONCURRENCY=1`（每 worker 独立加载模型/索引）；挂持久卷并把 `ASK_BUDGET_DB` 指向卷内文件；健康检查 `/api/health` 超时 300s，启动预热在该窗口内完成；不要上传 `.env`。

## 2. 关键设计决策

- **镜像构建时重建 RAG**：`output/rag/chroma/` 和 HF 模型缓存不进入 Git（前者可重建、后者体积大）。Dockerfile 构建阶段装 CPU 版 torch（避免 CUDA 库入镜像）→ 下载 `bge-small-zh-v1.5` → `HF_HUB_OFFLINE=1` → 从 `endfield_kb/*.jsonl` 全量重建 Chroma/BM25/manifest → 运行阶段的 embedding 与检索离线；生成式回答仍需访问配置的 LLM 服务。首次构建慢且镜像大是离线 RAG 的成本，不要把真实密钥烘焙进镜像。
- **容器只监听 127.0.0.1:8000**：公网入口统一交给 Nginx，绝不改成 `0.0.0.0:8000`；公网只开 80/443。
- **流式问答与启动预热**：容器入口是 `start_server.py`，单进程默认预热 embedding 模型与索引（冷启动落在健康检查 `start_period` 内；内存极紧可设 `RAG_PREWARM=0`）。Nginx 模板 `deploy/nginx/endfield.conf` 已为 `/api/ask/stream` 关闭 `proxy_buffering` 并把读超时放宽到 300s；更新线上 Nginx 时必须同步保持，否则网页问答失去逐字输出。
- **应用层与读取接口都有保护**：问答 `query` 1~300 字符、`top_k` 1~10；每 IP 每分钟 6 次 / 每日 60 次 / 全站每日 200 次（UTC 日窗口，SQLite 计数走 Compose 命名卷跨重建保留）；可选 Bearer 令牌私有模式；反馈接口用同一 SQLite 的独立限额并校验 Trace、客户端、问题和回答快照。Nginx 对匿名可读的 `/api/synthesis` 限每 IP 平均 60 次/分钟，对 `/api/media` 限 120 次/分钟和 4 个并发连接；整包 `/api/ask` 代理读写超时 180 秒，流式接口 300 秒。
- **问答 Trace 数据**：`RAG_TRACE_DB` 配置，Compose 默认放持久卷。普通 Trace 不含问题/答案正文，用户主动反馈才保存当次文本——该库与回放报告按用户内容处理（限制管理员访问、纳入保留期、不提交 Git）。

## 3. 交付前准备

- 一台可 SSH 管理的 Linux 服务器，建议 Ubuntu 22.04/24.04 x86_64，至少 4 GB 内存和 15 GB 可用磁盘，首次保持 `WEB_CONCURRENCY=1`；
- 一个子域名，A 记录指向服务器公网 IPv4；只有服务器确实配置了 IPv6 时才添加 AAAA；
- 防火墙开放 SSH、80、443，不开放 8000；安装 Git、Nginx、Docker Engine 和 Docker Compose Plugin（用 Docker 官方仓库版本：<https://docs.docker.com/engine/install/ubuntu/>、<https://docs.docker.com/compose/install/linux/>）。

```bash
docker version
docker compose version
sudo nginx -t
```

主机若由朋友管理，采用「你管应用、朋友管主机」分工：

| 你负责（应用） | 朋友负责（主机） |
|---|---|
| GitHub、SSH 登录、项目目录、`.env`、Docker Compose、应用日志、后续更新 | 创建部署用户、添加 SSH 公钥、DNS、Docker 权限、Nginx、HTTPS、防火墙 |

执行前统一四个占位符（命令里必须替换）：`<SERVER_IP>` 公网 IPv4、`<SSH_PORT>`（默认 22）、`<DEPLOY_USER>`（建议 `endfielddeploy`）、`<SUBDOMAIN>` 实际子域名。边界与安全要点：

- 生成本次部署**专用** ed25519 密钥（`ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\endfield_deploy"`），只把 `.pub` 公钥发给朋友，私钥绝不出本机；朋友不交出 root 密码，你不修改朋友服务器上的其他站点；
- 朋友创建独立部署用户 + `authorized_keys`（目录 700 / 文件 600），加入 `docker` 组（**权限极高**，朋友须同意，不愿授予则由朋友代执行 compose 命令），加组后必须退出重登才生效；`permission denied` 时退出重登并检查 `id <DEPLOY_USER>` 是否含 docker 组，**不要**把 socket 改成 777；
- `.env` 只在服务器（`chmod 600`），不在聊天/截图/日志中展示；DNS 用 Cloudflare 时首发只选「仅 DNS」；HTTP 通之前不要申请证书；`/opt/endfield` 非空时先 `ls -la` 确认，不要直接删除。

## 4. 拉取项目与配置密钥

以 `/opt/endfield` 为项目目录：

```bash
sudo mkdir -p /opt/endfield
sudo chown "$USER":"$USER" /opt/endfield
git clone https://github.com/Sh1eepy/Endfield.git /opt/endfield
cd /opt/endfield
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，至少填写：

```dotenv
LLM_API_KEY=实际密钥
LLM_BASE_URL=实际 OpenAI 兼容端点
LLM_MODEL=实际模型名
LLM_TIMEOUT=60
WEB_CONCURRENCY=1
ASK_MAX_CONCURRENCY=2
# 可选：默认 1（启动预热 embedding 与索引）；内存极紧时设 0
RAG_PREWARM=1
```

`.env` 只保存在服务器，不能提交到 Git，额度默认值可在 `.env` 调整。`API_ACCESS_TOKEN` 留空保留有次数限制的匿名服务；设置后问答必须鉴权，当前网页/小程序不能直接使用该私有模式。请求次数不是金额预算，仍需模型服务商的预算上限/告警。

## 5. 构建与启动

首次构建会下载 CPU PyTorch 和 embedding 模型，并在镜像中重建 RAG 与知识图谱，耗时和磁盘占用都比普通 Web 镜像大。

```bash
cd /opt/endfield
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 app
curl http://127.0.0.1:8000/api/health
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/deep').read().decode())"
```

## 6. Nginx 与 HTTPS

先在 DNS 控制台添加子域名 A 记录，等它解析到服务器公网 IP，再把模板中的 `YOUR_SUBDOMAIN.example.com` 替换为实际子域名。

```bash
cd /opt/endfield
sudo cp deploy/nginx/endfield.conf /etc/nginx/sites-available/endfield
sudo nano /etc/nginx/sites-available/endfield
sudo ln -s /etc/nginx/sites-available/endfield /etc/nginx/sites-enabled/endfield
sudo nginx -t
sudo systemctl reload nginx
curl http://实际子域名/api/health
```

符号链接已存在时不要重复创建，直接检查文件内容并执行 `nginx -t`。

域名走 Cloudflare 等代理时首发先用「仅 DNS」，否则 Nginx 看到的可能是代理节点 IP，按 IP 限流会把不同用户误认为同一人；要开启代理，先按服务商官方网段配置 Nginx `real_ip`，不要无条件信任任意来源的 `X-Forwarded-For`。同时按 [API.md](API.md) 核实并设置 `FORWARDED_ALLOW_IPS` 的精确代理对端地址——Compose 默认不信任转发头，未配置时同一代理后的访客会共享应用层 IP 限额，不要填 `*`。

Nginx 对 `/api/ask` 的默认保护：单 IP 平均每分钟 6 次、突发 2 次、同时最多 1 个问答，超出返回 HTTP 429；`/api/ask/stream` 与 `/api/ask` 共用这组限制和应用层并发名额。模板中该 location 已关闭 `proxy_buffering` 并把 `proxy_read_timeout` 放宽到 300s，改动线上 Nginx 时必须同步保持，否则代理会攒批、网页问答失去逐字输出；整包 `/api/ask` 的读写超时为 180s，用于覆盖小程序整包生成窗口。

Certbot 要求普通 HTTP 站点先能从公网通过 80 端口访问，按官方 Nginx 流程安装（<https://certbot.eff.org/instructions?ws=nginx&os=ubuntufocal>）：

```bash
sudo certbot --nginx -d 实际子域名
sudo certbot renew --dry-run
curl https://实际子域名/api/health
```

Certbot 会修改 Nginx 站点配置并加入 HTTP → HTTPS 跳转。以后修改模板时不要直接覆盖 Certbot 已写入的线上配置，应人工合并后先运行 `nginx -t`。

## 7. 上线验收

```bash
curl https://实际子域名/api/health
curl "https://实际子域名/api/synthesis?item=重息壤"
curl -X POST https://实际子域名/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"重息壤是什么","top_k":5,"gen_answer":true}'
# 流式问答（SSE）验证：-N 关闭客户端缓冲，应看到逐字/逐块输出
curl -N -X POST https://实际子域名/api/ask/stream \
  -H 'Content-Type: application/json' \
  -d '{"query":"重息壤是什么","top_k":5,"gen_answer":true}'
docker compose ps
docker compose logs --tail=200 app
```

浏览器再检查首页、名称联想、配方树、知识问答、图片和音频。微信小程序正式发布前，把 `miniprogram/app.js` 的 `apiBase` 改为该 HTTPS 子域名，并在微信公众平台配置 request 合法域名。`/api/health/deep` 和 `/api/metrics` 在 Nginx 中禁止公网访问，应用层也要求本机或令牌，管理员用 `docker compose exec` 在容器内查看。测试与门禁矩阵见 [TESTING.md](TESTING.md)。

**本机模拟不能当线上验收**：任何公网环境上线后，都必须用正式域名复核健康检查、配方树、整包问答和 SSE。

## 8. 日常更新

更新前先记下当前提交，便于回滚：

```bash
cd /opt/endfield
git rev-parse HEAD
git pull --ff-only origin master
docker compose build
docker compose up -d
docker compose ps
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/deep').read().decode())"
```

Compose 会先创建新容器再替换旧容器。应用数据和索引都构建在镜像中，不需要挂载本地 Chroma 目录。问答次数单独存放于 `api-security` 持久卷：**不要删除该卷，也不要执行 `docker compose down -v`**，否则计数会清零。

## 9. 回滚

把 `<previous_commit>` 替换为更新前记录的提交，重建启动后用与第 5 节相同的健康检查命令复查：

```bash
cd /opt/endfield
git switch --detach <previous_commit>
docker compose build
docker compose up -d
```

确认旧版本恢复后再决定何时回到主分支：`git switch master`。回滚不会删除 `.env`，也不需要删除 Docker 数据目录。

## 10. 排障

```bash
docker compose ps
docker compose logs --tail=300 app
curl -i http://127.0.0.1:8000/api/health
sudo nginx -t
sudo systemctl status nginx
sudo journalctl -u nginx --since "30 minutes ago"
```

判断顺序：① 本机 `127.0.0.1:8000` 不通 → 查容器和应用日志；② 本机通、域名不通 → 查 DNS、Nginx、防火墙；③ HTTP 通、HTTPS 不通 → 查证书和 Certbot；④ 只有 `/api/ask` 返回 429 → 看响应说明和 `Retry-After`，可能是频率、并发或当日次数超限，503 也可能是次数数据库不可写；⑤ 健康检查正常但问答失败 → 检查 `.env` 中的 LLM 配置和模型服务商状态。

| 现象 | 原因 | 对策 |
|---|---|---|
| 网页问答不再逐字显示 | Nginx 缓冲 SSE | 确认 `/api/ask/stream` 的 `proxy_buffering off` 已生效并 `reload` |
| 容器反复重启、健康检查失败 | 预热 + 索引加载超过 `start_period` | 放宽 `start_period`，或临时 `RAG_PREWARM=0` 让首问承担加载 |
| 次数额度在更新后被清零 | 计数卷被删除或换了 Compose 项目名 | 保留命名卷；不要执行 `docker compose down -v` |
| 所有访客共享同一 IP 限额 | 未配置可信代理，应用只看到代理地址 | 核实容器看到的 Nginx 对端地址后设置 `FORWARDED_ALLOW_IPS`，不要填 `*` |
| 合成查询或媒体接口被批量刷取 | 公开读取路由缺少单独入口限制 | 同步部署模板中的 `endfield_read_rate`、`endfield_media_rate` 和媒体连接限制 |
| 构建阶段模型下载失败 | 构建网络或磁盘/内存额度不足 | 检查构建环境配额；不要靠关闭运行阶段离线设置绕过 |
| 镜像过大、首次构建很慢 | 构建期下载 CPU torch 并重建 RAG 与图谱 | 接受该成本；多层缓存依赖清单前置于源码拷贝之前 |
| 重建索引时服务报错 | 运行中的服务占用 Chroma/SQLite 文件 | 先停服或在独立目录构建后再切换 |

## 11. 未完成边界

- 本机验证替代不了公网验收：域名、HTTPS、SSE 逐字输出、限流与代理 IP 都必须在正式域名上复核；
- 多主机副本不能共用独立计数库，横向扩容前需要重新设计额度存储。
