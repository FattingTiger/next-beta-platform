# QA 试验场

一个用于验证内部应用分发、下载与安装链路的独立 Android 测试应用。

- 包名：`com.company.qa.playground`
- 版本：`1.0.0`（versionCode 1）
- 系统要求：Android 8.0 及以上
- 技术实现：Android Framework View + built-in Kotlin
- 运行时依赖：无 Compose、无 AndroidX、无第三方库

## 本地验证

```bash
./gradlew testDebugUnitTest lintDebug assembleDebug
```

生成的调试包位于 `app/build/outputs/apk/debug/app-debug.apk`。

`distribution/qa-playground-1.0.0-debug.apk` 是实际上传到公网测试平台并完成客户端下载安装验收的固定制品，其 SHA-256 为：

```text
ca451771cd6735bf12fd724efb1b81036607bd6ff03d422318abd56772dedb46
```

由于 APK/ZIP 构建元数据可能变化，重新构建的调试包字节摘要不保证与该固定制品一致；包名、版本和功能保持一致。
