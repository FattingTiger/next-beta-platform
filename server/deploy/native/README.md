# Native staging 部署

这套资产只用于 CentOS 7 内测机。CentOS 7 已停止维护，不能作为生产环境。它不使用
Docker/Podman，不创建 bridge/NAT，不运行任何防火墙或路由修改命令，也不会停止、重启、
重载或改写 sing-box。固定监听为 PostgreSQL `127.0.0.1:55432`、Uvicorn
`127.0.0.1:18089`、Caddy `:80` 与 `:18443`；TCP 443 始终留给 sing-box。

## 安全边界

- PostgreSQL 17、Python 3.12、Java/Android 35 工具和 Caddy 2.11.4 必须已放在独立前缀，
  `install.sh` 只采用现有文件，不联网、不调用包管理器；复制 release 时会排除任意层级的
  `.env` 与 `.secrets`，避免把本地凭据带到测试机。
- 三个服务分别使用 `beta-pg`、`beta-app`、`beta-caddy`。应用以 `beta-files` 为主组创建
  `0750/0640` 私有文件；Caddy 仅以附加组只读。Caddy 只有
  `CAP_NET_BIND_SERVICE`，用于绑定 80 端口。
- 三个服务都进入 `beta-center.slice`，合计限制为 75% CPU、700 MiB 内存，并设置较高
  的 OOM 回收优先级，为既有 sing-box 和系统进程保留资源余量。
- native 启动包装器固定 SQLAlchemy 常驻池 16、临时 overflow 4，总数据库请求槽为 20；应用据此
  自动配置 40 个同步工作线程。PostgreSQL `max_connections=28`，健康检查复用应用池，仍为运维
  与 PostgreSQL 的默认保留连接留下余量。这是 1 vCPU、约 980 MiB 共享测试机的专用值，不修改
  应用通用 `Settings` 默认值。
- Let's Encrypt IP 证书使用 `shortlived` profile，只走 HTTP-01；
  `disable_tlsalpn_challenge` 保证 Caddy 不触碰 443。ACME 联系邮箱可留空。
- `forward_auth` 与业务 `reverse_proxy` 全部使用完全相同的 upstream
  `127.0.0.1:18089`。这是 Caddy 2.11.4 对 GHSA-6365 的必要约束；两个鉴权 transport 还关闭
  HTTP keepalive，业务代理以 4 秒复用连接，严格短于 Uvicorn 默认的 5 秒空闲连接超时，避免
  Caddy 复用已被上游关闭的 HTTP/1.1 连接并让非幂等请求返回 502。不得为 POST 开启网关重试。
  远端验收须并发混合已授权全链和未授权上传，确认 422/401/403 决策稳定且没有随机 404。
  官方 advisory 预告修复版为 2.11.5，但截至当前尚无正式 tag/release；发布后应优先升级并重跑验证。
- 私有文件、三类上传与通用 fallback 位于同一个顺序保留的 `route`，并以同一 `handle`
  group 互斥。`verify.sh --caddy ...` 会检查真实适配 JSON，确保 fallback 始终排在上传分支后，
  且每个上传严格先鉴权、再启用请求体、最后转发业务请求。
- 下载只在应用返回 `X-Accel-Redirect` 时进入 `handle_response`，剥离
  `/_protected-files` 后由 `file_server` 发送；客户端直接访问该前缀固定 404。

## 容量参数依据

40 VU 校准轮在旧的 8 槽连接池下完成 915 个请求且无失败，聚合 P95 为 1200ms，但 Bug 列表
P95 达到 1400ms，主要等待发生在数据库请求 limiter。同期 PostgreSQL 约 41 MiB / 192 MiB、
应用约 83 MiB / 448 MiB、Caddy 约 20 MiB / 160 MiB，说明可以在现有服务 cgroup 内审慎增加
连接并发。因此 native 配置采用 16+4 的应用池与 PostgreSQL 28 连接上限；池等待超时仍为通用
默认的 10 秒。

这些观测值只是调参依据，不是新配置的验收结果。变更后仍须完成 40/100 VU、耐久和 Range 轮次，
同时检查 cgroup、swap、数据库超时和 sing-box 实际 VPN 探针。父 slice 仍以 700 MiB、75% CPU
为硬边界；不得为了降低 API 延迟扩大该边界、修改 sing-box、占用 443，或在缺少新资源证据时
继续增加连接数。

## 部署顺序

先从 `env.example` 创建一个 root 所有、`0600` 的运行配置，替换公网 IPv4；不要在其中
写数据库密码、应用密钥或服务器登录凭据。若 sing-box 配置不在 `/etc/sing-box`，同时设置
完整的 `BETA_SING_BOX_CONFIG_PATHS`。预检快照目录必须尚不存在；脚本不会复用旧目录或
跟随同名链接。系统时间还必须已由 NTP 同步，否则预检会在申请证书前停止。

```bash
install -m 0600 deploy/native/env.example /var/tmp/beta-native.env
# 编辑 /var/tmp/beta-native.env，只填非敏感环境值

deploy/native/bin/preflight.sh /var/tmp/beta-native.env /var/tmp/beta-native-before

deploy/native/bin/install.sh \
  --runtime-env /var/tmp/beta-native.env \
  --source /path/to/server \
  --release-id release-YYYYMMDD-HHMMSS \
  --python-prefix /path/to/python-3.12 \
  --postgres-prefix /path/to/postgresql-17 \
  --caddy-binary /path/to/caddy-2.11.4 \
  --android-build-tools /path/to/android-sdk/build-tools/35.0.0 \
  --java-prefix /path/to/jdk \
  --app-venv /path/to/prepared-app-environment

deploy/native/bin/verify.sh --caddy /path/to/caddy-2.11.4 --require-systemd
deploy/native/bin/deploy.sh /etc/beta-center-native/runtime.env
```

也可用 `--wheelhouse DIR --requirements HASH_LOCK` 替代 `--app-venv`，但只接受离线且带哈希
的依赖锁。本流程当前只用于干净机器的首次内测部署：`install.sh` 对运行时链接、unit 和配置
的安装不在数据库事务内，后续代码升级必须先为这些项目资产创建版本化快照，不能直接把
首次安装脚本当作原子滚动升级工具。`deploy.sh` 在迁移前生成数据库 dump，失败时恢复旧
`current` 链接、数据库和原服务状态；它不操作 sing-box。事务目录位于
`/var/lib/beta-center-native/transactions/`，需要人工重放时执行：

```bash
deploy/native/bin/rollback.sh /var/lib/beta-center-native/transactions/TRANSACTION
```

部署前后会比较 sing-box 进程、配置、监听、443 所有者、路由、策略规则和规范化后的
iptables/ip6tables 指纹；监听队列计数和路由倒计时会被排除，因为它们只反映实时流量。
任一有效配置或所有权变化即撤回本项目服务；若差异仍存在，只报告并停机，不会
用修改 sing-box 或网络策略的方式“修复”。端口 80 必须能从公网到达，才能签发 IP
shortlived 证书；证书签发失败同样触发回滚。
