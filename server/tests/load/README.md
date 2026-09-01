# 服务端负载验收

所有场景都必须从服务器外部通过最终 HTTPS 地址运行。令牌和密码只放环境变量，不写入命令行、
CSV 前缀或报告。先跑串行远端验收，确认测试用户能看到目标应用和已发布版本。

## Native 容量基线

1 vCPU、约 980 MiB 的共享 native 测试机使用专用运行参数：SQLAlchemy pool 16、overflow 4，
数据库请求 limiter 总量 20，AnyIO 同步工作线程由应用自动设为 40；PostgreSQL
`max_connections=28`。健康检查与业务请求共享同一池，不另占常驻连接。池等待超时保持 10 秒。
这些值由 native 启动包装器注入，不改变开发、测试或其他部署方式的通用 `Settings` 默认值。

旧 8 槽配置的 40 VU 校准轮为 915 请求、0 失败、聚合 P95 1200ms，Bug 列表 P95 1400ms；
PostgreSQL、应用与 Caddy 的 cgroup 用量分别约为 41/192、83/448、20/160 MiB。该结果只能说明
扩容有内存依据，不能作为 20 槽配置通过验收的证据。正式轮次仍须同时归档新 CSV、cgroup、
swap、数据库日志与实际 VPN 探针；不得通过扩大 700 MiB 父 slice 或占用 sing-box 资源来达标。

## 100 人群混合短测

100 名内测用户是用户总量模型，不表示 100 个请求持续无间隔并发。每个 Locust 用户在一次操作
完成后默认等待 2–5 秒，再发起下一次操作；该场景按 18:1 的比例混合应用/反馈读取与完整下载
闭环。运行前清除突发模型变量并设置业务参数：

```bash
unset BETA_LOAD_WAIT_MIN_SECONDS BETA_LOAD_WAIT_MAX_SECONDS
export BETA_LOAD_BASE_URL='https://PUBLIC_IP:18443'
export BETA_LOAD_ACCESS_TOKEN='SHORT_LIVED_TESTER_TOKEN'
export BETA_LOAD_APP_ID='VISIBLE_APP_ID'
export BETA_LOAD_VERSION_ID='PUBLISHED_VERSION_ID'
export BETA_LOAD_MAX_FILE_BYTES=$((128 * 1024 * 1024))
```

然后执行：

```bash
locust -f tests/load/locustfile.py --headless --host "$BETA_LOAD_BASE_URL" \
  --users 100 --spawn-rate 20 --run-time 120s --csv /tmp/beta-load
python tests/load/assert_results.py /tmp/beta-load_stats.csv \
  --profile mixed --min-requests 1200 --min-rps 10 --min-downloads 20 \
  --max-failure-ratio 0.001 --max-p95-ms 1500 \
  --max-read-p95-ms 1200 --max-write-p95-ms 2000 \
  --max-download-p95-ms 10000
```

连接池调优后的最终 100 人群测试使用默认 2–5 秒间隔、每秒生成 20 用户并运行 120 秒。归档 CSV
的 `Aggregated` 行为 **3,522 个请求、0 失败、P95 460ms、29.46 req/s**，门禁通过。实时摘要与
最终 CSV 会因收尾采样边界略有差异，签署时以归档 CSV 为准。原始 stats、history、failures、
exceptions 和门禁输出位于
`test-results/server/20260829/final-audit/round3/load/population-100users-120s/`。该结果证明当轮人群
模型的 API 门禁通过，不替代 cgroup、swap 和实际 VPN 探针证据。

目标服务的 Uvicorn 并发上限必须大于 100。若日志出现 `Exceeded concurrency limit`，该轮是
入口硬拒绝，不能解释为服务器容量结论。第三轮候选值为 128；调高后仍需证明没有连接池超时、
OOM、swap 持续增长或 sing-box 退化。

## 40 VU 突发容量短测

只有需要测容量上限时才显式缩短思考时间。以下环境值把每个虚拟用户的操作间隔改为 0.2–0.8 秒；
不得把该节奏解释成 100 名真实员工的日常行为：

```bash
export BETA_LOAD_WAIT_MIN_SECONDS=0.2
export BETA_LOAD_WAIT_MAX_SECONDS=0.8

locust -f tests/load/locustfile.py --headless --host "$BETA_LOAD_BASE_URL" \
  --users 40 --spawn-rate 10 --run-time 120s --csv /tmp/beta-burst
python tests/load/assert_results.py /tmp/beta-burst_stats.csv \
  --profile mixed --min-requests 1200 --min-rps 10 --min-downloads 20 \
  --max-failure-ratio 0.001 --max-p95-ms 1500 \
  --max-read-p95-ms 1200 --max-write-p95-ms 2000 \
  --max-download-p95-ms 10000

unset BETA_LOAD_WAIT_MIN_SECONDS BETA_LOAD_WAIT_MAX_SECONDS
```

连接池调优后的 40 VU、0.2–0.8 秒突发观测约完成 959 个请求，失败为零，聚合 P95 约 1400ms，
但 Bug 列表 P95 约 1800ms，高于既定的 1200ms 严格门槛。这轮只能作为容量上限观测，不能签为
通过；门槛保持不变，后续应保留原始证据并继续定位 Bug 列表延迟。

上述旧失败基线保留用于说明优化前状态。最终复测仍使用 40 VU、0.2–0.8 秒等待和 120 秒时长；
归档 CSV 的 `Aggregated` 行为 **6,099 个请求、0 失败、P95 550ms、51.05 req/s**，对应门禁通过。
原始证据位于 `test-results/server/20260829/final-audit/round3/load/burst-40vu-120s/`。

## 30 VU 30 分钟混合耐久

最终耐久轮使用 30 VU、默认 2–5 秒等待并持续 30 分钟。归档 CSV 的 `Aggregated` 行为
**16,325 个请求、0 失败、P95 200ms、9.07 req/s**，对应门禁通过。原始 stats、history、
failures、exceptions 和门禁输出位于
`test-results/server/20260829/final-audit/round3/load/endurance-30vu-30m/`。

## 20 路流式 Range 耐久

`range_locustfile.py` 用多个 Range 请求按顺序重组 APK，逐块流式计算 SHA-256，不把整个文件
留在负载机内存中。建议使用最大预期 APK；默认拒绝超过 128 MiB 的文件。

短于 access token 有效期的冒烟或短测优先使用 Range 专用变量；脚本仍兼容
`BETA_LOAD_ACCESS_TOKEN`，但 `BETA_RANGE_ACCESS_TOKEN` 同时存在时优先使用后者。不要把 token
写进命令参数、CSV 前缀或报告：

```bash
unset BETA_LOAD_PHONE BETA_LOAD_PASSWORD
export BETA_RANGE_ACCESS_TOKEN='SHORT_LIVED_TESTER_TOKEN'
export BETA_LOAD_VERSION_ID='PUBLISHED_VERSION_ID'
export BETA_RANGE_CHUNK_BYTES=$((1024 * 1024))
export BETA_RANGE_MAX_FILE_BYTES=$((128 * 1024 * 1024))
```

超过 12 分钟的轮次应清除短期 token，并提供专用测试账号，让每个虚拟用户建立并轮换自己的
会话：

```bash
export BETA_LOAD_BASE_URL='https://PUBLIC_IP:18443'
unset BETA_RANGE_ACCESS_TOKEN BETA_LOAD_ACCESS_TOKEN
export BETA_LOAD_PHONE='DEDICATED_TESTER_PHONE'
export BETA_LOAD_PASSWORD='DEDICATED_TESTER_PASSWORD'
export BETA_LOAD_VERSION_ID='PUBLISHED_VERSION_ID'
export BETA_RANGE_CHUNK_BYTES=$((1024 * 1024))
export BETA_RANGE_MAX_FILE_BYTES=$((128 * 1024 * 1024))

locust -f tests/load/range_locustfile.py --headless --host "$BETA_LOAD_BASE_URL" \
  --users 20 --spawn-rate 2 --run-time 15m --stop-timeout 30 \
  --csv /tmp/beta-range
python tests/load/assert_results.py /tmp/beta-range_stats.csv \
  --profile range --min-requests 100 --min-rps 1 --min-downloads 20 \
  --max-failure-ratio 0.01 --max-p95-ms 3000 \
  --max-read-p95-ms 1200 --max-write-p95-ms 3000 \
  --max-download-p95-ms 10000
```

`BETA_LOAD_VERSION_ID` 必须是非空的已发布版本 ID。分片大小必须是整数，默认 1 MiB，允许范围为
64 KiB–8 MiB；文件上限默认 128 MiB，必须不小于分片且不超过 512 MiB。配置错误会在登录或发起
下载前直接终止，错误信息只包含变量名和边界，不包含 token 或密码。

Range 场景的硬门槛是：至少 20 个完整闭环、成功率不低于 99%、成功文件摘要正确率 100%、
所有分块均为 206 且 `Content-Range`/`Accept-Ranges` 正确。负载期间另起普通 API 探针，P95
不超过 1200ms。

本次归档的最终 Range 复测是 **20 VU、60 秒**短时重组压力轮，history 覆盖 59 秒；CSV
`Aggregated` 行为 **2,439 个请求、0 失败、P95 230ms、41.19 req/s**，对应短时门禁通过。原始
证据位于 `test-results/server/20260829/final-audit/round3/load/range-20vu-60s/`。该结果不能写成
15 分钟 Range 耐久测试，也不替代上方建议的 15 分钟发布前耐久场景。

## 结果解释

`assert_results.py` 同时检查聚合和每个端点，不允许用高频列表请求掩盖低频下载失败。验收还必须
归档 Locust stats/failures、服务日志、cgroup 指标、VPN 探针和部署前后主机指纹；单独一份 CSV
不能证明共享服务器未影响 sing-box。若两个等待时间环境变量只设置一个、不是有限数字，或不满足
`0.1 <= minimum <= maximum <= 60` 秒，负载脚本会在启动时直接拒绝运行。
