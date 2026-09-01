# Native 第三轮服务器验收

这是一套面向 CentOS 7、1 vCPU、约 1 GiB RAM 共享主机的有界验收。业务流量从服务器外部
通过最终公网 HTTPS 地址发起；主机采集和恢复演练在服务器 root 终端执行。任何阶段触发 OOM、
持续 swap、sing-box 探针失败、路由或防火墙变化时，立即停止下一阶段，不通过继续加压来定位。

## 0. 前置条件

- 仅在管理员确认的内测维护窗口执行。
- 使用专用管理员、测试员和可归档的已发布 APK，不使用真实员工密码。
- 密码、Bearer、refresh token 只放环境变量，不放命令参数或验收报告。
- 公网 TLS 必须正常校验；`--insecure` 不能作为签署结果。
- Uvicorn `--limit-concurrency` 应为 128。32 在 100 VU 实测会大量返回 503，属于入口硬拒绝。
- 四个业务 `reverse_proxy` 的 idle keepalive 必须为 4 秒，严格短于 Uvicorn 默认的 5 秒；两个
  `forward_auth` 仍关闭 keepalive。不得以重试 POST 掩盖 stale upstream connection reset。
- native 包装器必须注入 SQLAlchemy pool 16、overflow 4；应用会据此生成 20 个数据库请求槽和
  40 个同步工作线程。PostgreSQL `max_connections` 必须为 28，池等待超时保持 10 秒。
- 混合负载默认等待 2–5 秒，用于 100 人内测用户总量模型；0.2–0.8 秒只能通过成对环境变量显式
  启用，用于 40 VU 突发容量模型。100 名用户不等于 100 个请求持续同时轰击。
- 负载机必须与服务器分开；极限带宽测试不能经过需要保护的 sing-box 隧道。
- 若没有一个通过既有 sing-box 客户端执行的真实 VPN 出口探针，只能签主机配置不变量，不能签
  “VPN 性能无退化”。

## 1. 静态、systemd 219 和主机基线

在服务器的 `server/` 目录执行：

```bash
deploy/native/bin/verify.sh \
  --caddy /opt/beta-center-native/caddy-2.11.4/bin/caddy \
  --require-systemd

systemctl --version | head -n 1
systemctl cat beta-center.slice \
  beta-center-postgres.service beta-center-app.service beta-center-caddy.service
systemctl show beta-center.slice \
  beta-center-postgres.service beta-center-app.service beta-center-caddy.service \
  --property=Id,LoadState,ActiveState,SubState,ControlGroup,Slice,MemoryLimit,CPUQuotaPerSecUSec,OOMScoreAdjust
```

第一行必须是 systemd 219；不得有未知 drop-in。先确认生效的容量参数：

```bash
grep -Fx 'export BETA_DATABASE_POOL_SIZE=16' \
  /opt/beta-center-native/bin/with-app-env.sh
grep -Fx 'export BETA_DATABASE_MAX_OVERFLOW=4' \
  /opt/beta-center-native/bin/with-app-env.sh
runuser -u beta-pg -- /opt/beta-center-native/postgresql-17/bin/psql \
  --host=/run/beta-center-pg --port=55432 --dbname=postgres \
  --no-psqlrc --tuples-only --no-align --command='SHOW max_connections'
```

前两条必须精确命中，最后一条必须只输出 `28`。健康检查使用应用的同一 SQLAlchemy engine/pool，
不为 readiness 另加连接配额；PostgreSQL 默认保留连接及常规运维必须仍有余量。

创建本轮证据目录并采集只读基线：

```bash
ROUND=/var/lib/beta-center-native/transactions/acceptance-r3-$(date -u +%Y%m%dT%H%M%SZ)
install -d -o root -g root -m 0700 "$ROUND"
date -u +%Y-%m-%dT%H:%M:%SZ >"$ROUND/started-at"

deploy/native/bin/preflight.sh \
  /etc/beta-center-native/runtime.env "$ROUND/host-before"

slice_cgroup=$(systemctl show beta-center.slice --property=ControlGroup | cut -d= -f2-)
memory_mount=$(awk '$3 == "cgroup" && $4 ~ /(^|,)memory(,|$)/ {print $2; exit}' /proc/mounts)
cpu_mount=$(awk '$3 == "cgroup" && $4 ~ /(^|,)cpu(,|$)/ {print $2; exit}' /proc/mounts)
cat "$cpu_mount$slice_cgroup/cpu.cfs_period_us" | tee "$ROUND/cpu-period-before"
cat "$cpu_mount$slice_cgroup/cpu.cfs_quota_us" | tee "$ROUND/cpu-quota-before"
tests/e2e/native_resource_snapshot.sh "$ROUND/resource-cgroups-before"
df -Pk /var/lib/beta-center-native | tee "$ROUND/disk-before"
systemctl show beta-center-postgres.service beta-center-app.service beta-center-caddy.service \
  --property=Id,ActiveState,SubState,MainPID,NRestarts >"$ROUND/services-before"
```

必须实读到父 slice 内存 `734003200` bytes。默认 100000µs CPU period 下 quota 应为 75000µs；
若 period 不同，以 quota/period=0.75 为准。

## 2. 公网串行业务与安全冒烟

先构建一个真实签名且包名唯一的 APK fixture，并准备有效 PNG/JPEG/WebP。负载机从 `server/`
执行：

```bash
export BETA_ACCEPTANCE_BASE_URL='https://PUBLIC_IP:18443'
export BETA_ACCEPTANCE_ADMIN_PHONE='DEDICATED_ADMIN_PHONE'
export BETA_ACCEPTANCE_ADMIN_PASSWORD='DEDICATED_ADMIN_PASSWORD'
export BETA_ACCEPTANCE_TESTER_PHONE='DEDICATED_TESTER_PHONE'
export BETA_ACCEPTANCE_TESTER_PASSWORD='DEDICATED_TESTER_PASSWORD'
export BETA_ACCEPTANCE_APK='/absolute/path/to/signed-fixture.apk'
export BETA_ACCEPTANCE_IMAGE='/absolute/path/to/fixture.png'
export BETA_ACCEPTANCE_APK_PACKAGE='com.example.betacenter.fixture.rUNIQUE'

.venv/bin/python tests/e2e/remote_acceptance.py
```

全部阶段必须 PASS。该脚本会验证并清理随机验收数据，包括权限范围、真实 APK 检查、私有媒体、
票据轮换后旧票失效、越权携带 Range 仍为 opaque 404、合法 206、越界 416、完整 SHA-256、
完成后票据失效、Bug 流转、安全头和审计记录。

另从外部检查 HTTP 跳转和公网证书：

```bash
curl --silent --show-error --dump-header /tmp/beta-http80.headers \
  --output /dev/null 'http://PUBLIC_IP/'
curl --fail --silent --show-error --dump-header /tmp/beta-health.headers \
  --output /tmp/beta-health.json 'https://PUBLIC_IP:18443/health/ready'
openssl s_client -connect PUBLIC_IP:18443 -servername PUBLIC_IP </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

80 应跳到 `https://PUBLIC_IP:18443`；证书 SAN 必须包含该 IP 且链受信。响应不得暴露 `Server`。
应用 API 的 2xx/4xx 必须有 `X-Request-ID`，错误 JSON 的 request_id 必须存在且不含敏感值。
Caddy 自产的早拒绝 401、私有前缀 404 和 body-limit 413 当前没有统一应用错误 request_id；若验收
要求所有网关错误也遵守同一 JSON/request-id 契约，这是一项明确的未通过项，不能由 E2E 冒烟
代替。

## 3. forward_auth 并发门禁

读取一个新鲜、已完成首次改密的测试员 Bearer 到环境变量后执行。脚本不会发送声明的 8 MiB
admin body；测试员 Bug 全链只发送无效的两字节 JSON，因此会经过 user forward_auth 和业务
reverse_proxy 后停在 422 校验，不创建 Bug、附件或上传记录：

```bash
export BETA_GATE_BASE_URL='https://PUBLIC_IP:18443'
read -r -s -p 'Tester bearer token: ' BETA_GATE_TESTER_TOKEN
export BETA_GATE_TESTER_TOKEN

.venv/bin/python tests/e2e/gateway_concurrency.py \
  --confirm-public-test --workers 20 --iterations 20 --max-p95-ms 1000
```

它混合 400 次匿名 admin 上传 header、400 次 tester→admin 拒绝、400 次
tester→user forward_auth→Bug 业务代理全链，以及 400 次合法 catalog。硬门槛依次为
401、403、422/`validation_error`、200；`100 Continue`、2xx 上传、随机 404、5xx、超时均为零，
每类 P95 ≤1000ms。服务器侧在脚本前后分别采集并比较：

```bash
find /var/lib/beta-center-native/upload-tmp -xdev -type f -printf '%P %s\n' \
  | sort >"$ROUND/upload-files-before"
find /var/lib/beta-center-native/storage -xdev -name '*.part' -type f -printf '%P %s\n' \
  | sort >"$ROUND/upload-parts-before"

# 外部并发脚本结束后：
find /var/lib/beta-center-native/upload-tmp -xdev -type f -printf '%P %s\n' \
  | sort >"$ROUND/upload-files-after"
find /var/lib/beta-center-native/storage -xdev -name '*.part' -type f -printf '%P %s\n' \
  | sort >"$ROUND/upload-parts-after"
cmp -s "$ROUND/upload-files-before" "$ROUND/upload-files-after"
cmp -s "$ROUND/upload-parts-before" "$ROUND/upload-parts-after"
```

门禁前后不得新增临时文件。Caddy 2.11.4 仍属于 GHSA-6365 官方影响版本；同 upstream、仅鉴权
transport 关闭 HTTP keepalive，以及本并发验收是内测期缓解，不等同于补丁。官方 advisory 将
2.11.5 标为修复版，但截至当前尚无正式 tag/release；发布后应升级、重新固定 SHA-256，并重跑
适配 JSON 和本节并发门禁。本轮继续使用 2.11.4 必须列为书面风险接受项。

## 4. 有界公网负载

具体环境变量和命令见 `tests/load/README.md`。执行顺序：

1. 默认 2–5 秒间隔的 100 人群、120 秒混合短测；
2. 显式 0.2–0.8 秒间隔的 40 VU、120 秒突发容量短测；
3. 默认 2–5 秒间隔的 30 VU、30 分钟混合耐久；
4. 20 VU、15 分钟流式 Range 重组。

连接池调优后的正式 100 人群测试使用默认 2–5 秒间隔、每秒生成 20 用户并运行 120 秒；失败为
零，聚合 P95 为 460ms，读取端点 P95 均不高于 710ms，最终 CSV 超过 3500 个请求和 150 个完整
下载闭环。实时摘要与 CSV 的收尾计数可有轻微差异，验收以归档 CSV 为准。该结果属于人群模型。

另一次 40 VU、0.2–0.8 秒突发观测约完成 959 个请求，失败为零，聚合 P95 约 1400ms，但 Bug
列表 P95 约 1800ms，未达到下方既定的 1200ms 严格门槛。这轮只能记录为容量上限观测，不能签为
通过；不得降低门槛来迎合该结果。

旧失败基线保留用于复盘。2026-08-29 最终复测的 CSV `Aggregated` 精确结果如下；四个目录都
包含 stats、history、failures、exceptions 和门禁输出，汇总见
`test-results/server/20260829/final-audit/round3/load/load-summary.json`：

| 场景 | 请求 | 失败 | P95 | 吞吐 | 证据目录 |
| --- | ---: | ---: | ---: | ---: | --- |
| 40 VU / 120 秒突发 | 6,099 | 0 | 550ms | 51.05 req/s | `round3/load/burst-40vu-120s/` |
| 100 用户 / 120 秒人群 | 3,522 | 0 | 460ms | 29.46 req/s | `round3/load/population-100users-120s/` |
| 30 VU / 30 分钟耐久 | 16,325 | 0 | 200ms | 9.07 req/s | `round3/load/endurance-30vu-30m/` |
| 20 VU / 60 秒 Range | 2,439 | 0 | 230ms | 41.19 req/s | `round3/load/range-20vu-60s/` |

前三轮按对应门禁通过。归档的 Range 证据是 20 VU、60 秒短时重组压力轮（history 59 秒），
不是本章建议的 15 分钟 Range 耐久；它只签短时门禁，不扩大解释为 15 分钟耐久证明。

30 分钟场景必须用专用测试账号而非单个短期 token，使每个 VU 建立并轮换独立 session：

```bash
export BETA_LOAD_PHONE='DEDICATED_TESTER_PHONE'
export BETA_LOAD_PASSWORD='DEDICATED_TESTER_PASSWORD'
unset BETA_LOAD_ACCESS_TOKEN
unset BETA_LOAD_WAIT_MIN_SECONDS BETA_LOAD_WAIT_MAX_SECONDS

locust -f tests/load/locustfile.py --headless --host "$BETA_LOAD_BASE_URL" \
  --users 30 --spawn-rate 1 --run-time 30m --stop-timeout 30 \
  --csv /tmp/beta-endurance
python tests/load/assert_results.py /tmp/beta-endurance_stats.csv \
  --profile mixed --min-requests 3000 --min-rps 5 --min-downloads 50 \
  --max-failure-ratio 0.001 --max-p95-ms 1200 \
  --max-read-p95-ms 800 --max-write-p95-ms 1200 \
  --max-download-p95-ms 10000
```

在服务器另一个终端同步采样，时间应覆盖最长阶段：

```bash
timeout 2000 vmstat 1 >"$ROUND/vmstat.log"
```

可在第三个终端运行：

```bash
timeout 2000 systemd-cgtop --batch --delay=1 >"$ROUND/cgtop.log"
```

负载硬门槛：

- 40 VU 突发轮必须显式设置两个 wait 环境变量为 0.2 和 0.8；失败和 5xx 为零，Bug 列表 P95
  应从旧 8 槽校准值 1400ms 降至 ≤1200ms，且不得出现 pool timeout、`too many clients` 或
  持续 swap；Caddy 日志不得出现 upstream `connection reset by peer`。
- 100 人群短测必须清除两个 wait 环境变量并使用默认 2–5 秒；Uvicorn concurrency-limit 503
  为零，总 5xx 为零，聚合 P95 ≤1500ms。
- 30 VU 耐久失败率和 5xx 均 <0.1%，普通读 P95 ≤800ms、写 P95 ≤1200ms，连接池超时为零。
- Range 至少 20 个完整闭环，成功率 ≥99%，成功文件 SHA-256 正确率 100%，所有 chunk 的
  206/Content-Range/Accept-Ranges 断言错误为零；同期普通 API P95 ≤1200ms。
- 正常流量 429 为零；任何 ACL 串号、摘要错误或业务断言错误均为零。

## 5. 登录速率限制

该项会给负载机 IP 留下 10 次、15 分钟窗口内的失败计数，必须在所有需要登录的步骤之后，从
失败桶干净的外部 IP 执行。先获取一个新 tester token，再用很小的并发运行：

```bash
.venv/bin/python tests/e2e/gateway_concurrency.py \
  --confirm-public-test --workers 1 --iterations 1 \
  --max-p95-ms 2000 --check-login-rate-limit
```

随机不存在手机号的前 10 次必须稳定返回 401/`invalid_credentials`，第 11 次必须返回
429/`login_rate_limited` 且 `Retry-After` ≥60。不得用真实账号做错误密码测试，否则会锁账号。

## 6. 数据库备份与隔离恢复演练

这一步有计划内公网中断。先停入口和应用，保持 PostgreSQL 在线，再把演练置于受限 slice：

```bash
systemctl stop beta-center-caddy.service
systemctl stop beta-center-app.service
systemctl is-active --quiet beta-center-postgres.service

systemd-run --scope --slice=beta-center.slice \
  --property=CPUQuota=50% --property=MemoryLimit=256M \
  tests/e2e/native_restore_drill.sh
```

脚本生成 mode 0700 的证据目录和 mode 0600 的 custom dump，只恢复到随机 scratch database，
逐表精确比较 quiescent 源库与恢复库计数并核对 Alembic revision，最后删除 scratch database。
它会先锁住 native 维护流程，核对 Unix socket 确实对应
`/var/lib/beta-center-native/postgres`、端口 55432、可写 PostgreSQL 实例和正确的生产库/角色，
并检查恢复所需空间与 2 GiB 余量；发现遗留 scratch database 时只报错，不猜测性删除。
它不读取或写入 storage，也不调用 sing-box、443、路由或防火墙命令。只有 scratch database
已经删除后才会写入 `complete`；任何失败或中断都会再尝试清理，清理失败则整体返回非零并打印
唯一允许人工删除的 scratch 名称。输出必须 PASS，`elapsed-seconds` 建议 ≤300，硬 RTO ≤2h。

无论演练成功还是失败，都立即执行第 7 节恢复 App 和 Caddy；失败时先记录完整输出和精确的
scratch 清理告警，不得运行针对 `beta_center` 的 `dropdb` 或 `pg_restore`。

这只证明数据库备份可恢复，不证明 APK/截图 storage 的灾备。完整灾备还必须冻结写入后归档
`/var/lib/beta-center-native/storage`，保留逐文件 SHA-256，并在隔离目录恢复为
`beta-app:beta-files`、目录 2750、文件 0640；现有 Docker Compose restore 工具不能直接用于 native。

## 7. 明确的服务重启演练

不要依赖 `Requires=` 自动传播。按入口到数据层停止，再逐层启动和验活：

```bash
systemctl stop beta-center-caddy.service
systemctl stop beta-center-app.service
systemctl stop beta-center-postgres.service

systemctl start beta-center-postgres.service
postgres_ready=false
for _ in {1..30}; do
  if runuser -u beta-pg -- /opt/beta-center-native/postgresql-17/bin/pg_isready \
    --host=/run/beta-center-pg --port=55432 --quiet; then
    postgres_ready=true
    break
  fi
  sleep 1
done
[[ "$postgres_ready" == true ]] || { echo 'PostgreSQL readiness timeout' >&2; exit 1; }

systemctl start beta-center-app.service
app_ready=false
for _ in {1..45}; do
  if curl --fail --silent --max-time 3 http://127.0.0.1:18089/health/ready >/dev/null; then
    app_ready=true
    break
  fi
  sleep 1
done
[[ "$app_ready" == true ]] || { echo 'application readiness timeout' >&2; exit 1; }

systemctl start beta-center-caddy.service
caddy_ready=false
for _ in {1..90}; do
  if curl --fail --silent --max-time 5 'https://PUBLIC_IP:18443/health/ready' >/dev/null; then
    caddy_ready=true
    break
  fi
  sleep 2
done
[[ "$caddy_ready" == true ]] || { echo 'public gateway readiness timeout' >&2; exit 1; }
```

最后三条 ready 必须再次显式执行并成功，随后重跑公网业务冒烟。PostgreSQL ≤30s、App ≤45s、
已有证书的 Caddy ≤30s 为目标；总恢复硬门槛 ≤5min，无自动重启循环、证书丢失或新 ACME 错误。

## 8. 资源、VPN 与最终主机不变量

负载和恢复后重新读取 cgroup 与日志：

```bash
tests/e2e/native_resource_snapshot.sh "$ROUND/resource-cgroups-after"
df -Pk /var/lib/beta-center-native | tee "$ROUND/disk-after"
systemctl show beta-center-postgres.service beta-center-app.service beta-center-caddy.service \
  --property=Id,ActiveState,SubState,MainPID,NRestarts >"$ROUND/services-after"
journalctl --since "$(cat "$ROUND/started-at")" \
  -u beta-center-postgres.service -u beta-center-app.service -u beta-center-caddy.service \
  >"$ROUND/project-journal.log"
journalctl -k --since "$(cat "$ROUND/started-at")" >"$ROUND/kernel-journal.log"

deploy/native/bin/preflight.sh \
  /etc/beta-center-native/runtime.env "$ROUND/host-after"
deploy/native/bin/host-state.sh compare "$ROUND/host-before" "$ROUND/host-after"
```

验收线：

- 父 slice 和三个服务各自的 `memory.failcnt` 增量都为零，日志无 OOM、pool timeout、
  `too many clients`、`Exceeded concurrency limit`、死锁或意外重启。
- slice 峰值达到 80%（560 MiB）告警，达到 90%（630 MiB）即中止；App 峰值建议 <400 MiB。
- ramp 完成后不得持续 swap-in/swap-out；磁盘剩余同时大于 20% 和 2 GiB。
- host-state compare 必须完全相同：sing-box ActiveState/MainPID、unit、配置、监听、TCP 443
  所有者、IPv4/6 rule/route、iptables/ip6tables 变化均为零。
- VPN 合成探针成功率 100%、无重连；相对基线丢包增量 ≤1 个百分点，P95 RTT 不超过
  `max(基线×1.2, 基线+20ms)`。探针必须实际经过 sing-box，不接受只连通 TCP 443 代替。

所有 CSV、失败清单、E2E 输出、证书信息、cgroup、journal、恢复证据、VPN 曲线和 host-state
目录一起归档。任何硬门槛失败都保留原始证据，不修改 sing-box、防火墙或路由来“修复”结果。
