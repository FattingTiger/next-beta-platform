# NEXT 内测平台 — Design System

## 1. Product intent

NEXT 内测平台是 NEXT 系统平台中的 Android 应用内测与反馈工具。管理员通过 Web 管理后台发布 APK、分配测试组并处理 Bug；员工通过 Android 客户端查看获准测试的应用、下载安装并提交带截图的 Bug。

产品给人的感受应当是：可信、清楚、安静、精确、有适度质感。它是小规模企业工具，不需要电商促销感、游戏感或夸张增长数据。

## 2. Brand

- 正式名称：`NEXT 内测平台`
- 英文短名：`NEXT Beta`
- 英文辅助语：`BETA PLATFORM`
- 核心图形：由两张向前连接的应用卡片构成的立体字母 N，右下角有小型青绿色验证标记。
- Web 与 Android 使用同一个核心图形，不再分别创造不同图标。
- 品牌方案参考图：`brand/NEXT-brand-direction-board.png`
- Android 图标参考图：`brand/NEXT-android-icon-concept.png`

## 3. Visual principles

1. **内容先于装饰**：状态、版本、测试范围与下一步操作必须一眼可见。
2. **卡片承载任务**：卡片表达可操作对象或一组相关信息，不把每段文字都包成卡片。
3. **克制的拟物质感**：品牌图标可以有珐琅、金属和微光；业务界面只使用柔和高光、细边框和短阴影，避免厚重 3D 控件。
4. **玻璃只用于层级**：浮层、顶部工具条和关键摘要可使用半透明材质；长表格、表单和正文使用实色表面确保可读性。
5. **真实信息密度**：Web 是桌面管理工具，允许紧凑表格；Android 使用可触控的舒适间距。
6. **不照搬 iOS**：可以借鉴 App Store 的内容编排与 Apple Developer 的卡片层次，但交互遵循 Web 与 Android 平台习惯。

## 4. Color tokens

### Brand

- `brand.primary`: `#3357D5` — 主按钮、当前导航、关键链接
- `brand.primary.hover`: `#2848BA`
- `brand.primary.soft`: `#E2E8FF`
- `brand.ink`: `#16231F` — 深色品牌面、标题、Hero
- `brand.teal`: `#20C7B5` — 已验证、小范围高亮，不作为大面积主色

### Surfaces

- `surface.canvas`: `#EEF2F1`
- `surface.base`: `#FBFDFC`
- `surface.raised`: `#FFFFFF`
- `surface.muted`: `#E7ECE9`
- `surface.glass`: `rgba(252,255,253,0.82)`

### Text and outline

- `text.primary`: `#111A17`
- `text.secondary`: `#4F5D57`
- `text.tertiary`: `#65726C`
- `outline.default`: `#C6D0CB`
- `outline.strong`: `#A8B5AF`

### Semantic

- `success`: `#006E51`, soft `#D7F4E8`
- `warning`: `#8A4F00`, soft `#FFECD0`
- `danger`: `#A7221B`, soft `#FFE2DF`
- `info`: `#235794`, soft `#DEEBFF`

所有文本与背景组合必须达到 WCAG AA；不能只靠颜色区分状态。

## 5. Typography

- 中文优先：`Noto Sans SC` 或 `Source Han Sans SC`（开源字体）
- 英文与数字：`Inter`，不可用时跟随 Noto Sans SC
- Web 页面标题：40–48 px / 700–800
- Web 分区标题：22–28 px / 650–750
- Web 正文：14–16 px / 400–500
- Android 大标题：28–32 sp / 700
- Android 标题：20–24 sp / 650–700
- Android 正文：14–16 sp / 400–500
- 表格数字使用等宽数字特性；版本号、包名可使用等宽字体，但不要整页使用等宽字体。

## 6. Shape, spacing and elevation

- 基础间距：4 px；常用间距为 8 / 12 / 16 / 24 / 32 / 48
- Web 控件圆角：12 px；普通卡片：20 px；重点卡片：28 px
- Android 控件圆角：12–16 dp；卡片：20–24 dp；大图容器：28 dp
- 普通卡片：1 px 中性边框 + 轻微短阴影
- 浮层：明显但柔和的阴影，保持边缘清晰
- 避免所有组件都使用相同圆角、相同阴影和相同高度

## 7. Iconography and imagery

- 功能图标采用简洁圆角线性图标，默认 20–24 px/dp。
- 状态图标必须和文字标签同时出现。
- 应用 Logo、应用截图和 Bug 截图是主要内容图片；不要加入无关图库照片和抽象 3D 插画。
- NEXT 品牌拟物图标只出现在登录页、侧边栏品牌区、Android 启动图标和 About 区域，不在每张卡片反复出现。

## 8. Web shell

- 目标宽度：1440 px 桌面优先，同时适配 1280 px 与 1024 px。
- 左侧固定导航：发布概览、应用与版本、测试组、Bug 反馈、用户管理、下载记录、审计日志。
- 主内容区最大宽度约 1500 px，使用 24–40 px 页面边距。
- 页面标题区包含标题、简短说明和最多两个主操作。
- 筛选条应保持单行或有序换行，不让搜索框与状态筛选争夺焦点。
- 数据列表提供普通模式和“批量管理”模式；进入批量模式后才显示首列复选框和批量操作条。

## 9. Android shell

- 基于 Material Design 3 和 Jetpack Compose 可实现的组件。
- 目标画板：412 × 915 dp；同时适配 360 × 800 dp。
- 底部导航：应用、反馈、我的；详情和提交页不显示底部导航或保持弱化。
- 使用系统返回手势、系统分享/文件选择器、Android 安装流程，不模拟 iOS 控件。
- 主要触控区域至少 48 × 48 dp，正文不小于 14 sp。
- 下载按钮需要表达等待、下载中、校验中、可安装、失败五种状态。

## 10. Core components

- App card：应用 Logo、名称、版本、更新日期、测试状态、主操作
- Version row：版本号、versionCode、发布时间、更新说明、下载记录
- Status chip：草稿、已发布、已归档；待处理、处理中、待验证、已关闭
- Metric card：数值、单位、明确名称和解释提示
- Screenshot gallery：应用展示图与 Bug 证据图分开
- Filter bar：搜索、状态、测试组、清除
- Batch action bar：已选数量、全选本页、归档/删除、恢复、永久删除、退出管理
- Destructive confirmation：对象数量、影响说明、管理员密码、不可恢复警告
- Empty state：说明为什么为空，并给出唯一推荐操作
- Error state：人类可读说明、重试入口、不会丢失表单草稿

## 11. Content rules

- 用具体事实代替抽象健康判断，例如“1 个应用正在内测”。
- 下载统计写成“下载请求”和“下载完成”，明确“下载完成不代表安装成功”。
- 管理删除操作区分“归档/停用”和“永久删除”。
- 永久删除必须写明依赖关系和不可恢复性，并要求当前管理员密码确认。
- “审计日志”说明为“记录管理员的关键操作，用于追踪谁在何时修改了什么”。
- 避免“发布面”“闭环态势”“赋能”等抽象内部术语。

## 12. Motion

- 状态切换与浮层：160–220 ms ease-out
- 页面或大容器切换：220–320 ms
- 只动画 opacity、transform 和必要的尺寸变化
- 支持减少动态效果；不使用循环动画、漂浮装饰或大面积视差

## 13. Required states

每个关键页面都应给出：正常、加载、空数据、请求失败、无权限、离线/网络中断、操作成功。列表还应包含选中、批量处理中、部分失败；表单包含未保存、校验失败、上传中和上传失败。

## 14. Avoid

- 不使用紫色渐变 SaaS 模板、霓虹光晕、随机大数字和无意义趋势图。
- 不使用过多胶囊按钮、无边界浮动卡片或低对比玻璃正文。
- 不把危险操作只藏在没有文字的图标里。
- 不生成静默安装、强制升级、远程卸载、审批流、外部合作方或消息提醒界面，这些不在当前范围内。
