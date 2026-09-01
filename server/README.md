# 内测中心服务端

公网小规模 Android 内测分发平台的 API、管理后台和文件服务。

## 开发原则

- 权限在每次应用详情、Bug、附件和下载请求上重新校验。
- APK 必须通过签名与清单校验；生产环境缺少校验工具时拒绝上传。
- 文件使用随机内部路径保存，不暴露真实磁盘路径，不提供公开静态目录。
- 下载开始与客户端确认完成分开记录，不把下载完成解释为安装成功。
- 管理员变更写入审计记录；用户禁用后现有会话立即失效。

## 本地运行与迁移

安装锁定依赖并升级数据库：

```bash
uv sync --frozen
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn beta_center.main:app --host 127.0.0.1 --port 8088
```

迁移配置只从 `BETA_DATABASE_URL` 读取目标库。生产环境必须设置
`BETA_AUTO_CREATE_SCHEMA=false`，应用启动前由 Alembic 显式执行迁移，不能使用
SQLAlchemy `create_all` 代替版本化迁移。

常用迁移检查：

```bash
uv run alembic current
uv run alembic heads
uv run alembic check
uv run alembic upgrade head
```

基线迁移显式处理了 `apps.current_version_id` 与 `app_versions.app_id` 的循环外键：
先创建 `users`、`apps` 和 `app_versions`，再添加当前版本外键。每次新增迁移都应在空的
PostgreSQL 数据库执行一次 `upgrade head`，并对带数据副本完成一次升级演练。SQLite
往返验证只能作为快速检查，不能替代 PostgreSQL 发布门槛。

## 隔离部署结构

生产骨架由三个非 root 容器组成：PostgreSQL、FastAPI 应用和 Nginx 网关。数据库、
应用存储和大文件上传临时区使用独立卷，数据库和应用边缘网络都是 Compose 内部网络。
另有一个只包含 Nginx 的入口桥接网络，用于实现宿主机端口映射；只有网关发布端口，默认
绑定 `127.0.0.1:18088`，应用端口从不发布到宿主机。

该配置有以下硬约束：

- 不使用 `network_mode: host`、`privileged`、`CAP_NET_ADMIN`、`CAP_SYS_ADMIN` 或
  `/dev/net/tun`。
- 不挂载 sing-box 的配置、状态目录或设备。
- 不执行 `iptables`、`nftables`、路由、策略路由或防火墙修改命令。
- 不占用 80、443 或任何低位端口；首次联调只使用回环高位端口。
- 所有服务启用只读根文件系统、`no-new-privileges`、capability 全量移除、进程数限制和
  有界日志轮转。
- Nginx 的 real-IP 模块只信任入口 bridge gateway 的精确单 IP（以及必要 loopback），递归
  解析外层 TLS 代理追加的 `X-Forwarded-For`，再用解析后的客户端 IP 覆盖传给应用的 XFF；
  不信任 `10/8`、`172.16/12`、`192.168/16` 等宽泛私网。应用只信任边缘网络中的网关。
- Python、uv、PostgreSQL 与 Nginx 基础镜像使用可读版本标签和多架构 manifest digest
  双重锁定；升级安全补丁时必须显式更新 digest 并重跑三轮服务端验证。

Docker 在发布端口时会维护它自己的桥接/NAT 规则。`deploy/up.sh` 不解析 nftables/iptables
语义，不能证明既有 sing-box 防火墙链未受影响；它的自动快照只覆盖 sing-box 运行状态、
配置、监听、`ip rule` 和默认路由。`preflight_readonly.sh` 仅额外记录防火墙只读指纹，供人工
或宿主机专用审计工具比较，不能区分 Docker 的预期规则和 sing-box 规则。

因此在运行 sing-box 的目标机上，首选已经验证且不创建 Docker bridge/NAT 的 native 或
rootless 部署方案。只有在同版本、同网络策略环境的演练证实 Docker 与 sing-box 兼容，并有
宿主机专用的防火墙差分或业务功能探针时，才使用本 Compose 骨架。任何异常都应撤掉本项目
并改部署方式；不得以修改 sing-box、iptables/nftables 或策略路由来迁就本项目。

## Native staging（CentOS 7，仅测试）

`deploy/native/` 提供不创建容器网络、不修改防火墙/路由且不触碰 sing-box 的原生测试部署。
它将 PostgreSQL 17 和 Uvicorn 只绑定到回环地址，由独立用户运行的 Caddy 2.11.4 占用 80
与 18443；443 始终留给 sing-box。Let's Encrypt IP 证书使用 `shortlived` profile 和
HTTP-01，显式禁用 TLS-ALPN。CentOS 7 已停止维护，这套方案只用于本次内测验收，不能用于
生产。安装、指纹比较、故障回滚、systemd 219 约束与静态验证步骤见
[`deploy/native/README.md`](deploy/native/README.md)。运行配置只使用占位值，密码和应用密钥
由目标机本地生成到 `/etc/beta-center-native/secrets/`，不得提交到仓库。

边缘网络使用一个显式 `/29`，其中 Docker bridge、应用和网关使用三个不同地址。入口网络
也使用不重叠的显式 `/29`，且只有网关加入。应用的
`BETA_TRUSTED_PROXY_NETWORKS` 只包含网关的单一 `/32`，而 Uvicorn 自身关闭 proxy-header
信任，因此只有 Nginx 覆盖后的 `X-Forwarded-For` 会被采用。`deploy/up.sh` 会在创建网络前
检查两个候选网段和所有路由表；任一候选与物理网卡、已有 Docker 网络、VPN 或 sing-box
路由有任何重叠都会阻断部署。默认网段只是示例，必须依据目标机只读盘点确认或修改。

生产环境强制启用 `X-Accel-Redirect`。网关的 `/_protected-files/` 带 Nginx `internal`
限制，客户端无法直接访问；API 只有在完成登录、测试组权限与下载票据复核后才返回内部
跳转。Nginx 访问日志只记录 method、无 query 的 `$uri` 和协议，不记录含下载 ticket 的
原始 `$request`，Uvicorn 访问日志也关闭以避免在第二份日志中泄露 query。上传入口先通过
无 body 的 Nginx `auth_request` 子请求验证管理员或内测用户身份，未认证请求不会进入
multipart 解析或临时卷。图标/截图、APK 和 Bug 反馈分别限制为 12、520 和 60 MiB，并有
按真实客户端 IP 的上传请求与并发连接上限；通用路由只允许 2 MiB。应用和网关共享
同一个非 root UID/GID，因此网关能读取应用以 `0700/0600` 创建的私有文件；网关对存储卷
仍只有只读权限，无需放宽为 world-readable。APK 上限为 512 MiB，网关请求体上限为
520 MiB，并关闭上传请求预缓冲；应用使用独立磁盘临时卷承接 multipart spool，避免
512 MiB 文件填满内存 tmpfs。三个服务还分别设置了可配置且非空的 CPU、内存和进程上限。

## 首次部署准备

先在目标机项目目录执行只读盘点，并把输出保存到项目目录之外：

```bash
BETA_HTTP_PORT=18088 ./deploy/preflight_readonly.sh \
  > /var/tmp/beta-center-preflight.txt
```

检查输出中的 sing-box ActiveState、MainPID、配置指纹、监听端口和路由。不要在盘点阶段
安装软件、启动容器或修改系统配置。

创建不会进入 Git 的运行配置和密钥：

```bash
cp deploy/env.example .env.production
mkdir -p .secrets
umask 077
openssl rand -base64 48 > .secrets/db_password
openssl rand -base64 48 > .secrets/app_secret
chmod 600 .secrets/db_password .secrets/app_secret
```

修改 `.env.production` 中的公开地址与允许的 Host。不要把数据库密码、应用密钥、服务器
root 密码或 sing-box 信息写进该文件。隔离检查和首次启动：

```bash
docker compose --env-file .env.production config --format json \
  | python3 deploy/verify_compose_isolation.py
./deploy/up.sh
curl --fail http://127.0.0.1:18088/health/live
curl --fail http://127.0.0.1:18088/health/ready
```

`deploy/up.sh` 会在启动前拒绝非回环发布、低位端口、host network、特权容器、TUN 和危险
capability，也会拒绝边缘网段与现有路由重叠，并在启动后比较 sing-box 的运行状态与配置
指纹、sing-box 监听行、策略路由规则和默认路由。任一快照失败或发生变化时，脚本会立即
执行 `docker compose down` 撤掉本次栈并返回失败；数据卷不会被删除。它不会直接创建防火墙
规则或修改 sing-box，但 Docker daemon 仍会维护项目 bridge/NAT；脚本不对这部分做“未变化”
承诺。没有完成宿主机专用防火墙审计时，不应在该机器执行 `deploy/up.sh`。
公网入口应由已经过审计的宿主机 TLS 入口反代到 `127.0.0.1:18088`；如果 443 已由
sing-box 使用，不得抢占或重配该端口。

首次管理员通过容器内交互命令创建，初始密码不会出现在命令参数或日志中：

```bash
docker compose --env-file .env.production exec app \
  python -m beta_center.cli create-admin --phone +8613800000000 --name 管理员
```

## 备份、恢复与文件对账

备份脚本会短暂停止网关和应用，先确认数据库引用的文件全部存在且没有未隔离的孤立文件，
再生成 PostgreSQL custom dump 与存储归档。由于写入端已停止，数据库和文件快照共享
一致性边界；数据库
容器没有发布宿主机端口，停机窗口内不存在另一条应用写入路径。

```bash
./scripts/backup.sh
```

默认备份保存在被 Git 忽略的 `data/backups/`。每个备份目录包含：

- `database.dump`：无 owner、无 ACL 的 PostgreSQL custom dump；
- `storage.tar.gz`：拒绝软链接并排除未完成 `.part` 文件的私有存储归档；
- `reconcile.json`：备份前文件引用检查；
- `metadata.txt`：时间、PostgreSQL 版本与 Alembic revision；
- `SHA256SUMS`：上述文件的完整性清单。

备份与恢复共用项目内固定的 `data/.maintenance.lock`，即使调用者选择不同备份目录也不能
并发执行。异常退出遗留锁时必须先确认没有维护进程，再由管理员人工清理。备份完成后若
应用或网关恢复失败，脚本会明确返回失败并保留已经生成的备份，不会吞掉重启错误。

只读文件对账可以随时执行：

```bash
docker compose --env-file .env.production run --rm --no-deps \
  -e BETA_RUN_MIGRATIONS=false app \
  python /opt/beta-center/scripts/reconcile_storage.py --json
```

缺失引用会返回失败。孤立文件默认只报告；需要处理时可加 `--quarantine-orphans`，脚本只会
将其原子移动到隔离目录，不会删除。

恢复必须显式确认：

```bash
./scripts/restore.sh --confirm data/backups/backup-YYYYMMDDTHHMMSSZ
```

恢复前会强制创建一份新的安全备份，随后校验 SHA256、停止写入端、重建数据库 schema、
恢复文件并再次对账。任何破坏性步骤后的失败都会让应用与网关保持停止，并输出安全备份
位置，防止错误数据重新对外提供。恢复演练应定期在独立环境执行，不能等到事故时第一次
运行。

## 上线前仍需验证的环境门槛

- 在与服务器同版本的 PostgreSQL 17 空库真实执行 `alembic upgrade head` 和
  `alembic check`。
- 实际构建镜像并确认 `/usr/bin/apksigner`、`/usr/bin/aapt` 与 readiness 检查通过。
- 验证外部请求无法直达应用端口或 `/_protected-files/`，授权下载由 X-Accel 正常发送，且
  下载 ticket 不出现在 Nginx 日志中。
- 用测试 APK 完成上传、签名连续性校验、授权下载与下载完成回执。
- 完成一次备份、破坏性恢复和数据库/文件一致性复核。
- 用宿主机专用审计或功能探针确认 Docker 新增的仅为本项目预期 bridge/NAT，既有 sing-box
  防火墙链和实际代理路径没有变化；通用 `deploy/up.sh` 不完成此项证明。缺少该证明时改用
  不创建 Docker 网络栈的 native/rootless 方案。
