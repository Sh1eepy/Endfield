# 自有服务器部署手册

如果使用朋友的服务器，并采用“你管理应用、朋友保留主机/Nginx 管理权”的权限分工，请优先阅读
[`FRIEND_SERVER_HANDOFF.md`](FRIEND_SERVER_HANDOFF.md)。

适用架构：子域名 → Nginx/HTTPS → `127.0.0.1:8000` → Docker Compose → FastAPI。
应用容器不会把 8000 端口暴露到公网；Nginx 限流之外，应用还限制问答频率、每日次数和并发数。
鉴权模式、额度持久化、可信代理 IP 与管理接口访问见 [`API_SECURITY.md`](API_SECURITY.md)。

## 1. 交付前需要的信息

- 一台能通过 SSH 管理的 Linux 服务器，建议 Ubuntu 22.04/24.04 x86_64；
- 建议至少 4 GB 内存和 15 GB 可用磁盘，首次保持 `WEB_CONCURRENCY=1`；
- 一个子域名，其 A 记录指向服务器公网 IPv4；只有服务器确实配置了 IPv6 时才添加 AAAA；
- 防火墙开放 SSH、80、443，不开放 8000；
- 服务器安装 Git、Nginx、Docker Engine 和 Docker Compose Plugin。

Docker 与 Compose 应使用 Docker 官方仓库版本：

- <https://docs.docker.com/engine/install/ubuntu/>
- <https://docs.docker.com/compose/install/linux/>

安装后确认：

```bash
docker version
docker compose version
sudo nginx -t
```

## 2. 拉取项目并配置密钥

以下以 `/opt/endfield` 为项目目录：

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
```

`.env` 只保存在服务器，不能提交到 Git。默认每 IP 每分钟 6 次、每日 60 次、全站每日 200 次（UTC 日窗口），可在 `.env` 调整。
公开网页无法安全保存固定令牌；`API_ACCESS_TOKEN` 留空保留有次数限制的匿名服务，设置后问答必须鉴权，当前网页/小程序不能直接使用该私有模式。
请求次数不是金额预算，仍需模型服务商的预算上限/告警。

## 3. 构建并启动容器

首次构建会下载 CPU PyTorch 和 embedding 模型，并在镜像中重建 RAG 与知识图谱，耗时和磁盘占用都比普通 Web 镜像大：

```bash
cd /opt/endfield
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 app
curl http://127.0.0.1:8000/api/health
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/deep').read().decode())"
```

`compose.yaml` 只绑定 `127.0.0.1:8000`。不要改成 `0.0.0.0:8000`，公网入口统一交给 Nginx。

## 4. 配置子域名与 Nginx

先在 DNS 控制台添加子域名 A 记录，等待它解析到服务器公网 IP。然后：

```bash
cd /opt/endfield
sudo cp deploy/nginx/endfield.conf /etc/nginx/sites-available/endfield
sudo nano /etc/nginx/sites-available/endfield
```

把其中的 `YOUR_SUBDOMAIN.example.com` 替换为实际子域名，再启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/endfield /etc/nginx/sites-enabled/endfield
sudo nginx -t
sudo systemctl reload nginx
curl http://实际子域名/api/health
```

如果符号链接已经存在，不要重复创建，直接检查文件内容并执行 `nginx -t`。
如果域名使用 Cloudflare 等代理，首发先使用“仅 DNS”模式；否则 Nginx 看到的可能是代理节点 IP，按 IP 限流会把不同用户误认为同一人。需要开启代理时，应先按服务商官方网段配置 Nginx `real_ip`，不要无条件信任任意来源的 `X-Forwarded-For`。

上线前按 `API_SECURITY.md` 核实并设置 `FORWARDED_ALLOW_IPS` 的精确代理对端地址。Compose 默认不信任转发头，未配置时同一代理后的访客会共享应用层 IP 限额；不要填 `*`。

Nginx 对 `/api/ask` 的默认保护是：

- 单 IP 平均每分钟 6 次；
- 允许短时间突发 2 次；
- 单 IP 同时最多 1 个问答；
- 超出返回 HTTP 429；
- 其他只读接口不使用这组严格限制。

## 5. 开启 HTTPS

Certbot 官方说明要求普通 HTTP 站点先能从公网通过 80 端口访问。推荐按 Certbot 官方 Nginx 流程安装：

- <https://certbot.eff.org/instructions?ws=nginx&os=ubuntufocal>

安装好 Certbot 后执行：

```bash
sudo certbot --nginx -d 实际子域名
sudo certbot renew --dry-run
curl https://实际子域名/api/health
```

Certbot 会修改 Nginx 站点配置并加入 HTTP → HTTPS 跳转。以后修改模板时，不要直接覆盖 Certbot 已写入的线上配置；应人工合并后先运行 `nginx -t`。

## 6. 上线验收

```bash
curl https://实际子域名/api/health
curl "https://实际子域名/api/synthesis?item=重息壤"
curl -X POST https://实际子域名/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"重息壤是什么","top_k":5,"gen_answer":true}'
docker compose ps
docker compose logs --tail=200 app
```

浏览器再检查首页、名称联想、配方树、知识问答、图片和音频。微信小程序正式发布前，把 `miniprogram/app.js` 的 `apiBase` 改为该 HTTPS 子域名，并在微信公众平台配置 request 合法域名。
`/api/health/deep` 和 `/api/metrics` 在 Nginx 中禁止公网访问，应用层也要求本机或令牌。Docker 管理员通过上面的 `docker compose exec` 命令在容器内查看。

## 7. 日常更新

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

Compose 会先创建新容器，再替换旧容器。应用数据和索引都构建在镜像中，因此不需要挂载本地 Chroma 目录。
问答次数单独存放于 `api-security` 持久卷；不要删除该卷或使用 `docker compose down -v`，否则计数会清零。

## 8. 回滚

把 `<previous_commit>` 替换为更新前记录的提交：

```bash
cd /opt/endfield
git switch --detach <previous_commit>
docker compose build
docker compose up -d
docker compose exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/deep').read().decode())"
```

确认旧版本恢复后再决定何时回到主分支：

```bash
git switch master
```

回滚不会删除 `.env`，也不需要删除 Docker 数据目录。

## 9. 排障命令

```bash
docker compose ps
docker compose logs --tail=300 app
curl -i http://127.0.0.1:8000/api/health
sudo nginx -t
sudo systemctl status nginx
sudo journalctl -u nginx --since "30 minutes ago"
```

判断顺序：

1. 本机 `127.0.0.1:8000` 不通：查容器和应用日志；
2. 本机通、域名不通：查 DNS、Nginx、防火墙；
3. HTTP 通、HTTPS 不通：查证书和 Certbot；
4. 只有 `/api/ask` 返回 429：查看响应说明和 `Retry-After`，可能是频率、并发或当日次数超限；503 也可能是次数数据库不可写；
5. 健康检查正常但问答失败：检查 `.env` 中的 LLM 配置和模型服务商状态。
