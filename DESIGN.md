---
name: 内测中心 · Release Lens
description: 以一个版本透镜卡连接发布、下载与 Bug 证据，其余界面使用清晰的 Material 3 tonal surface
colors:
  canvas: "#eef2f1"
  surface: "#fbfdfc"
  surface-container: "#e8edeb"
  glass: "rgba(252,255,253,0.72)"
  glass-strong: "rgba(252,255,253,0.88)"
  ink: "#111a17"
  ink-soft: "#4f5d57"
  primary: "#3357d5"
  published: "#00795a"
  progress: "#315fa8"
  pending: "#9a5a00"
  error: "#b3261e"
rounded:
  control: "12px"
  compact: "14–16px"
  content: "20px"
  lens: "28–30px"
---

# Design System: 内测中心 · Release Lens

## 设计方向

**Creative North Star：版本透镜（Release Lens）**

每个 APK 版本都是一个需要观察、验证和追踪的制品。每页只有一个高层“透镜卡”承载当前版本或绑定上下文；其余内容使用稳定、接近实体的 Material tonal surface。视觉重点来自卡片职责和深度差异，不来自模糊数量。

钴蓝表示主操作和当前选择，薄荷绿只表示已发布或验证通过，蓝色表示处理中，琥珀表示待处理，珊瑚红表示错误。这样避免主色与状态色混用。版本号、发布编号、包名、时间和设备数据使用等宽数字，便于比对。

## 卡片语法

### Lens Card

- 每页最多一个，圆角 28–30px。
- 承载当前发布、客户端当前版本或 Bug 绑定版本。
- Web 原型使用 72%–88% 半透明表面、1px 上沿高光和柔和环境影。
- Android 12 以上可在受控静态背景上增强模糊；低版本直接换为 `surfaceContainerHigh`，结构不变。

### Content Card

- 圆角 20px，92%–100% 实体 tonal surface。
- 承载更新说明、连续表单、截图证据和 Bug 状态。
- 依靠明度和细边线建立层级，不使用实时模糊或大阴影。

### Compact/Data Tile

- 圆角 14–16px，用于应用行、指标、设备信息和内部 inset。
- 高频数据区不为每个元素单独投影；只突出选中行。

### Controls

- 输入框和按钮圆角 12–15px；胶囊只用于状态、筛选和分段控制。
- 主按钮保持实体钴蓝，不做透明玻璃按钮。
- 所有移动端触控目标至少 48dp。

## 三页构图

### Web 应用管理

玻璃工作台内分为三个独立操作面：深色导航卡、应用台账卡、版本 Inspector 卡。当前内测态势是内容区唯一深色高层卡，上传 APK 是唯一突出主操作。表格继续保持固定列和扫描效率；普通行低层、选中行显示钴蓝边缝和轻 tonal elevation。

### Android 应用详情

首屏版本透镜卡包含测试组、发布编号、应用身份、当前版本、更新按钮和三个版本事实。截图使用无外框横向媒体 deck，更新说明使用实体 Content Card，Bug 状态使用深色状态卡。底部导航是高不透明玻璃表面，保留 Android 导航和系统返回习惯。

### Android Bug 反馈

绑定应用和版本是唯一上下文透镜。标题与描述合并为一张连续 Problem Card；截图与设备信息合并为 Evidence Card；提交操作位于高不透明 sticky action bar。提交失败时保留文字和截图，并在原位置显示恢复动作。

## Android 实现边界

- 使用 Jetpack Compose Material 3 的色彩角色、字体角色、预测返回、edge-to-edge 和 window insets。
- `Modifier.blur()` 会模糊组件自身内容，不等于 Web `backdrop-filter`，不能直接加在文字卡片根节点。
- Android 12 / API 31 以上只在应用详情 Hero 与底部导航两个有界、静态区域尝试 `RenderEffect` 或独立背景层模糊，建议半径 12–18dp。
- 滚动列表、表单、截图、输入框和长正文不做实时模糊；不做嵌套模糊或全屏离屏缓冲。
- Android 11 及以下、低性能设备、省电模式或减少透明度时使用 94%–100% 实体表面、1dp outline 和 tonal elevation。
- 动态颜色可以作为 Android 12 以上的可选个性化，但钴蓝主操作和 Bug 状态色保持固定语义。
- 深色主题使用独立语义色阶设计，不通过简单反相生成；在 Android 客户端阶段与浅色主题一起验收。

## 动效

- 按压反馈 100–140ms，缩放到 0.98–0.985，并保留 Material ripple。
- 页面进入采用 180–240ms fade-through，位移不超过 8dp。
- 下载、上传和状态切换在触发位置交叉淡化，按钮尺寸不跳变。
- 不动画模糊半径，不让背景光场持续漂浮，不对高频列表操作播放入场动画。
- 尊重系统“移除动画”和 Web `prefers-reduced-motion`。

## 可访问性与降级

- 正文、占位符和状态文案按最终合成背景检查 WCAG AA；文字保持不透明。
- 状态同时使用文字、形状或图标和颜色，不只依赖颜色。
- 卡片不写死内容高度，支持 Android 系统字体放大和 Web 浏览器缩放。
- 装饰高光和光场不进入无障碍语义树。
- 毛玻璃永远不是理解权限、状态或按钮可用性的必要条件。

## Do / Don't

**Do**

- 每页只设置一个主透镜，让其余表面安静地服务任务。
- 用钴蓝表达操作，用薄荷绿表达发布与验证。
- 对表单、正文和截图使用接近实体的 Material surface。
- 在真实中端 Android 设备上检查滚动帧率、功耗和字体放大。

**Don't**

- 不把每个白色容器都做成玻璃卡，不叠加实时模糊。
- 不照搬 iOS Liquid Glass 的控件、底栏或弹性动效。
- 不用随机彩色光斑、紫蓝营销渐变或大量发光阴影冒充材质。
- 不为了视觉效果改变 Android 的安装确认、权限提示和失败恢复流程。
