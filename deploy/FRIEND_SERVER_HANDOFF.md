# 朋友服务器协作上线手册

本文采用以下权限分工：

- **你负责应用**：GitHub、SSH 登录、项目目录、`.env`、Docker Compose、应用日志和后续更新；
- **朋友负责主机管理**：创建部署用户、添加 SSH 公钥、DNS、Docker 权限、Nginx、HTTPS 和防火墙；
- **朋友不需要把 root 密码交给你**；
- **你不修改朋友服务器上的其他站点**。

主流程按 Ubuntu 22.04/24.04 编写。如果 `cat /etc/os-release` 显示的不是 Ubuntu，软件安装部分先停止，按实际系统调整。

## 0. 先统一占位符

执行命令前，把下面四项写在自己的记录里：

```text
<SERVER_IP>     服务器公网 IPv4，例如 203.0.113.10
<SSH_PORT>      SSH 端口，默认 22
<DEPLOY_USER>   独立部署用户，建议 endfielddeploy
<SUBDOMAIN>     实际子域名，例如 endfield.example.com
```

尖括号只是说明，实际命令里必须替换，不能原样复制。

## 1. 你：确认最新代码已经在 GitHub

所需软件：本机 Git、PowerShell。

```powershell
cd "C:\Users\28277\Desktop\ANY\Vibe Coding"
git status -sb
```

含义：确认当前分支和未提交改动。如果看到修改文件，执行：

```powershell
git add -A
git commit -m "feat: add self-hosted production deployment"
git push origin master
```

- `git add -A`：把当前项目的新增、修改和删除放入本次提交；
- `git commit`：在本地创建一个可回滚版本；
- `git push`：把版本上传到 GitHub，服务器才能拉取。

再次执行：

```powershell
git status -sb
```

预期只显示：

```text
## master...origin/master
```

并确认 GitHub 中存在：

```text
compose.yaml
deploy/nginx/endfield.conf
deploy/README.md
```

## 2. 你：生成本次部署专用 SSH 密钥

所需软件：Windows 自带 OpenSSH Client。先检查：

```powershell
ssh -V
```

生成独立密钥：

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\endfield_deploy" -C "endfield-deploy"
```

- `ed25519`：密钥算法；
- `-f`：使用独立文件，避免覆盖你已有的默认 SSH 密钥；
- `-C`：给公钥加一个便于识别的备注。

查看公钥：

```powershell
Get-Content "$env:USERPROFILE\.ssh\endfield_deploy.pub"
```

把输出的一整行发给朋友。只发送 `endfield_deploy.pub` 的内容，绝不能发送没有 `.pub` 后缀的私钥。

## 3. 朋友：确认服务器与现有服务

朋友登录服务器后执行：

```bash
cat /etc/os-release
uname -m
free -h
df -h
docker version
docker compose version
nginx -v
git --version
```

命令含义：

- `cat /etc/os-release`：系统类型和版本；
- `uname -m`：CPU 架构，常见为 `x86_64`；
- `free -h`：内存；
- `df -h`：磁盘余量；
- 后四项确认 Docker、Compose、Nginx、Git 是否已安装。

建议至少 4 GB 内存和 15 GB 可用磁盘。首次构建需要下载 CPU PyTorch 和 embedding 模型，并重建 RAG。

如果 Docker 已存在，不要为了“按文档重装”而卸载朋友当前的 Docker。缺少软件时由朋友处理：

```bash
sudo apt-get update
sudo apt-get install -y git nginx snapd ca-certificates curl
```

Docker Engine 与 Compose Plugin 使用 Docker 官方 Ubuntu 安装方法：

- <https://docs.docker.com/engine/install/ubuntu/>
- <https://docs.docker.com/compose/install/linux/>

如果 `docker version` 或 `docker compose version` 不可用，朋友按下面的官方 APT 仓库流程安装；两条命令都可用时整段跳过：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo sh -c '. /etc/os-release && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list'

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

命令含义：

- `/etc/apt/keyrings/docker.asc`：保存 Docker 官方仓库的签名密钥；
- `docker.list`：让 Ubuntu 从 Docker 官方仓库而不是旧版系统包获取 Docker；
- `docker-ce`：Docker Engine；
- `docker-buildx-plugin`：负责构建镜像；
- `docker-compose-plugin`：提供 `docker compose` 命令；
- `enable --now`：立即启动 Docker，并设置为开机自启；
- `hello-world`：只用于确认 Docker 能实际启动容器，运行完自动删除测试容器。

安装完成后应再次确认：

```bash
docker version
docker compose version
```

## 4. 朋友：创建独立部署用户

以下示例用户名为 `endfielddeploy`；朋友可以换名，但后续命令必须一致。

```bash
sudo adduser --disabled-password --gecos "" endfielddeploy
sudo install -d -m 700 -o endfielddeploy -g endfielddeploy /home/endfielddeploy/.ssh
sudo nano /home/endfielddeploy/.ssh/authorized_keys
```

朋友把你发来的 `ssh-ed25519 ... endfield-deploy` 公钥粘贴为一整行，保存后执行：

```bash
sudo chown endfielddeploy:endfielddeploy /home/endfielddeploy/.ssh/authorized_keys
sudo chmod 600 /home/endfielddeploy/.ssh/authorized_keys
sudo usermod -aG docker endfielddeploy
sudo install -d -m 755 -o endfielddeploy -g endfielddeploy /opt/endfield
```

命令含义：

- `.ssh` 目录权限为 700、`authorized_keys` 为 600，否则 SSH 可能拒绝使用；
- 加入 `docker` 组后，你可以管理 Docker，不必获得朋友的 root 密码；
- `/opt/endfield` 只交给部署用户维护，不碰朋友的其他项目。

注意：Docker 用户组本身拥有非常高的主机权限。朋友必须明确同意；如果不愿授予，就由朋友代为执行本文中的 `docker compose` 命令。

加入 Docker 组后必须退出并重新登录，新的组权限才会生效。

## 5. 朋友：解析子域名并检查端口

朋友在 DNS 控制台添加：

```text
记录类型：A
主机记录：子域名前缀，例如 endfield
记录值：<SERVER_IP>
```

- 服务器没有配置 IPv6 时不要添加 AAAA；
- 使用 Cloudflare 时，首发先选择“仅 DNS”，不要先开启代理；
- 云服务器安全组和主机防火墙允许 `<SSH_PORT>`、80、443；
- 不允许公网访问 8000。

朋友把以下信息发给你：

```text
服务器 IP
SSH 端口
部署用户名
完整子域名
服务器系统版本
Docker/Compose 是否可用
Nginx 是否已有其他站点
```

## 6. 你：首次 SSH 登录

```powershell
ssh -p <SSH_PORT> -i "$env:USERPROFILE\.ssh\endfield_deploy" <DEPLOY_USER>@<SERVER_IP>
```

- `-p`：SSH 端口；
- `-i`：指定你的部署私钥；
- 第一次连接出现主机指纹时，先让朋友核对指纹，再输入 `yes`。

登录后执行：

```bash
whoami
id
docker version
docker compose version
```

预期：

- `whoami` 是部署用户名；
- `id` 输出包含 `docker` 组；
- Docker 命令不需要 `sudo`。

如果出现 Docker socket `permission denied`，退出 SSH 重新登录；仍失败则请朋友检查 Docker 组，不要改 socket 为 777。

## 7. 你：拉取项目

```bash
git clone https://github.com/Sh1eepy/Endfield.git /opt/endfield
cd /opt/endfield
git status -sb
```

- `git clone`：从 GitHub 下载项目；
- `git status -sb`：确认服务器位于 `master`，且工作区干净。

如果提示 `/opt/endfield` 非空，先运行：

```bash
ls -la /opt/endfield
```

把输出发给朋友或我确认，不要直接删除目录。

## 8. 你：创建服务器 `.env`

```bash
cd /opt/endfield
cp .env.example .env
chmod 600 .env
nano .env
```

填写：

```dotenv
LLM_API_KEY=实际密钥
LLM_BASE_URL=实际 OpenAI 兼容地址
LLM_MODEL=实际模型名称
LLM_TIMEOUT=60
WEB_CONCURRENCY=1
ASK_MAX_CONCURRENCY=2
```

- `.env` 只存在服务器，不进入 Git；
- `WEB_CONCURRENCY=1`：只加载一份 embedding 模型和索引；
- `ASK_MAX_CONCURRENCY=2`：同一进程最多同时执行两个知识问答；
- 不要在聊天、截图或日志中展示 `.env` 内容。

确认权限而不显示密钥：

```bash
ls -l .env
git status --short --ignored
```

`.env` 应显示为仅所有者读写，并被 Git 忽略。

## 9. 你：构建并启动应用

```bash
cd /opt/endfield
docker compose build
docker compose up -d
docker compose ps
```

- `build`：构建镜像、下载模型、重建 RAG 和图谱；首次可能需要较长时间；
- `up -d`：后台启动，SSH 断开后容器继续运行；
- `ps`：查看容器状态和健康状态。

查看日志：

```bash
docker compose logs --tail=200 app
```

服务器本机验收：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/deep
curl "http://127.0.0.1:8000/api/synthesis?item=重息壤"
```

预期：健康接口返回 `status: ok`，合成接口返回 `ok: true`。如果失败，先停止在这里排查，不配置公网代理。

## 10. 朋友：接入 Nginx

这一步需要主机管理权限，建议由朋友执行，避免你碰其他站点。

```bash
sudo cp /opt/endfield/deploy/nginx/endfield.conf /etc/nginx/sites-available/endfield
sudo nano /etc/nginx/sites-available/endfield
```

朋友把文件中的：

```text
YOUR_SUBDOMAIN.example.com
```

替换成 `<SUBDOMAIN>`，然后执行：

```bash
sudo ln -s /etc/nginx/sites-available/endfield /etc/nginx/sites-enabled/endfield
sudo nginx -t
sudo systemctl reload nginx
```

- `ln -s`：启用这个独立站点；如果链接已存在，不重复创建；
- `nginx -t`：先验证所有 Nginx 配置，必须成功才能 reload；
- `reload`：平滑载入新站点，不中断朋友的其他网站。

此时你从本机检查：

```powershell
Invoke-RestMethod "http://<SUBDOMAIN>/api/health"
```

HTTP 不通时不要申请证书，先检查 DNS、80 端口和 Nginx。

## 11. 朋友：申请 HTTPS

Certbot 官方 Nginx 流程要求域名已经能从公网通过 HTTP 访问：

- <https://certbot.eff.org/instructions?ws=nginx&os=ubuntufocal>

如果服务器还没有 Certbot，朋友执行：

```bash
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/local/bin/certbot
```

如果 `certbot` 已存在或链接已存在，就跳过对应安装命令。申请证书：

```bash
sudo certbot --nginx -d <SUBDOMAIN>
sudo certbot renew --dry-run
```

- 第一条申请证书，并让 Certbot 自动修改该 Nginx 站点；
- 第二条模拟续期，确认以后能自动更新证书。

## 12. 你：公网验收

```powershell
Invoke-RestMethod "https://<SUBDOMAIN>/api/health"
Invoke-RestMethod "https://<SUBDOMAIN>/api/names"
```

知识问答：

```powershell
$body = @{
  query = "重息壤是什么"
  top_k = 5
  gen_answer = $true
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "https://<SUBDOMAIN>/api/ask" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

浏览器打开：

```text
https://<SUBDOMAIN>
```

依次检查：

1. 首页资源正常；
2. 名称联想；
3. “重息壤”配方树；
4. 普通知识问答；
5. 图片和音频；
6. 手机浏览器布局。

Nginx 已限制 `/api/ask` 的单 IP频率与并发；公网不能访问 `/api/health/deep` 和 `/api/metrics`，管理员通过 SSH 后请求 `127.0.0.1:8000` 查看。

## 13. 你：微信小程序切换正式域名

修改本地 `miniprogram/app.js`：

```javascript
apiBase: 'https://<SUBDOMAIN>'
```

不要带末尾 `/`。然后：

1. 在微信公众平台把该域名加入 request 合法域名；
2. 重新上传小程序版本；
3. 真机测试健康检查、联想、配方、问答和媒体。

## 14. 你：日常更新

更新前记录当前版本：

```bash
cd /opt/endfield
git rev-parse HEAD
```

保存输出，然后：

```bash
git pull --ff-only origin master
docker compose build
docker compose up -d
docker compose ps
curl http://127.0.0.1:8000/api/health/deep
```

- `--ff-only`：远端历史不一致时停止，避免服务器自动生成合并提交；
- 重新 `up -d`：使用新镜像替换旧容器；
- `.env` 不会被 Git 覆盖。

## 15. 你：回滚

如果新版本失败，把 `<PREVIOUS_COMMIT>` 换成更新前记录的提交：

```bash
cd /opt/endfield
git switch --detach <PREVIOUS_COMMIT>
docker compose build
docker compose up -d
curl http://127.0.0.1:8000/api/health/deep
```

恢复成功后保留现场。需要重新跟随主分支时：

```bash
git switch master
```

不要通过删除 `/var/lib/docker`、项目目录或 `.env` 来回滚。

## 16. 快速排障顺序

### SSH 不通

检查服务器 IP、SSH 端口、安全组、公钥和用户名。

### Docker permission denied

退出 SSH 重新登录；朋友检查 `id <DEPLOY_USER>` 是否包含 docker 组。不要把 Docker socket 改成 777。

### 容器启动失败

```bash
cd /opt/endfield
docker compose ps
docker compose logs --tail=300 app
```

### 本机 8000 不通

说明问题在 Docker/FastAPI，暂时不要检查 Nginx。

### 本机 8000 通，域名不通

检查 DNS、Nginx、80/443、安全组和防火墙。

### 只有问答失败

检查服务器 `.env`、模型服务商状态和：

```bash
curl http://127.0.0.1:8000/api/health/deep
docker compose logs --tail=300 app
```

### 返回 HTTP 429

触发了 Nginx 单 IP 限流或应用问答并发保护，等待后重试；不要通过公开 8000 端口绕过。
