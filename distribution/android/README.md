# Android 客户端下载页

本目录保存 NEXT Beta 客户端公开下载页的源码，不包含 APK。

部署时将以下文件放到同一个 HTTPS 目录：

- `index.html`
- `next-logo.png`
- `index.json`：由发布流程根据实际 APK 生成
- `NEXT-Beta-android-x.y.z.apk`
- `NEXT-Beta-android-latest.apk`：指向或复制自最新正式 APK

文件名中的语义化版本号和 `index.json` 中的 `versionCode` 必须同时递增。客户端只接受与 API 相同源站上的 HTTPS 更新地址。

`index.example.json` 仅用于说明格式，发布前应计算真实文件大小和 SHA-256。正式 APK 必须使用公司 release 证书签名。
