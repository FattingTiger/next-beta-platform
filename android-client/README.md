# 内测中心 Android 客户端

原生 Jetpack Compose 客户端，面向公司内部测试用户。默认连接公网测试环境：

```text
https://beta.example.com
```

可在构建时覆盖地址：

```bash
./gradlew -PbetaApiBaseUrl=https://example.internal :app:assembleDebug
```

地址必须使用 HTTPS。客户端不使用 Cookie，不关闭证书校验，也不把 access token、refresh token或下载票据写入日志。

## 主要流程

- 手机号和管理员配置的密码登录；首次登录强制改密。
- 按测试组查看应用列表、详情、截图和更新内容。
- WorkManager 获取短时下载票据并支持断点续传。
- 下载任务、缓存目录和清理操作按登录用户隔离；退出前先持久化会话退出屏障，进程中断也不会恢复旧登录态。
- APK 下载后校验文件大小、SHA-256、包名、版本与签名，再打开 Android 系统安装确认界面。
- 使用 WorkManager 每 7 天检查固定更新清单；严格从 `NEXT-Beta-android-x.y.z.apk` 文件名
  解析版本，发现更高版本且 Android 版本代码递增时提示用户下载。
- 从系统照片选择器选取 Bug 截图；上传前在应用私有目录重新编码为单帧 WebP，去掉元数据。
- 查看自己的 Bug、同组公开 Bug、处理状态、评论与验证结果；本人可在管理员开始处理前修改
  标题、描述和复现步骤，处理开始后改用追加回复。

## 设计边界

界面采用 Material 3 “Release Lens”：每页最多一张半透明 Lens Card，其余表单、正文和截图区域使用高不透明 tonal surface。Android 12 以上仅模糊独立的静态装饰背景层；文字、列表、输入框与截图不做实时模糊。Android 11 及以下自动显示同结构的实体表面。

## 构建与检查

需要 JDK 17、Android SDK 37 和 Build Tools 36.0.0：

```bash
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

如需使用另一套已安装的平台与 Build Tools，可以在构建时指定：

```bash
./gradlew -PbetaCompileSdk=37 -PbetaBuildTools=36.0.0 :app:assembleDebug
```

调试安装包生成在 `app/build/outputs/apk/debug/app-debug.apk`。当前验收基线包含 52 项 JVM
单元测试、Android Lint、真实服务器下载/安装跳转、Bug 闭环、暗色/大字号/横屏/进程恢复、
断网、退出竞态和 PATCH 取消绑定测试；完整结果见项目根目录的最终验收报告。

客户端更新目录固定为 `/downloads/android/`，`index.json` 是机器读取的版本清单，APK 使用
`NEXT-Beta-android-x.y.z.apk` 命名。客户端只在与 API 相同的 HTTPS 源站下载更新。

发布包尚未配置公司正式签名。联调阶段只产出 debug APK；正式发布前需由公司提供独立的客户端签名方案。
