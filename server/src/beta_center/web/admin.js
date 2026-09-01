const API_ROOT = "/api/v1";

const ICON_PATHS = Object.freeze({
  dashboard: ["M4 13.5V20h6v-6.5H4Zm10-9.5v16h6V4h-6ZM4 4v5.5h6V4H4Z"],
  apps: ["M4 4h6v6H4V4Zm10 0h6v6h-6V4ZM4 14h6v6H4v-6Zm10 0h6v6h-6v-6Z"],
  groups: ["M16 20v-1.5c0-2-1.8-3.5-4-3.5H6c-2.2 0-4 1.5-4 3.5V20", "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M17 11a3 3 0 0 0 0-6", "M22 20v-1.5c0-1.7-1.2-3-3-3.4"],
  bugs: ["M9 9h6v6H9V9Z", "M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1"],
  users: ["M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z", "M3 21c.7-3.4 4.2-5.5 9-5.5s8.3 2.1 9 5.5"],
  downloads: ["M12 3v12m0 0 4-4m-4 4-4-4", "M4 20h16"],
  audit: ["M8 4H5a2 2 0 0 0-2 2v14h14v-3", "M8 2h8v4H8V2Z", "m14 9-6.5 6.5L14 17l1.5-3.5L22 7l-2-2Z"],
  logout: ["M14 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2v-3", "M10 12h11m-3-3 3 3-3 3"],
  arrowRight: ["M5 12h14m-5-5 5 5-5 5"],
  close: ["M6 6l12 12M18 6 6 18"],
  plus: ["M12 5v14M5 12h14"],
  refresh: ["M20 7v5h-5", "M19 12a7 7 0 1 1-2-5"],
  search: ["m20 20-4.4-4.4", "M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15Z"],
  edit: ["M13.5 6.5 17.5 10.5", "M4 20h4l11.5-11.5a2.8 2.8 0 0 0-4-4L4 16v4Z"],
  eye: ["M2 12s3.7-6 10-6 10 6 10 6-3.7 6-10 6S2 12 2 12Z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"],
  upload: ["M12 16V4m0 0L7 9m5-5 5 5", "M4 20h16"],
  publish: ["M5 4h14v16H5V4Z", "m8 8 2.2 2.2L16 7.5", "M8 15h8"],
  disable: ["M6 6l12 12", "M12 3a9 9 0 1 1-6.4 2.7"],
  trash: ["M4 7h16", "M9 7V4h6v3", "m7 7 1 14h10l1-14", "M10 11v6m4-6v6"],
  comment: ["M4 4h16v12H8l-4 4V4Z"],
  lock: ["M6 10h12v11H6V10Z", "M8 10V7a4 4 0 0 1 8 0v3", "M12 14v3"],
  check: ["m5 12 4 4L19 6"],
  alert: ["M12 3 2.5 20h19L12 3Z", "M12 9v5m0 4h.01"],
  info: ["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z", "M12 10v7m0-11h.01"],
  file: ["M6 2h8l4 4v16H6V2Z", "M14 2v5h4", "M9 13h6m-6 4h6"],
  image: ["M3 4h18v16H3V4Z", "M7 9h.01", "m3 17 4-4 3 3 3-4 5 5"],
  chevronLeft: ["m15 18-6-6 6-6"],
  chevronRight: ["m9 18 6-6-6-6"],
});

const ROUTES = Object.freeze({
  dashboard: { title: "发布概览", description: "查看内测参与、版本发布与反馈处理状态" },
  apps: { title: "应用与版本", description: "维护应用资料、展示素材，以及 APK 的校验与独立发布" },
  groups: { title: "测试组", description: "用测试组精确控制应用的可见范围" },
  bugs: { title: "Bug 反馈", description: "跟进问题、内部协作，并形成验证关闭记录" },
  users: { title: "用户管理", description: "创建绑定手机号的账户，分配权限与测试组" },
  downloads: { title: "下载记录", description: "核对版本下载开始、完成与失败证据" },
  audit: { title: "审计日志", description: "记录谁在何时做了什么，帮助追踪误操作与安全事件" },
});

const LABELS = Object.freeze({
  appStatus: { draft: "草稿", published: "已发布", archived: "已归档" },
  versionStatus: { draft: "待发布", published: "已发布", disabled: "已停用" },
  bugStatus: { pending: "待处理", in_progress: "处理中", verifying: "待验证", closed: "已关闭" },
  visibility: { group: "测试组可见", private: "仅提交人与管理员" },
  resolution: { fixed: "已修复", duplicate: "重复问题", not_a_bug: "非 Bug", cannot_reproduce: "无法复现", wont_fix: "暂不修复" },
  downloadStatus: { started: "已开始", completed: "已完成", failed: "失败", cancelled: "已取消" },
  role: { admin: "管理员", tester: "测试用户" },
  outcome: { success: "成功", failure: "失败", locked: "已锁定" },
});

const FIELD_LABELS = Object.freeze({
  phone: "手机号",
  password: "密码",
  current_password: "当前密码",
  new_password: "新密码",
  initial_password: "初始密码",
  name: "名称",
  package_name: "Android 包名",
  short_description: "一句话简介",
  description: "完整说明",
  group_ids: "测试组",
  member_ids: "测试成员",
  app_ids: "应用范围",
  release_notes: "版本更新说明",
  status: "状态",
  resolution: "处理结论",
  fix_version_id: "修复版本",
  note: "处理说明",
  content: "评论内容",
});

const els = {
  loginView: document.querySelector("#login-view"),
  loginForm: document.querySelector("#login-form"),
  loginError: document.querySelector("#login-error"),
  consoleView: document.querySelector("#console-view"),
  primaryNav: document.querySelector("#primary-nav"),
  pageTitle: document.querySelector("#page-title"),
  pageDescription: document.querySelector("#page-description"),
  pageActions: document.querySelector("#page-actions"),
  viewRoot: document.querySelector("#view-root"),
  accountName: document.querySelector("#account-name"),
  accountPhone: document.querySelector("#account-phone"),
  accountAvatar: document.querySelector("#account-avatar"),
  logoutButton: document.querySelector("#logout-button"),
  sidebarNewApp: document.querySelector("#sidebar-new-app"),
  bugNavCount: document.querySelector("#bug-nav-count"),
  loadingBar: document.querySelector("#loading-bar"),
  toastRegion: document.querySelector("#toast-region"),
  entityDialog: document.querySelector("#entity-dialog"),
  entityForm: document.querySelector("#entity-form"),
  dialogTitle: document.querySelector("#dialog-title"),
  dialogBody: document.querySelector("#dialog-body"),
  dialogError: document.querySelector("#dialog-error"),
  dialogSubmit: document.querySelector("#dialog-submit"),
  detailDialog: document.querySelector("#detail-dialog"),
  detailTitle: document.querySelector("#detail-title"),
  detailBody: document.querySelector("#detail-body"),
  passwordDialog: document.querySelector("#password-dialog"),
  passwordForm: document.querySelector("#password-form"),
  passwordError: document.querySelector("#password-error"),
  reauthDialog: document.querySelector("#reauth-dialog"),
  reauthForm: document.querySelector("#reauth-form"),
  reauthError: document.querySelector("#reauth-error"),
};

const state = {
  user: null,
  route: "dashboard",
  renderId: 0,
  loadingCount: 0,
  entitySubmit: null,
  refreshPromise: null,
  reauthRequest: null,
  filters: {
    apps: { search: "", status: "", group_id: "", page: 1 },
    groups: { search: "", active: "", page: 1 },
    bugs: { status: "", app_id: "", deleted: "false", page: 1 },
    users: { search: "", active: "", role: "", group_id: "", page: 1 },
    downloads: { status: "", user_id: "", app_id: "", version_id: "", created_from: "", created_to: "", page: 1 },
    audit: { action: "", actor_id: "", reason_code: "", request_id: "", page: 1 },
  },
  cache: { apps: null, groups: null, users: null },
  bulk: {
    apps: { enabled: false, selected: new Set() },
    groups: { enabled: false, selected: new Set() },
    users: { enabled: false, selected: new Set() },
    bugs: { enabled: false, selected: new Set() },
  },
};

const BULK_CONFIG = Object.freeze({
  apps: {
    entityLabel: "应用",
    inactiveStateLabel: "已归档",
    deactivateLabel: "归档",
    restoreLabel: "恢复为草稿",
    isInactive: (item) => item.status === "archived",
    isSelectable: () => true,
    displayName: (item) => item.name,
    cacheKeys: ["apps", "groups"],
    permanentResource: "apps",
    permanentImpact: "这些应用的 APK、图标、截图、下载记录及关联 Bug 都会被彻底清除。",
    updateLifecycle: (item, inactive) => api(`/admin/apps/${encodeURIComponent(item.id)}`, { method: "PATCH", json: { status: inactive ? "archived" : "draft" } }),
  },
  groups: {
    entityLabel: "测试组",
    inactiveStateLabel: "已删除",
    deactivateLabel: "删除",
    restoreLabel: "恢复",
    isInactive: (item) => !item.is_active,
    isSelectable: () => true,
    displayName: (item) => item.name,
    cacheKeys: ["groups", "users", "apps"],
    permanentResource: "groups",
    permanentImpact: "这些测试组与用户、应用之间的关联都会被彻底清除。",
    updateLifecycle: (item, inactive) => api(`/admin/groups/${encodeURIComponent(item.id)}`, { method: "PATCH", json: { is_active: !inactive } }),
  },
  users: {
    entityLabel: "用户",
    inactiveStateLabel: "已删除",
    deactivateLabel: "删除",
    restoreLabel: "恢复",
    isInactive: (item) => !item.is_active,
    isSelectable: (item) => item.id !== state.user?.id,
    displayName: (item) => item.display_name,
    cacheKeys: ["users", "groups"],
    permanentResource: "users",
    permanentImpact: "这些账号、会话、下载与反馈数据都会被清除；关联已上传 APK 的账号会被系统跳过。",
    updateLifecycle: (item, inactive) => api(`/admin/users/${encodeURIComponent(item.id)}`, { method: "PATCH", json: { is_active: !inactive } }),
  },
  bugs: {
    entityLabel: "Bug",
    inactiveStateLabel: "已删除",
    deactivateLabel: "删除",
    restoreLabel: "恢复",
    isInactive: (item) => Boolean(item.deleted_at),
    isSelectable: () => true,
    displayName: (item) => item.reference,
    cacheKeys: [],
    permanentResource: "bugs",
    permanentImpact: "这些 Bug 的描述、截图附件、评论与全部处理轨迹都会被彻底清除。",
    updateLifecycle: (item, inactive) => api(`/admin/bugs/${encodeURIComponent(item.id)}/deletion`, { method: "PATCH", json: { deleted: inactive } }),
  },
});

class ApiError extends Error {
  constructor(message, status = 0, code = "request_failed", payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.payload = payload;
  }
}

function makeIcon(name, size = 20) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("icon");
  for (const d of ICON_PATHS[name] || ICON_PATHS.info) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}

function hydrateStaticIcons() {
  document.querySelectorAll("[data-icon]").forEach((node) => {
    const rawName = node.dataset.icon || "info";
    const name = rawName.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    node.replaceChildren(makeIcon(name));
  });
}

function h(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "className") {
      node.className = value;
    } else if (key === "text") {
      node.textContent = String(value);
    } else if (key === "dataset") {
      for (const [dataKey, dataValue] of Object.entries(value)) node.dataset[dataKey] = String(dataValue);
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "ariaLabel") {
      node.setAttribute("aria-label", value);
    } else if (key === "htmlFor") {
      node.htmlFor = value;
    } else if (key in node && !key.includes("-")) {
      node[key] = value;
    } else {
      node.setAttribute(key, String(value));
    }
  }
  const append = (child) => {
    if (child === undefined || child === null || child === false) return;
    if (Array.isArray(child)) child.forEach(append);
    else if (child instanceof Node) node.append(child);
    else node.append(document.createTextNode(String(child)));
  };
  children.forEach(append);
  return node;
}

function button(label, { icon, variant = "quiet", small = false, type = "button", onClick, disabled = false, ariaLabel, className = "" } = {}) {
  const node = h("button", {
    className: `button button--${variant}${small ? " button--small" : ""}${className ? ` ${className}` : ""}`,
    type,
    disabled,
    ariaLabel,
    onClick,
  });
  if (icon) node.append(makeIcon(icon, small ? 17 : 19));
  node.append(h("span", { text: label }));
  return node;
}

function iconButton(name, label, onClick, { danger = false } = {}) {
  return h("button", {
    className: `icon-button${danger ? " button--danger" : ""}`,
    type: "button",
    title: label,
    ariaLabel: label,
    onClick,
  }, makeIcon(name));
}

function getCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(prefix));
  if (!item) return "";
  try {
    return decodeURIComponent(item.slice(prefix.length));
  } catch {
    return "";
  }
}

function errorMessage(payload, fallback = "操作未完成，请稍后重试") {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload.slice(0, 300);
  let message = fallback;
  if (payload.error && typeof payload.error.message === "string") message = payload.error.message;
  else if (payload.detail && typeof payload.detail.message === "string") message = payload.detail.message;
  if (Array.isArray(payload.detail)) {
    message = payload.detail.map((item) => item && item.msg).filter(Boolean).join("；") || fallback;
  }
  else if (typeof payload.message === "string") message = payload.message;
  const fields = payload?.error?.fields;
  if (Array.isArray(fields) && fields.length) {
    const labels = [...new Set(fields.map((fieldName) => FIELD_LABELS[fieldName] || fieldName))];
    message = `${message}（请检查：${labels.join("、")}）`;
  }
  const requestId = payload?.error?.request_id;
  return requestId ? `${message}（请求编号：${requestId}）` : message;
}

function errorCode(payload) {
  return payload?.error?.code || payload?.detail?.code || "request_failed";
}

function markValidationErrors(root, error) {
  root.querySelectorAll("[aria-invalid='true']").forEach((node) => node.removeAttribute("aria-invalid"));
  const fields = error?.payload?.error?.fields;
  if (!Array.isArray(fields)) return;
  let first = null;
  for (const fieldName of fields) {
    const control = root.querySelector(`[name="${CSS.escape(String(fieldName))}"]`);
    if (!control) continue;
    control.setAttribute("aria-invalid", "true");
    first ||= control;
  }
  first?.focus();
}

async function parseResponse(response) {
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return response.json();
  const text = await response.text();
  return text ? { message: text.slice(0, 300) } : null;
}

async function refreshSession() {
  if (state.refreshPromise) return state.refreshPromise;
  state.refreshPromise = (async () => {
    const csrf = getCookie("beta_csrf");
    if (!csrf) throw new ApiError("登录已过期，请重新登录", 401, "session_expired");
    const response = await fetch(`${API_ROOT}/auth/refresh`, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: "{}",
    });
    const payload = await parseResponse(response);
    if (!response.ok) throw new ApiError(errorMessage(payload, "登录已过期，请重新登录"), response.status, errorCode(payload), payload);
    if (!payload?.user || payload.user.role !== "admin") throw new ApiError("该账户没有管理后台权限", 403, "admin_required");
    state.user = payload.user;
    return payload.user;
  })().finally(() => {
    state.refreshPromise = null;
  });
  return state.refreshPromise;
}

async function api(path, { method = "GET", json, body, retryAuth = true, retryReauth = true, signal } = {}) {
  const headers = { Accept: "application/json" };
  const upperMethod = method.toUpperCase();
  if (json !== undefined) headers["Content-Type"] = "application/json";
  if (!["GET", "HEAD", "OPTIONS"].includes(upperMethod)) {
    const csrf = getCookie("beta_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  const response = await fetch(`${API_ROOT}${path}`, {
    method: upperMethod,
    credentials: "same-origin",
    headers,
    body: json !== undefined ? JSON.stringify(json) : body,
    signal,
  });
  if (response.status === 401 && retryAuth && path !== "/auth/login" && path !== "/auth/refresh") {
    try {
      await refreshSession();
      return api(path, { method, json, body, retryAuth: false, retryReauth, signal });
    } catch (error) {
      if (state.user) showLogin("登录已过期，请重新登录");
      throw error;
    }
  }
  const payload = await parseResponse(response);
  if (response.status === 403 && retryReauth && errorCode(payload) === "admin_reauthentication_required" && path !== "/auth/reauthenticate") {
    await requestReauthentication();
    return api(path, { method, json, body, retryAuth, retryReauth: false, signal });
  }
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status, errorCode(payload), payload);
  return payload;
}

function setLoading(active) {
  state.loadingCount = Math.max(0, state.loadingCount + (active ? 1 : -1));
  els.loadingBar.hidden = state.loadingCount === 0;
  els.viewRoot.setAttribute("aria-busy", state.loadingCount > 0 ? "true" : "false");
}

async function withLoading(operation) {
  setLoading(true);
  try {
    return await operation();
  } finally {
    setLoading(false);
  }
}

function toast(message, type = "success", timeout = null) {
  const item = h("div", { className: `toast${type === "error" ? " toast--error" : ""}`, role: type === "error" ? "alert" : "status" },
    makeIcon(type === "error" ? "alert" : "check"),
    h("p", { text: message }),
  );
  const close = h("button", { type: "button", ariaLabel: "关闭消息", onClick: () => item.remove() }, makeIcon("close", 16));
  item.append(close);
  els.toastRegion.append(item);
  const duration = timeout ?? (type === "error" ? 0 : 4200);
  if (duration > 0) window.setTimeout(() => item.remove(), duration);
}

function safeAssetUrl(value, expectedPrefix = "/api/v1/files/") {
  if (typeof value !== "string" || !value) return "";
  try {
    const parsed = new URL(value, window.location.origin);
    if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith(expectedPrefix)) return "";
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return "";
  }
}

function initials(value) {
  const text = String(value || "应用").trim();
  return Array.from(text).slice(0, 2).join("").toUpperCase();
}

function appIcon(app, large = false) {
  const box = h("span", { className: `app-icon${large ? " app-icon--large" : ""}`, text: initials(app?.name) });
  const url = safeAssetUrl(app?.icon_url);
  if (url) {
    const img = h("img", { src: url, alt: "", loading: "lazy" });
    img.addEventListener("error", () => box.replaceChildren(document.createTextNode(initials(app?.name))), { once: true });
    box.replaceChildren(img);
  }
  return box;
}

const dateFormatter = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dateFormatter.format(date).replaceAll("/", "-");
}

function localDateTimeToIso(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let size = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && size >= 1024; index += 1) {
    size /= 1024;
    unit = units[index];
  }
  return `${size >= 100 ? size.toFixed(0) : size.toFixed(1)} ${unit}`;
}

function badge(kind, value) {
  let label = value || "未知";
  let tone = "neutral";
  if (kind === "app") {
    label = LABELS.appStatus[value] || value;
    tone = value === "published" ? "success" : value === "archived" ? "neutral" : "warning";
  } else if (kind === "version") {
    label = LABELS.versionStatus[value] || value;
    tone = value === "published" ? "success" : value === "disabled" ? "neutral" : "warning";
  } else if (kind === "availability") {
    label = value ? "当前可下载" : "不可下载";
    tone = value ? "info" : "neutral";
  } else if (kind === "bug") {
    label = LABELS.bugStatus[value] || value;
    tone = value === "closed" ? "success" : value === "pending" ? "warning" : "info";
  } else if (kind === "download") {
    label = LABELS.downloadStatus[value] || value;
    tone = value === "completed" ? "success" : value === "failed" ? "danger" : value === "cancelled" ? "neutral" : "info";
  } else if (kind === "active") {
    label = value ? "启用" : "停用";
    tone = value ? "success" : "neutral";
  } else if (kind === "groupLifecycle") {
    label = value ? "使用中" : "已删除";
    tone = value ? "success" : "neutral";
  } else if (kind === "userLifecycle") {
    label = value ? "正常" : "已删除";
    tone = value ? "success" : "neutral";
  } else if (kind === "deleted") {
    label = value ? "已删除" : "当前反馈";
    tone = value ? "danger" : "info";
  } else if (kind === "outcome") {
    label = LABELS.outcome[value] || value;
    tone = value === "success" ? "success" : value === "failure" ? "danger" : "warning";
  } else if (kind === "visibility") {
    label = LABELS.visibility[value] || value;
    tone = value === "private" ? "warning" : "info";
  } else if (kind === "role") {
    label = LABELS.role[value] || value;
    tone = value === "admin" ? "info" : "neutral";
  }
  return h("span", { className: `badge badge--${tone}`, text: label });
}

function primaryCell(title, subtitle = "") {
  const cell = h("span", { className: "primary-cell" }, h("strong", { text: title || "—" }));
  if (subtitle) cell.append(h("small", { text: subtitle }));
  return cell;
}

function chipSet(items, mapLabel = (value) => value) {
  const wrap = h("span", { className: "chip-set" });
  if (!items?.length) return h("span", { text: "—" });
  for (const item of items) wrap.append(h("span", { className: "chip", text: mapLabel(item) || item }));
  return wrap;
}

function dataTable(headers, rows) {
  const headRow = h("tr");
  headers.forEach((header, index) => {
    const cell = h("th", {
      scope: "col",
      className: index === headers.length - 1 ? "cell-actions-heading" : "",
    });
    if (header instanceof Node) cell.append(header);
    else cell.textContent = String(header);
    headRow.append(cell);
  });
  const body = h("tbody");
  for (const cells of rows) {
    const row = h("tr");
    cells.forEach((cell, index) => row.append(h("td", { className: index === cells.length - 1 ? "cell-actions" : "" }, cell)));
    body.append(row);
  }
  return h("div", { className: "table-shell" }, h("table", { className: "data-table" }, h("thead", {}, headRow), body));
}

function toggleBulkMode(route) {
  const bulk = state.bulk[route];
  if (!bulk) return;
  bulk.enabled = !bulk.enabled;
  bulk.selected.clear();
  renderRoute(route);
}

function reconcileBulkSelection(route, items) {
  const bulk = state.bulk[route];
  const config = BULK_CONFIG[route];
  if (!bulk || !config) return;
  const availableIds = new Set(items.filter(config.isSelectable).map((item) => item.id));
  for (const id of bulk.selected) {
    if (!availableIds.has(id)) bulk.selected.delete(id);
  }
}

function bulkHeaderCheckbox(route, items) {
  const config = BULK_CONFIG[route];
  const selectable = items.filter(config.isSelectable);
  const input = h("input", {
    type: "checkbox",
    className: "bulk-checkbox",
    ariaLabel: `全选本页${config.entityLabel}`,
    dataset: { bulkSelectAll: route },
    onChange: () => {
      if (input.checked) selectable.forEach((item) => state.bulk[route].selected.add(item.id));
      else selectable.forEach((item) => state.bulk[route].selected.delete(item.id));
      syncBulkControls(route, items);
    },
  });
  return h("span", { className: "bulk-check-cell" }, input);
}

function bulkRowCheckbox(route, item) {
  const config = BULK_CONFIG[route];
  const selectable = config.isSelectable(item);
  const input = h("input", {
    type: "checkbox",
    className: "bulk-checkbox",
    checked: state.bulk[route].selected.has(item.id),
    disabled: !selectable,
    ariaLabel: selectable ? `选择${config.entityLabel} ${config.displayName(item)}` : "当前管理员不能选择",
    title: selectable ? "" : "不能批量操作当前登录的管理员账号",
    dataset: { bulkRow: route, bulkId: item.id },
    onChange: () => {
      if (input.checked) state.bulk[route].selected.add(item.id);
      else state.bulk[route].selected.delete(item.id);
      syncBulkControls(route, state.bulk[route].pageItems || []);
    },
  });
  return h("span", { className: "bulk-check-cell" }, input);
}

function bulkSelectionBar(route, items) {
  const config = BULK_CONFIG[route];
  state.bulk[route].pageItems = items;
  const deactivate = button(config.deactivateLabel, {
    small: true,
    variant: "danger",
    icon: config.deactivateLabel === "归档" ? "disable" : "trash",
    onClick: () => runBulkLifecycle(route, items, true),
  });
  deactivate.dataset.bulkAction = "deactivate";
  const restore = button(config.restoreLabel, {
    small: true,
    variant: "tonal",
    icon: "refresh",
    onClick: () => runBulkLifecycle(route, items, false),
  });
  restore.dataset.bulkAction = "restore";
  const permanent = button("永久删除", {
    small: true,
    variant: "danger",
    icon: "trash",
    onClick: () => openBulkPermanentDelete(route, items),
  });
  permanent.dataset.bulkAction = "permanent";
  const bar = h("section", { className: "bulk-action-bar", dataset: { bulkBar: route } },
    h("div", { className: "bulk-action-bar__summary" },
      h("span", { className: "bulk-action-bar__icon" }, makeIcon("check", 18)),
      h("span", {}, h("strong", { text: "批量管理" }), h("small", { dataset: { bulkCount: route }, text: "尚未选择条目" })),
    ),
    h("div", { className: "bulk-action-bar__actions" }, deactivate, restore, permanent),
  );
  window.setTimeout(() => syncBulkControls(route, items), 0);
  return bar;
}

function syncBulkControls(route, items) {
  const bulk = state.bulk[route];
  const config = BULK_CONFIG[route];
  if (!bulk || !config) return;
  const selectable = items.filter(config.isSelectable);
  const selectedItems = selectable.filter((item) => bulk.selected.has(item.id));
  const inactive = selectedItems.filter(config.isInactive);
  const active = selectedItems.filter((item) => !config.isInactive(item));
  document.querySelectorAll(`[data-bulk-row="${route}"]`).forEach((input) => {
    input.checked = bulk.selected.has(input.dataset.bulkId);
    input.closest("tr")?.classList.toggle("is-selected", input.checked);
  });
  document.querySelectorAll(`[data-bulk-select-all="${route}"]`).forEach((input) => {
    input.checked = selectable.length > 0 && selectedItems.length === selectable.length;
    input.indeterminate = selectedItems.length > 0 && selectedItems.length < selectable.length;
  });
  const count = document.querySelector(`[data-bulk-count="${route}"]`);
  if (count) count.textContent = selectedItems.length ? `已选择 ${selectedItems.length} 条` : "尚未选择条目";
  const bar = document.querySelector(`[data-bulk-bar="${route}"]`);
  if (!bar) return;
  const deactivate = bar.querySelector('[data-bulk-action="deactivate"]');
  const restore = bar.querySelector('[data-bulk-action="restore"]');
  const permanent = bar.querySelector('[data-bulk-action="permanent"]');
  setBulkButtonState(deactivate, active.length, config.deactivateLabel);
  setBulkButtonState(restore, inactive.length, config.restoreLabel);
  if (permanent) {
    const eligible = selectedItems.length > 0 && inactive.length === selectedItems.length;
    permanent.disabled = !eligible;
    permanent.title = eligible ? "" : `永久删除要求所选条目全部处于“${config.inactiveStateLabel}”状态`;
    permanent.querySelector("span").textContent = eligible ? `永久删除 (${selectedItems.length})` : "永久删除";
  }
}

function setBulkButtonState(control, count, label) {
  if (!control) return;
  control.disabled = count === 0;
  control.querySelector("span").textContent = count ? `${label} (${count})` : label;
}

async function runBulkLifecycle(route, items, makeInactive) {
  const bulk = state.bulk[route];
  const config = BULK_CONFIG[route];
  const candidates = items.filter((item) => bulk.selected.has(item.id) && config.isInactive(item) !== makeInactive);
  if (!candidates.length) return;
  const actionLabel = makeInactive ? config.deactivateLabel : config.restoreLabel;
  if (!window.confirm(`确定批量${actionLabel}所选的 ${candidates.length} 个${config.entityLabel}吗？`)) return;
  const failures = [];
  let completed = 0;
  setLoading(true);
  try {
    for (const item of candidates) {
      try {
        await config.updateLifecycle(item, makeInactive);
        bulk.selected.delete(item.id);
        completed += 1;
      } catch (error) {
        failures.push({ item, error });
        if (error.status === 401 || error.code === "reauthentication_cancelled") break;
      }
    }
    invalidate(...config.cacheKeys);
    if (failures.length) toast(`已完成 ${completed} 条，${failures.length} 条未能${actionLabel}：${failures[0].error.message}`, "error");
    else toast(`已批量${actionLabel} ${completed} 个${config.entityLabel}`);
    renderRoute(route);
  } finally {
    setLoading(false);
  }
}

function openBulkPermanentDelete(route, items) {
  const bulk = state.bulk[route];
  const config = BULK_CONFIG[route];
  const candidates = items.filter((item) => bulk.selected.has(item.id));
  if (!candidates.length || candidates.some((item) => !config.isInactive(item))) {
    toast(`请只选择处于“${config.inactiveStateLabel}”状态的条目`, "error");
    return;
  }
  const password = textInput({
    name: "current_password",
    type: "password",
    required: true,
    maxLength: 128,
    autocomplete: "current-password",
    placeholder: "请输入当前管理员密码",
  });
  const body = h("div", { className: "form-stack" },
    h("section", { className: "deleted-notice" }, makeIcon("alert", 21), h("div", {},
      h("strong", { text: `即将永久删除 ${candidates.length} 个${config.entityLabel}` }),
      h("p", { text: `${config.permanentImpact}永久删除后无法恢复。` }),
    )),
    h("div", { className: "bulk-delete-preview" }, candidates.slice(0, 6).map((item) => h("span", { text: config.displayName(item) })), candidates.length > 6 ? h("small", { text: `另有 ${candidates.length - 6} 条` }) : null),
    field("当前管理员密码", password, { hint: "本批操作只需输入一次当前管理员密码。" }),
  );
  openEntityDialog({
    title: "确认批量永久删除",
    body,
    submitLabel: `验证密码并永久删除 (${candidates.length})`,
    onSubmit: async () => {
      const failures = [];
      let completed = 0;
      for (const item of candidates) {
        try {
          await api(`/admin/${config.permanentResource}/${encodeURIComponent(item.id)}`, {
            method: "DELETE",
            json: { current_password: password.value },
            retryReauth: false,
          });
          bulk.selected.delete(item.id);
          completed += 1;
        } catch (error) {
          if (error.code === "current_password_invalid" || error.code === "admin_reauth_rate_limited") throw error;
          failures.push({ item, error });
        }
      }
      invalidate(...config.cacheKeys);
      if (failures.length) toast(`已永久删除 ${completed} 条，${failures.length} 条被系统保留：${failures[0].error.message}`, "error");
      else toast(`已永久删除 ${completed} 个${config.entityLabel}`);
      renderRoute(route);
    },
  });
}

function pagination(pageData, onPage) {
  const totalPages = Math.max(1, Math.ceil(pageData.total / pageData.page_size));
  const summary = h("span", { text: `共 ${pageData.total} 条 · 第 ${pageData.page}/${totalPages} 页` });
  const actions = h("span", { className: "pagination__actions" },
    iconButton("chevronLeft", "上一页", () => onPage(pageData.page - 1)),
    iconButton("chevronRight", "下一页", () => onPage(pageData.page + 1)),
  );
  actions.firstElementChild.disabled = pageData.page <= 1;
  actions.lastElementChild.disabled = pageData.page >= totalPages;
  return h("nav", { className: "pagination", ariaLabel: "分页" }, summary, actions);
}

function emptyState(title, description, { actionLabel, onAction, icon = "info" } = {}) {
  const inner = h("div", { className: "empty-state__inner" },
    h("span", { className: "empty-state__icon" }, makeIcon(icon, 25)),
    h("h2", { text: title }),
    h("p", { text: description }),
  );
  if (actionLabel && onAction) inner.append(button(actionLabel, { variant: "tonal", icon: "plus", onClick: onAction }));
  return h("section", { className: "surface-card empty-state" }, inner);
}

function errorState(error, retry) {
  return h("section", { className: "surface-card error-state" }, h("div", { className: "error-state__inner" },
    h("span", { className: "error-state__icon" }, makeIcon("alert", 25)),
    h("h2", { text: "页面暂时无法加载" }),
    h("p", { text: error?.message || "请检查网络后重试" }),
    button("重新加载", { variant: "tonal", icon: "refresh", onClick: retry }),
  ));
}

function showSkeleton() {
  els.viewRoot.replaceChildren(h("div", { className: "skeleton-stack", ariaLabel: "正在加载" },
    h("div", { className: "skeleton skeleton--hero" }),
    h("div", { className: "skeleton skeleton--row" }),
    h("div", { className: "skeleton skeleton--row" }),
  ));
}

function setPageActions(...actions) {
  els.pageActions.replaceChildren(...actions.flat().filter(Boolean));
}

function toolbarField(label, control, grow = false) {
  return h("label", { className: `toolbar-field${grow ? " toolbar-field--grow" : ""}` }, h("span", { text: label }), control);
}

function textInput({ name, value = "", placeholder = "", type = "text", required = false, maxLength, minLength, inputMode, autocomplete, disabled = false, readOnly = false } = {}) {
  return h("input", { name, value, placeholder, type, required, maxLength, minLength, inputMode, autocomplete, disabled, readOnly });
}

function selectInput({ name, value = "", options = [], required = false, ariaLabel } = {}) {
  const select = h("select", { name, required, ariaLabel });
  for (const option of options) {
    select.append(h("option", { value: option.value, text: option.label, selected: String(option.value) === String(value), disabled: option.disabled || false }));
  }
  return select;
}

function field(label, control, { hint = "", full = false } = {}) {
  const wrapper = h("label", { className: `field${full ? " field--full" : ""}` }, h("span", { text: label }), control);
  if (hint) wrapper.append(h("small", { className: "field-hint", text: hint }));
  return wrapper;
}

function textareaInput({ name, value = "", placeholder = "", required = false, maxLength = 5000, rows = 5 } = {}) {
  return h("textarea", { name, value, placeholder, required, maxLength, rows });
}

function checkboxChoices(name, items, selected = [], { emptyText = "暂无可选项", subtitle = () => "" } = {}) {
  const wrap = h("div", { className: "choice-grid" });
  if (!items.length) {
    wrap.append(h("p", { className: "field-hint", text: emptyText }));
    return wrap;
  }
  const selectedSet = new Set(selected || []);
  for (const item of items) {
    const copy = h("span", {}, h("strong", { text: item.name || item.display_name || "未命名" }));
    const secondary = subtitle(item);
    if (secondary) copy.append(h("small", { text: secondary }));
    wrap.append(h("label", { className: "choice-item" }, h("input", { type: "checkbox", name, value: item.id, checked: selectedSet.has(item.id) }), copy));
  }
  return wrap;
}

function checkedValues(root, name) {
  return Array.from(root.querySelectorAll(`input[name="${name}"]:checked`), (node) => node.value);
}

function openEntityDialog({ title, body, submitLabel = "保存", onSubmit }) {
  els.dialogTitle.textContent = title;
  els.dialogBody.replaceChildren(body);
  els.dialogSubmit.textContent = submitLabel;
  els.dialogSubmit.disabled = false;
  els.dialogError.hidden = true;
  els.dialogError.textContent = "";
  state.entitySubmit = onSubmit;
  if (els.detailDialog.open) els.detailDialog.close();
  if (!els.entityDialog.open) els.entityDialog.showModal();
  window.setTimeout(() => els.dialogBody.querySelector("input:not([type='hidden']), textarea, select")?.focus(), 0);
}

function openDetailDialog(title, body) {
  els.detailTitle.textContent = title;
  els.detailBody.replaceChildren(body);
  if (!els.detailDialog.open) els.detailDialog.showModal();
}

function closeDialogs() {
  if (els.entityDialog.open) els.entityDialog.close();
  if (els.detailDialog.open) els.detailDialog.close();
}

function invalidate(...keys) {
  for (const key of keys) state.cache[key] = null;
}

async function loadAll(kind, force = false) {
  if (!force && state.cache[kind]) return state.cache[kind];
  const path = kind === "apps" ? "/admin/apps?page_size=100" : kind === "groups" ? "/admin/groups?page_size=100" : "/admin/users?page_size=100";
  const page = await api(path);
  state.cache[kind] = page.items;
  return page.items;
}

function mapById(items) {
  return new Map(items.map((item) => [item.id, item]));
}

function currentRoute() {
  const raw = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  return Object.hasOwn(ROUTES, raw) ? raw : "dashboard";
}

function showLogin(message = "") {
  if (state.reauthRequest) cancelReauthentication("登录状态已失效");
  state.user = null;
  closeDialogs();
  if (els.passwordDialog.open) els.passwordDialog.close();
  els.consoleView.hidden = true;
  els.loginView.hidden = false;
  els.loginError.hidden = !message;
  els.loginError.textContent = message;
  els.loginForm.querySelector("input[name='password']").value = "";
  window.setTimeout(() => els.loginForm.querySelector("input[name='phone']")?.focus(), 0);
}

function enterConsole(user) {
  if (!user || user.role !== "admin") {
    showLogin("该账户没有管理后台权限");
    return;
  }
  state.user = user;
  els.accountName.textContent = user.display_name;
  els.accountPhone.textContent = user.phone;
  els.accountAvatar.textContent = initials(user.display_name).slice(0, 1);
  els.loginView.hidden = true;
  els.consoleView.hidden = false;
  if (user.must_change_password && !els.passwordDialog.open) els.passwordDialog.showModal();
  navigate(currentRoute(), { replace: true });
}

function navigate(route, { replace = false } = {}) {
  const safeRoute = Object.hasOwn(ROUTES, route) ? route : "dashboard";
  const target = `#${safeRoute}`;
  if (replace) {
    window.history.replaceState(null, "", target);
    renderRoute(safeRoute);
  } else if (window.location.hash !== target) {
    window.location.hash = target;
  } else {
    renderRoute(safeRoute);
  }
}

async function renderRoute(route = currentRoute()) {
  if (!state.user) return;
  const routeInfo = ROUTES[route] || ROUTES.dashboard;
  state.route = route;
  document.body.dataset.route = route;
  const renderId = ++state.renderId;
  els.pageTitle.textContent = routeInfo.title;
  els.pageDescription.textContent = routeInfo.description;
  els.primaryNav.querySelectorAll("[data-route]").forEach((item) => {
    if (item.dataset.route === route) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });
  setPageActions();
  showSkeleton();
  setLoading(true);
  try {
    await RENDERERS[route](renderId);
    if (renderId === state.renderId) els.viewRoot.focus({ preventScroll: true });
  } catch (error) {
    if (renderId !== state.renderId || error?.name === "AbortError") return;
    els.viewRoot.replaceChildren(errorState(error, () => renderRoute(route)));
  } finally {
    setLoading(false);
  }
}

function isCurrentRender(renderId) {
  return renderId === state.renderId;
}

async function renderDashboard(renderId) {
  const [summary, appsPage, groups, bugsPage] = await Promise.all([
    api("/admin/dashboard"),
    api("/admin/apps?status=published&page_size=100"),
    loadAll("groups"),
    api("/admin/bugs?page_size=5"),
  ]);
  if (!isCurrentRender(renderId)) return;
  els.bugNavCount.textContent = String(summary.open_bugs);
  els.bugNavCount.hidden = summary.open_bugs === 0;
  const completionRate = summary.downloads_started_7d > 0
    ? Math.round((summary.downloads_completed_7d / summary.downloads_started_7d) * 100)
    : 0;
  const healthTitle = summary.active_apps === 0
    ? "还没有正在内测的应用"
    : `${summary.active_apps} 个应用正在内测`;
  const publishedVersionSummary = summary.published_versions > 0
    ? `当前有 ${summary.published_versions} 个已发布版本面向测试用户开放。`
    : "当前还没有已发布版本。";
  const lens = h("section", { className: "lens-card dashboard-lens" },
    h("div", { className: "dashboard-lens__copy" },
      h("h2", { text: healthTitle }),
      h("p", { text: `${publishedVersionSummary}近 7 天发起 ${summary.downloads_started_7d} 次下载，完成 ${summary.downloads_completed_7d} 次；下载完成仅代表文件校验通过，不代表安装成功。` }),
    ),
    h("div", { className: "lens-facts" },
      lensFact(summary.active_apps, "已发布应用"),
      lensFact(summary.published_versions, "已发布版本"),
      lensFact(summary.open_bugs, "未关闭 Bug"),
      lensFact(`${completionRate}%`, "下载完成率"),
    ),
  );
  const metrics = h("section", { className: "metric-grid" },
    metricTile("活跃用户", summary.active_users, "可登录的后台与测试账户"),
    metricTile("近 7 天下载请求", summary.downloads_started_7d, "客户端每次发起下载时计数，包含失败、取消和未完成"),
    metricTile("近 7 天下载完成", summary.downloads_completed_7d, "文件接收与摘要校验完成，不等于安装成功"),
  );
  const groupMap = mapById(groups);
  const testingApps = h("section", { className: "testing-apps-section" },
    h("header", { className: "section-heading" },
      h("div", {}, h("h2", { text: "正在测试的应用" }), h("p", { text: "已发布并对测试组开放的应用，集中查看版本与参与范围。" })),
      button("管理全部应用", { small: true, variant: "tonal", icon: "apps", onClick: () => navigate("apps") }),
    ),
    appsPage.items.length
      ? h("div", { className: "testing-app-grid" },
        appsPage.items.map((app) => testingAppCard(app, groupMap)),
        h("button", { className: "testing-app-add-card", type: "button", onClick: () => openAppForm() },
          h("span", {}, makeIcon("plus", 24)), h("strong", { text: "添加内测应用" }), h("small", { text: "创建应用资料并上传首个 APK" }),
        ),
      )
      : h("div", { className: "testing-apps-empty" }, h("p", { text: "目前没有正在测试的应用。发布首个 APK 版本后会显示在这里。" }), button("前往应用管理", { small: true, variant: "tonal", onClick: () => navigate("apps") })),
  );
  const recentBugs = surfaceListCard("最近更新的 Bug", "优先处理仍未关闭的问题", bugsPage.items.map((bug) => {
    return h("li", { className: "compact-list__item" },
      h("div", { className: "compact-list__top" }, primaryCell(bug.title, `${bug.reference} · ${bug.app_name} ${bug.version_name}`), badge("bug", bug.status)),
      h("div", { className: "inline-actions" }, h("time", { text: formatDate(bug.updated_at) }), button("查看", { small: true, onClick: () => openBugDetail(bug.id) })),
    );
  }), "目前没有 Bug 反馈", () => navigate("bugs"));
  els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, lens, metrics, testingApps, recentBugs));
}

function testingAppCard(app, groupMap) {
  const version = app.current_version;
  const groupNames = app.group_ids.map((id) => groupMap.get(id)?.name || "未知测试组");
  const groupSummary = groupNames.length > 2
    ? `${groupNames.slice(0, 2).join("、")} 等 ${groupNames.length} 个测试组`
    : groupNames.join("、") || "尚未分配测试组";
  return h("article", { className: "testing-app-card" },
    h("div", { className: "testing-app-card__head" },
      appIcon(app, true),
      h("div", { className: "testing-app-card__identity" }, h("h3", { text: app.name }), h("p", { className: "mono", text: app.package_name })),
      badge("app", app.status),
    ),
    h("p", { className: "testing-app-card__description", text: app.short_description || "暂未填写应用简介。" }),
    h("div", { className: "testing-app-card__facts" },
      h("span", {}, h("small", { text: "当前版本" }), h("strong", { text: version ? `v${version.version_name}` : "—" })),
      h("span", {}, h("small", { text: "版本代码" }), h("strong", { text: version ? version.version_code : "—" })),
      h("span", {}, h("small", { text: "测试范围" }), h("strong", { text: `${groupNames.length} 个组` })),
    ),
    h("div", { className: "testing-app-card__footer" },
      h("span", { className: "testing-app-card__groups", text: groupSummary, title: groupSummary }),
      button("查看详情", { small: true, variant: "quiet", icon: "arrowRight", onClick: () => openAppDetail(app.id) }),
    ),
  );
}

function lensFact(value, label) {
  return h("span", { className: "lens-fact" }, h("strong", { text: value }), h("span", { text: label }));
}

function metricTile(label, value, note) {
  return h("article", { className: "metric-tile" }, h("span", {}, h("span", { text: label }), makeIcon("info", 16)), h("strong", { text: value }), h("small", { text: note }));
}

function surfaceListCard(title, description, items, emptyText, onEmptyAction) {
  const card = h("article", { className: "surface-card surface-card--padded" },
    h("header", { className: "section-heading" }, h("div", {}, h("h2", { text: title }), h("p", { text: description }))),
  );
  if (items.length) card.append(h("ul", { className: "compact-list" }, items));
  else card.append(h("div", { className: "empty-state__inner" }, h("p", { text: emptyText }), button("开始设置", { small: true, variant: "tonal", onClick: onEmptyAction })));
  return card;
}

async function renderApps(renderId) {
  const filters = state.filters.apps;
  const bulk = state.bulk.apps;
  setPageActions(
    button(bulk.enabled ? "完成管理" : "批量管理", { variant: bulk.enabled ? "tonal" : "quiet", icon: bulk.enabled ? "check" : "edit", onClick: () => toggleBulkMode("apps") }),
    button("新建应用", { variant: "primary", icon: "plus", onClick: () => openAppForm() }),
    iconButton("refresh", "刷新应用列表", () => { invalidate("apps"); renderRoute("apps"); }),
  );
  const params = new URLSearchParams({ page: String(filters.page), page_size: "20" });
  if (filters.search) params.set("search", filters.search);
  if (filters.status) params.set("status", filters.status);
  if (filters.group_id) params.set("group_id", filters.group_id);
  const [pageData, groups] = await Promise.all([api(`/admin/apps?${params}`), loadAll("groups")]);
  if (!isCurrentRender(renderId)) return;
  reconcileBulkSelection("apps", pageData.items);
  const groupMap = mapById(groups);
  const search = textInput({ name: "search", value: filters.search, placeholder: "应用名称或包名" });
  const statusSelect = selectInput({ name: "status", value: filters.status, options: [
    { value: "", label: "全部状态" },
    ...Object.entries(LABELS.appStatus).map(([value, label]) => ({ value, label })),
  ] });
  const groupSelect = selectInput({ name: "group_id", value: filters.group_id, options: [
    { value: "", label: "全部测试组" },
    ...groups.map((group) => ({ value: group.id, label: group.name })),
  ] });
  const toolbar = h("form", { className: "toolbar", onSubmit: (event) => {
    event.preventDefault();
    filters.search = search.value.trim();
    filters.status = statusSelect.value;
    filters.group_id = groupSelect.value;
    filters.page = 1;
    renderRoute("apps");
  } },
  toolbarField("搜索", search, true), toolbarField("状态", statusSelect), toolbarField("测试组", groupSelect),
  button("筛选", { type: "submit", variant: "tonal", icon: "search" }),
  button("清除", { onClick: () => {
    Object.assign(filters, { search: "", status: "", group_id: "", page: 1 });
    renderRoute("apps");
  } }));
  if (!pageData.items.length) {
    els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, toolbar, emptyState("没有匹配的应用", "可以调整筛选条件，或创建第一个需要内测的应用。", { actionLabel: "新建应用", onAction: () => openAppForm(), icon: "apps" })));
    return;
  }
  const rows = pageData.items.map((app) => {
    const appIdentity = h("span", { className: "app-cell" }, appIcon(app), primaryCell(app.name, app.package_name));
    const current = app.current_version
      ? primaryCell(app.current_version.version_name, `versionCode ${app.current_version.version_code}`)
      : h("span", { text: "尚未发布" });
    const groupNames = app.group_ids.map((id) => groupMap.get(id)?.name || "未知测试组");
    const actions = h("span", { className: "inline-actions" },
      button("详情", { small: true, variant: "tonal", icon: "eye", onClick: () => openAppDetail(app.id) }),
      iconButton("edit", `编辑 ${app.name}`, () => openAppForm(app.id)),
      button(app.status === "archived" ? "恢复" : "归档", { small: true, variant: app.status === "archived" ? "quiet" : "danger", icon: app.status === "archived" ? "refresh" : "disable", onClick: () => changeAppLifecycle(app) }),
      app.status === "archived" ? button("永久删除", { small: true, variant: "danger", icon: "trash", onClick: () => openPermanentDelete({
        resource: "apps", id: app.id, label: `应用“${app.name}”`, route: "apps", cacheKeys: ["apps", "groups"],
        impact: "全部 APK 版本、图标、应用截图、下载记录和关联 Bug（含附件、评论、处理轨迹）都会被清除。",
      }) }) : null,
    );
    return [bulk.enabled ? bulkRowCheckbox("apps", app) : null, appIdentity, badge("app", app.status), current, chipSet(groupNames), h("time", { text: formatDate(app.updated_at) }), actions].filter((cell) => cell !== null);
  });
  const headers = ["应用", "状态", "当前版本", "可见测试组", "最近更新", "操作"];
  if (bulk.enabled) headers.unshift(bulkHeaderCheckbox("apps", pageData.items));
  els.viewRoot.replaceChildren(h("div", { className: "view-stack" },
    toolbar,
    bulk.enabled ? bulkSelectionBar("apps", pageData.items) : null,
    dataTable(headers, rows),
    pagination(pageData, (page) => { filters.page = page; renderRoute("apps"); }),
  ));
}

async function openAppForm(appId = null) {
  try {
    setLoading(true);
    const [groups, app] = await Promise.all([
      loadAll("groups"),
      appId ? api(`/admin/apps/${encodeURIComponent(appId)}`) : Promise.resolve(null),
    ]);
    const grid = h("div", { className: "form-grid" });
    grid.append(
      field("应用名称", textInput({ name: "name", value: app?.name || "", required: true, maxLength: 100, placeholder: "例如：审批助手" })),
      field("Android 包名", textInput({ name: "package_name", value: app?.package_name || "", required: !app, maxLength: 255, placeholder: "com.company.app", disabled: Boolean(app) }), { hint: app ? "应用创建后不可修改包名。" : "必须与随后上传的 APK 完全一致。" }),
      field("一句话简介", textInput({ name: "short_description", value: app?.short_description || "", maxLength: 180, placeholder: "显示在客户端应用列表中" }), { full: true }),
      field("完整说明", textareaInput({ name: "description", value: app?.description || "", maxLength: 5000, placeholder: "说明用途、测试重点和使用注意事项" }), { full: true }),
    );
    grid.append(field("可见测试组", checkboxChoices("group_ids", groups, app?.group_ids || [], { subtitle: (group) => `${group.member_ids.length} 位成员` }), { full: true, hint: "未分配测试组时，普通测试用户不会看到此应用。" }));
    if (app) grid.append(managementPanel({
      title: app.status === "archived" ? "恢复应用" : "归档应用",
      description: app.status === "archived"
        ? "恢复后应用会回到草稿状态。需要上传并发布一个新的 APK 版本，测试用户才能再次下载。"
        : "归档后测试用户将看不到此应用，所有版本会停止下载；版本、下载、Bug 与审计记录都会保留。",
      actionLabel: app.status === "archived" ? "恢复为草稿" : "归档应用",
      restore: app.status === "archived",
      onAction: () => changeAppLifecycle(app),
    }));
    if (app?.status === "archived") grid.append(managementPanel({
      title: "永久删除应用",
      description: "将彻底清除该应用、全部 APK 与截图、下载记录及关联 Bug。此操作无法撤销。",
      actionLabel: "永久删除",
      onAction: () => openPermanentDelete({
        resource: "apps", id: app.id, label: `应用“${app.name}”`, route: "apps", cacheKeys: ["apps", "groups"],
        impact: "全部 APK 版本、图标、应用截图、下载记录和关联 Bug（含附件、评论、处理轨迹）都会被清除。",
      }),
    }));
    openEntityDialog({
      title: app ? `编辑 ${app.name}` : "新建内测应用",
      body: grid,
      submitLabel: app ? "保存应用" : "创建应用",
      onSubmit: async () => {
        const formData = new FormData(els.entityForm);
        const payload = {
          name: String(formData.get("name") || "").trim(),
          short_description: String(formData.get("short_description") || "").trim(),
          description: String(formData.get("description") || "").trim(),
          group_ids: checkedValues(els.entityForm, "group_ids"),
        };
        if (!app) payload.package_name = String(formData.get("package_name") || "").trim();
        const saved = await api(app ? `/admin/apps/${encodeURIComponent(app.id)}` : "/admin/apps", { method: app ? "PATCH" : "POST", json: payload });
        invalidate("apps", "groups");
        toast(app ? "应用资料已保存" : "应用已创建，可以继续上传图标、截图和 APK");
        navigate("apps");
        if (!app) window.setTimeout(() => openAppDetail(saved.id), 120);
      },
    });
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function openAppDetail(appId) {
  try {
    setLoading(true);
    const [app, groups] = await Promise.all([api(`/admin/apps/${encodeURIComponent(appId)}`), loadAll("groups")]);
    const groupMap = mapById(groups);
    const heroActions = h("div", { className: "action-row" },
      button("编辑资料", { variant: "tonal", small: true, icon: "edit", onClick: () => openAppForm(app.id) }),
      button("更新图标", { variant: "quiet", small: true, icon: "image", onClick: () => openIconUpload(app) }),
      button("上传 APK", { variant: "primary", small: true, icon: "upload", onClick: () => openApkUpload(app) }),
      button(app.status === "archived" ? "恢复" : "归档", { variant: app.status === "archived" ? "quiet" : "danger", small: true, icon: app.status === "archived" ? "refresh" : "disable", onClick: () => changeAppLifecycle(app) }),
      app.status === "archived" ? button("永久删除", { variant: "danger", small: true, icon: "trash", onClick: () => openPermanentDelete({
        resource: "apps", id: app.id, label: `应用“${app.name}”`, route: "apps", cacheKeys: ["apps", "groups"],
        impact: "全部 APK 版本、图标、应用截图、下载记录和关联 Bug（含附件、评论、处理轨迹）都会被清除。",
      }) }) : null,
    );
    const hero = h("section", { className: "detail-hero" }, appIcon(app, true),
      h("div", { className: "detail-hero__copy" }, h("h3", { text: app.name }), h("p", { className: "mono", text: app.package_name }), h("div", { className: "chip-set" }, badge("app", app.status))),
      heroActions,
    );
    const groupsSection = detailSection("可见范围", "只有这些测试组的有效用户能看到和下载应用。",
      chipSet(app.group_ids, (id) => groupMap.get(id)?.name || "未知测试组"));
    const descriptionSection = detailSection("应用说明", app.short_description || "未填写一句话简介", h("p", { className: "prose", text: app.description || "暂未填写完整说明。" }));
    const screenshotsSection = buildScreenshotSection(app);
    const versionsSection = buildVersionSection(app);
    const body = h("div", { className: "view-stack" }, hero, descriptionSection, groupsSection, screenshotsSection, versionsSection);
    openDetailDialog(`${app.name} · 详情`, body);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function detailSection(title, description, content, actions = null) {
  return h("section", { className: "detail-section" },
    h("header", { className: "section-heading" }, h("div", {}, h("h2", { text: title }), description ? h("p", { text: description }) : null), actions),
    content,
  );
}

function managementPanel({ title, description, actionLabel, onAction, restore = false }) {
  return h("section", { className: `management-panel form-grid__full${restore ? " management-panel--restore" : ""}` },
    h("div", { className: "management-panel__copy" }, h("strong", { text: title }), h("p", { text: description })),
    button(actionLabel, { variant: restore ? "tonal" : "danger", icon: restore ? "refresh" : "trash", onClick: onAction }),
  );
}

function openPermanentDelete({ resource, id, label, impact, route, cacheKeys = [] }) {
  const password = textInput({
    name: "current_password",
    type: "password",
    required: true,
    maxLength: 128,
    autocomplete: "current-password",
    placeholder: "请输入当前管理员密码",
  });
  const body = h("div", { className: "form-stack" },
    h("section", { className: "deleted-notice" }, makeIcon("alert", 21), h("div", {},
      h("strong", { text: `即将永久删除${label}` }),
      h("p", { text: `${impact}永久删除后无法恢复。` }),
    )),
    field("当前管理员密码", password, { hint: "为了防止误操作，每次永久删除都必须重新输入当前登录管理员的密码。" }),
  );
  openEntityDialog({
    title: "确认永久删除",
    body,
    submitLabel: "验证密码并永久删除",
    onSubmit: async () => {
      await api(`/admin/${resource}/${encodeURIComponent(id)}`, {
        method: "DELETE",
        json: { current_password: password.value },
        retryReauth: false,
      });
      invalidate(...cacheKeys);
      toast(`${label}已永久删除`);
      renderRoute(route);
    },
  });
}

async function changeAppLifecycle(app) {
  const restoring = app.status === "archived";
  const message = restoring
    ? `确定恢复应用“${app.name}”吗？应用将恢复为草稿，需要发布新的 APK 版本后才能重新下载。`
    : `确定归档应用“${app.name}”吗？测试用户将无法看到或下载，但历史版本、下载记录和 Bug 会保留。`;
  if (!window.confirm(message)) return;
  try {
    await withLoading(() => api(`/admin/apps/${encodeURIComponent(app.id)}`, { method: "PATCH", json: { status: restoring ? "draft" : "archived" } }));
    invalidate("apps", "groups");
    closeDialogs();
    toast(restoring ? "应用已恢复为草稿" : "应用已归档，所有版本已停止下载");
    renderRoute(state.route === "dashboard" ? "dashboard" : "apps");
  } catch (error) {
    toast(error.message, "error");
  }
}

function buildScreenshotSection(app) {
  const actions = button("上传截图", { small: true, variant: "tonal", icon: "image", disabled: app.screenshots.length >= 10, onClick: () => openScreenshotUpload(app) });
  let content;
  if (!app.screenshots.length) {
    content = h("p", { className: "field-hint", text: "尚未上传应用截图。客户端详情页将无法展示界面预览。" });
  } else {
    const grid = h("div", { className: "screenshot-grid" });
    for (const shot of app.screenshots) {
      const box = h("figure", { className: "screenshot-item" });
      const url = safeAssetUrl(shot.url);
      if (url) box.append(h("img", { src: url, alt: `${app.name} 应用截图 ${shot.position + 1}`, loading: "lazy" }));
      box.append(iconButton("trash", `删除第 ${shot.position + 1} 张截图`, () => deleteScreenshot(app, shot), { danger: true }));
      grid.append(box);
    }
    content = grid;
  }
  return detailSection("应用截图", `共 ${app.screenshots.length}/10 张，按上传位置在客户端展示。`, content, actions);
}

function buildVersionSection(app) {
  const actions = button("上传 APK", { small: true, variant: "tonal", icon: "upload", onClick: () => openApkUpload(app) });
  if (!app.versions.length) return detailSection("版本记录", "APK 先上传并完成校验，再由管理员独立发布。", h("p", { className: "field-hint", text: "还没有上传过 APK。" }), actions);
  const list = h("div", { className: "version-list" });
  for (const version of app.versions) {
    const meta = h("div", { className: "version-item__meta" },
      h("span", { text: `versionCode ${version.version_code}` }),
      h("span", { text: formatBytes(version.file_size) }),
      h("span", { text: `minSdk ${version.min_sdk ?? "—"}` }),
      h("span", { text: `targetSdk ${version.target_sdk ?? "—"}` }),
      h("span", { text: formatDate(version.published_at || version.created_at) }),
    );
    const copy = h("div", {}, h("h4", {}, `v${version.version_name} `, badge("version", version.status), " ", badge("availability", version.download_enabled)), meta);
    if (version.release_notes) copy.append(h("p", { text: version.release_notes }));
    copy.append(h("details", {}, h("summary", { text: "查看文件校验摘要" }), h("p", { className: "mono", text: `SHA-256 ${version.sha256}\n签名证书 ${version.signing_cert_sha256}` })));
    const versionActions = h("div", { className: "version-item__actions" });
    if (version.status === "draft") versionActions.append(button("发布", { small: true, variant: "primary", icon: "publish", onClick: () => openPublishVersion(app, version) }));
    if (version.status !== "disabled") versionActions.append(button("停用", { small: true, variant: "danger", icon: "disable", onClick: () => disableVersion(app, version) }));
    list.append(h("article", { className: "version-item" }, copy, versionActions));
  }
  return detailSection("版本记录", "发布与停用均会写入审计日志。", list, actions);
}

async function deleteScreenshot(app, shot) {
  if (!window.confirm(`确定删除 ${app.name} 的第 ${shot.position + 1} 张截图吗？`)) return;
  try {
    await withLoading(() => api(`/admin/apps/${encodeURIComponent(app.id)}/screenshots/${encodeURIComponent(shot.id)}`, { method: "DELETE" }));
    invalidate("apps");
    toast("应用截图已删除");
    await openAppDetail(app.id);
  } catch (error) {
    toast(error.message, "error");
  }
}

function openIconUpload(app) {
  const input = h("input", { name: "file", type: "file", accept: "image/png,image/jpeg,image/webp", required: true });
  openEntityDialog({
    title: `上传 ${app.name} 图标`,
    body: h("div", { className: "form-stack" }, field("图标文件", input, { hint: "支持 PNG、JPEG 或 WebP；服务端会移除元数据并转为 WebP。" })),
    submitLabel: "上传图标",
    onSubmit: async () => {
      const file = input.files?.[0];
      if (!file) throw new ApiError("请选择图标文件");
      const body = new FormData();
      body.append("file", file);
      await api(`/admin/apps/${encodeURIComponent(app.id)}/icon`, { method: "POST", body });
      invalidate("apps");
      toast("应用图标已更新");
      navigate("apps");
      window.setTimeout(() => openAppDetail(app.id), 120);
    },
  });
}

function openScreenshotUpload(app) {
  const input = h("input", { name: "file", type: "file", accept: "image/png,image/jpeg,image/webp", required: true });
  const position = h("input", { name: "position", type: "number", min: 0, max: 9, value: app.screenshots.length });
  const body = h("div", { className: "form-grid" },
    field("截图文件", input, { full: true, hint: "建议上传竖屏实机截图；服务端会统一转码并移除 EXIF。" }),
    field("插入位置", position, { full: true, hint: "从 0 开始；留空会追加到末尾。" }),
  );
  openEntityDialog({
    title: `上传 ${app.name} 截图`, body, submitLabel: "上传截图",
    onSubmit: async () => {
      const file = input.files?.[0];
      if (!file) throw new ApiError("请选择截图文件");
      const formData = new FormData();
      formData.append("file", file);
      if (position.value !== "") formData.append("position", position.value);
      await api(`/admin/apps/${encodeURIComponent(app.id)}/screenshots`, { method: "POST", body: formData });
      invalidate("apps");
      toast("应用截图已上传");
      navigate("apps");
      window.setTimeout(() => openAppDetail(app.id), 120);
    },
  });
}

function openApkUpload(app) {
  const input = h("input", { name: "file", type: "file", accept: ".apk,application/vnd.android.package-archive", required: true });
  const notes = textareaInput({ name: "release_notes", maxLength: 5000, placeholder: "可先记录版本变化；发布时仍需确认最终更新说明。" });
  const body = h("div", { className: "form-stack" },
    field("已签名 APK", input, { hint: `包名必须是 ${app.package_name}，versionCode 必须大于历史版本。` }),
    field("版本更新说明", notes),
    h("p", { className: "field-hint field-hint--warning", text: "上传只会完成文件、包名、版本号和签名校验，不会自动发布给测试用户。" }),
  );
  openEntityDialog({
    title: `上传 ${app.name} APK`, body, submitLabel: "上传并校验",
    onSubmit: async () => {
      const file = input.files?.[0];
      if (!file) throw new ApiError("请选择 APK 文件");
      const formData = new FormData();
      formData.append("file", file);
      formData.append("release_notes", notes.value.trim());
      await api(`/admin/apps/${encodeURIComponent(app.id)}/versions`, { method: "POST", body: formData });
      invalidate("apps");
      toast("APK 已通过校验并保存为待发布版本");
      navigate("apps");
      window.setTimeout(() => openAppDetail(app.id), 120);
    },
  });
}

function openPublishVersion(app, version) {
  const notes = textareaInput({ name: "release_notes", value: version.release_notes || "", required: true, maxLength: 5000, placeholder: "说明本次版本变化和测试重点" });
  const body = h("div", { className: "form-stack" },
    h("div", { className: "bug-summary-card" }, h("strong", { text: `${app.name} v${version.version_name}` }), h("span", { className: "mono", text: `versionCode ${version.version_code}` }), h("span", { text: formatBytes(version.file_size) })),
    field("最终更新说明", notes, { hint: "发布后，该版本立即对已分配测试组的用户可见并可下载。" }),
  );
  openEntityDialog({
    title: "确认发布版本", body, submitLabel: "确认发布",
    onSubmit: async () => {
      await api(`/admin/apps/${encodeURIComponent(app.id)}/versions/${encodeURIComponent(version.id)}/publish`, { method: "POST", json: { release_notes: notes.value.trim() } });
      invalidate("apps");
      toast(`v${version.version_name} 已发布`);
      navigate("apps");
      window.setTimeout(() => openAppDetail(app.id), 120);
    },
  });
}

async function disableVersion(app, version) {
  if (!window.confirm(`确定停用 ${app.name} v${version.version_name} 吗？停用后将无法继续下载。`)) return;
  try {
    await withLoading(() => api(`/admin/apps/${encodeURIComponent(app.id)}/versions/${encodeURIComponent(version.id)}/disable`, { method: "POST" }));
    invalidate("apps");
    toast("版本下载已停用");
    navigate("apps");
    await openAppDetail(app.id);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function renderGroups(renderId) {
  const filters = state.filters.groups;
  const bulk = state.bulk.groups;
  setPageActions(
    button(bulk.enabled ? "完成管理" : "批量管理", { variant: bulk.enabled ? "tonal" : "quiet", icon: bulk.enabled ? "check" : "edit", onClick: () => toggleBulkMode("groups") }),
    button("新建测试组", { variant: "primary", icon: "plus", onClick: () => openGroupForm() }),
    iconButton("refresh", "刷新测试组", () => { invalidate("groups"); renderRoute("groups"); }),
  );
  const params = new URLSearchParams({ page: String(filters.page), page_size: "20" });
  if (filters.search) params.set("search", filters.search);
  if (filters.active) params.set("active", filters.active);
  const pageData = await api(`/admin/groups?${params}`);
  if (!isCurrentRender(renderId)) return;
  reconcileBulkSelection("groups", pageData.items);
  const search = textInput({ name: "search", value: filters.search, placeholder: "测试组名称" });
  const active = selectInput({ name: "active", value: filters.active, options: [
    { value: "", label: "全部状态" }, { value: "true", label: "使用中" }, { value: "false", label: "已删除" },
  ] });
  const toolbar = h("form", { className: "toolbar", onSubmit: (event) => {
    event.preventDefault();
    filters.search = search.value.trim();
    filters.active = active.value;
    filters.page = 1;
    renderRoute("groups");
  } }, toolbarField("搜索", search, true), toolbarField("状态", active), button("筛选", { type: "submit", variant: "tonal", icon: "search" }), button("清除", { onClick: () => {
    Object.assign(filters, { search: "", active: "", page: 1 });
    renderRoute("groups");
  } }));
  if (!pageData.items.length) {
    els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, toolbar, emptyState("没有匹配的测试组", "测试组用于同时管理成员与可见应用。", { actionLabel: "新建测试组", onAction: () => openGroupForm(), icon: "groups" })));
    return;
  }
  const rows = pageData.items.map((group) => [
    bulk.enabled ? bulkRowCheckbox("groups", group) : null,
    primaryCell(group.name, group.description || "未填写说明"),
    badge("groupLifecycle", group.is_active),
    h("span", { className: "mono", text: String(group.member_ids.length) }),
    h("span", { className: "mono", text: String(group.app_ids.length) }),
    h("time", { text: formatDate(group.updated_at) }),
    h("span", { className: "inline-actions" },
      button("编辑", { small: true, variant: "tonal", icon: "edit", onClick: () => openGroupForm(group.id) }),
      button(group.is_active ? "删除" : "恢复", { small: true, variant: group.is_active ? "danger" : "quiet", icon: group.is_active ? "trash" : "refresh", onClick: () => toggleGroup(group) }),
      !group.is_active ? button("永久删除", { small: true, variant: "danger", icon: "trash", onClick: () => openPermanentDelete({
        resource: "groups", id: group.id, label: `测试组“${group.name}”`, route: "groups", cacheKeys: ["groups", "users", "apps"],
        impact: "该组与用户、应用之间的所有关联都会被清除，但用户和应用本身不会被删除。",
      }) }) : null,
    ),
  ].filter((cell) => cell !== null));
  const headers = ["测试组", "状态", "成员", "应用", "最近更新", "操作"];
  if (bulk.enabled) headers.unshift(bulkHeaderCheckbox("groups", pageData.items));
  els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, toolbar, bulk.enabled ? bulkSelectionBar("groups", pageData.items) : null, dataTable(headers, rows), pagination(pageData, (page) => {
    filters.page = page;
    renderRoute("groups");
  })));
}

async function openGroupForm(groupId = null) {
  try {
    setLoading(true);
    const [users, apps, group] = await Promise.all([
      loadAll("users"),
      loadAll("apps"),
      groupId ? api(`/admin/groups/${encodeURIComponent(groupId)}`) : Promise.resolve(null),
    ]);
    const grid = h("div", { className: "form-grid" },
      field("测试组名称", textInput({ name: "name", value: group?.name || "", required: true, maxLength: 100, placeholder: "例如：财务流程内测组" })),
      field("用途说明", textareaInput({ name: "description", value: group?.description || "", maxLength: 500, rows: 3, placeholder: "说明该组负责测试的业务范围" }), { full: true }),
      field("组内用户", checkboxChoices("member_ids", users, group?.member_ids || [], { subtitle: (user) => `${user.phone} · ${LABELS.role[user.role] || user.role}` }), { full: true }),
      field("可见应用", checkboxChoices("app_ids", apps, group?.app_ids || [], { subtitle: (app) => app.package_name }), { full: true }),
    );
    if (group) grid.append(managementPanel({
      title: group.is_active ? "删除测试组" : "恢复测试组",
      description: group.is_active
        ? "删除后，该组不再授予应用查看和下载权限；成员、关联应用和历史记录都会保留，并可恢复。"
        : "恢复后，该组会重新向有效成员授予所关联应用的访问权限。",
      actionLabel: group.is_active ? "删除测试组" : "恢复测试组",
      restore: !group.is_active,
      onAction: () => toggleGroup(group),
    }));
    if (group && !group.is_active) grid.append(managementPanel({
      title: "永久删除测试组",
      description: "将彻底清除该测试组及其成员、应用关联，但不会删除用户和应用本身。此操作无法撤销。",
      actionLabel: "永久删除",
      onAction: () => openPermanentDelete({
        resource: "groups", id: group.id, label: `测试组“${group.name}”`, route: "groups", cacheKeys: ["groups", "users", "apps"],
        impact: "该组与用户、应用之间的所有关联都会被清除，但用户和应用本身不会被删除。",
      }),
    }));
    openEntityDialog({
      title: group ? `编辑 ${group.name}` : "新建测试组", body: grid, submitLabel: group ? "保存测试组" : "创建测试组",
      onSubmit: async () => {
        const formData = new FormData(els.entityForm);
        const payload = {
          name: String(formData.get("name") || "").trim(),
          description: String(formData.get("description") || "").trim(),
          member_ids: checkedValues(els.entityForm, "member_ids"),
          app_ids: checkedValues(els.entityForm, "app_ids"),
        };
        await api(group ? `/admin/groups/${encodeURIComponent(group.id)}` : "/admin/groups", { method: group ? "PATCH" : "POST", json: payload });
        invalidate("groups", "users", "apps");
        toast(group ? "测试组已保存" : "测试组已创建");
        renderRoute("groups");
      },
    });
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function toggleGroup(group) {
  const verb = group.is_active ? "删除" : "恢复";
  const detail = group.is_active ? "删除后成员将失去该组授予的应用访问权限，但关联与历史记录会保留并可恢复。" : "恢复后会重新授予关联应用的访问权限。";
  if (!window.confirm(`确定${verb}测试组“${group.name}”吗？${detail}`)) return;
  try {
    await withLoading(() => api(`/admin/groups/${encodeURIComponent(group.id)}`, { method: "PATCH", json: { is_active: !group.is_active } }));
    invalidate("groups", "users", "apps");
    closeDialogs();
    toast(`测试组已${verb}`);
    renderRoute("groups");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function renderUsers(renderId) {
  const filters = state.filters.users;
  const bulk = state.bulk.users;
  setPageActions(
    button(bulk.enabled ? "完成管理" : "批量管理", { variant: bulk.enabled ? "tonal" : "quiet", icon: bulk.enabled ? "check" : "edit", onClick: () => toggleBulkMode("users") }),
    button("新建用户", { variant: "primary", icon: "plus", onClick: () => openUserForm() }),
    iconButton("refresh", "刷新用户", () => { invalidate("users"); renderRoute("users"); }),
  );
  const params = new URLSearchParams({ page: String(filters.page), page_size: "20" });
  for (const key of ["search", "active", "role", "group_id"]) if (filters[key]) params.set(key, filters[key]);
  const [pageData, groups] = await Promise.all([api(`/admin/users?${params}`), loadAll("groups")]);
  if (!isCurrentRender(renderId)) return;
  reconcileBulkSelection("users", pageData.items);
  const groupMap = mapById(groups);
  const search = textInput({ name: "search", value: filters.search, placeholder: "姓名或手机号" });
  const role = selectInput({ name: "role", value: filters.role, options: [{ value: "", label: "全部角色" }, { value: "admin", label: "管理员" }, { value: "tester", label: "测试用户" }] });
  const active = selectInput({ name: "active", value: filters.active, options: [{ value: "", label: "全部状态" }, { value: "true", label: "正常" }, { value: "false", label: "已删除" }] });
  const group = selectInput({ name: "group_id", value: filters.group_id, options: [{ value: "", label: "全部测试组" }, ...groups.map((item) => ({ value: item.id, label: item.name }))] });
  const toolbar = h("form", { className: "toolbar", onSubmit: (event) => {
    event.preventDefault();
    Object.assign(filters, { search: search.value.trim(), role: role.value, active: active.value, group_id: group.value, page: 1 });
    renderRoute("users");
  } }, toolbarField("搜索", search, true), toolbarField("角色", role), toolbarField("状态", active), toolbarField("测试组", group), button("筛选", { type: "submit", variant: "tonal", icon: "search" }), button("清除", { onClick: () => {
    Object.assign(filters, { search: "", role: "", active: "", group_id: "", page: 1 });
    renderRoute("users");
  } }));
  if (!pageData.items.length) {
    els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, toolbar, emptyState("没有匹配的用户", "用户只能由管理员创建，并需绑定唯一手机号。", { actionLabel: "新建用户", onAction: () => openUserForm(), icon: "users" })));
    return;
  }
  const rows = pageData.items.map((user) => [
    bulk.enabled ? bulkRowCheckbox("users", user) : null,
    h("span", { className: "app-cell" }, h("span", { className: "avatar", text: initials(user.display_name).slice(0, 1) }), primaryCell(user.display_name, user.phone)),
    badge("role", user.role),
    badge("userLifecycle", user.is_active),
    chipSet(user.group_ids, (id) => groupMap.get(id)?.name || "未知测试组"),
    primaryCell(user.last_login_at ? formatDate(user.last_login_at) : "尚未登录", user.must_change_password ? "待修改初始密码" : ""),
    h("span", { className: "inline-actions" },
      button("编辑", { small: true, variant: "tonal", icon: "edit", onClick: () => openUserForm(user.id) }),
      iconButton("lock", `重置 ${user.display_name} 的密码`, () => openPasswordReset(user)),
      button(user.is_active ? "删除" : "恢复", { small: true, variant: user.is_active ? "danger" : "quiet", icon: user.is_active ? "trash" : "refresh", onClick: () => toggleUser(user) }),
      !user.is_active ? button("永久删除", { small: true, variant: "danger", icon: "trash", onClick: () => openPermanentDelete({
        resource: "users", id: user.id, label: `用户“${user.display_name}”`, route: "users", cacheKeys: ["users", "groups"],
        impact: "该用户的账号、登录会话、下载记录、Bug 反馈及其评论和处理记录都会被清除。若账号关联已上传 APK，系统会拒绝删除。",
      }) }) : null,
    ),
  ].filter((cell) => cell !== null));
  const headers = ["用户", "角色", "状态", "测试组", "登录情况", "操作"];
  if (bulk.enabled) headers.unshift(bulkHeaderCheckbox("users", pageData.items));
  els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, toolbar, bulk.enabled ? bulkSelectionBar("users", pageData.items) : null, dataTable(headers, rows), pagination(pageData, (page) => {
    filters.page = page;
    renderRoute("users");
  })));
}

async function openUserForm(userId = null) {
  try {
    setLoading(true);
    const [groups, user] = await Promise.all([
      loadAll("groups"),
      userId ? api(`/admin/users/${encodeURIComponent(userId)}`) : Promise.resolve(null),
    ]);
    const grid = h("div", { className: "form-grid" },
      field("姓名", textInput({ name: "display_name", value: user?.display_name || "", required: true, maxLength: 80, autocomplete: "off" })),
      field("手机号", textInput({ name: "phone", value: user?.phone || "", required: true, maxLength: 20, inputMode: "tel", autocomplete: "off" })),
      field("角色", selectInput({ name: "role", value: user?.role || "tester", options: [{ value: "tester", label: "测试用户" }, { value: "admin", label: "管理员" }] })),
    );
    if (!user) grid.append(field("初始密码", textInput({ name: "initial_password", type: "password", required: true, minLength: 10, maxLength: 128, autocomplete: "new-password" }), { full: true, hint: "至少 10 位，同时包含大小写字母、数字和符号；首次登录必须修改。" }));
    grid.append(field("所属测试组", checkboxChoices("group_ids", groups, user?.group_ids || [], { subtitle: (group) => group.description || `${group.member_ids.length} 位成员` }), { full: true }));
    if (user) grid.append(managementPanel({
      title: user.is_active ? "删除用户" : "恢复用户",
      description: user.is_active
        ? "删除会立即撤销该用户的全部登录会话并阻止再次登录；Bug、下载和审计历史仍会保留，并可恢复。"
        : "恢复后该用户可以重新登录，并按所属测试组获得应用访问权限。",
      actionLabel: user.is_active ? "删除用户" : "恢复用户",
      restore: !user.is_active,
      onAction: () => toggleUser(user),
    }));
    if (user && !user.is_active) grid.append(managementPanel({
      title: "永久删除用户",
      description: "将清除账号、会话、下载与反馈数据。若该账号关联已上传 APK，系统会阻止删除。此操作无法撤销。",
      actionLabel: "永久删除",
      onAction: () => openPermanentDelete({
        resource: "users", id: user.id, label: `用户“${user.display_name}”`, route: "users", cacheKeys: ["users", "groups"],
        impact: "该用户的账号、登录会话、下载记录、Bug 反馈及其评论和处理记录都会被清除。若账号关联已上传 APK，系统会拒绝删除。",
      }),
    }));
    openEntityDialog({
      title: user ? `编辑 ${user.display_name}` : "新建用户", body: grid, submitLabel: user ? "保存用户" : "创建用户",
      onSubmit: async () => {
        const formData = new FormData(els.entityForm);
        const payload = {
          display_name: String(formData.get("display_name") || "").trim(),
          phone: String(formData.get("phone") || "").trim(),
          role: String(formData.get("role") || "tester"),
          group_ids: checkedValues(els.entityForm, "group_ids"),
        };
        if (!user) payload.initial_password = String(formData.get("initial_password") || "");
        await api(user ? `/admin/users/${encodeURIComponent(user.id)}` : "/admin/users", { method: user ? "PATCH" : "POST", json: payload });
        invalidate("users", "groups");
        toast(user ? "用户资料已保存" : "用户已创建，请安全传达初始密码");
        renderRoute("users");
      },
    });
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function openPasswordReset(user) {
  const password = textInput({ name: "new_password", type: "password", required: true, minLength: 10, maxLength: 128, autocomplete: "new-password" });
  const confirm = textInput({ name: "confirm_password", type: "password", required: true, minLength: 10, maxLength: 128, autocomplete: "new-password" });
  const body = h("div", { className: "form-stack" },
    h("p", { className: "dialog-note", text: `重置后，${user.display_name} 的所有现有登录会话将失效。` }),
    field("新密码", password, { hint: "至少 10 位，同时包含大小写字母、数字和符号。" }),
    field("确认新密码", confirm),
    h("p", { className: "field-hint", text: "为保护账户，用户下次登录时必须再次设置自己的密码。" }),
  );
  openEntityDialog({
    title: `重置 ${user.display_name} 的密码`, body, submitLabel: "确认重置",
    onSubmit: async () => {
      if (password.value !== confirm.value) throw new ApiError("两次输入的新密码不一致");
      await api(`/admin/users/${encodeURIComponent(user.id)}/reset-password`, { method: "POST", json: { new_password: password.value, force_change: true } });
      invalidate("users");
      toast("密码已重置，原有会话已失效");
      renderRoute("users");
    },
  });
}

async function toggleUser(user) {
  const verb = user.is_active ? "删除" : "恢复";
  if (!window.confirm(`确定${verb}用户“${user.display_name}”吗？${user.is_active ? "删除会立即撤销其登录会话，但历史数据会保留并可恢复。" : "恢复后该用户可以重新登录。"}`)) return;
  try {
    await withLoading(() => api(`/admin/users/${encodeURIComponent(user.id)}`, { method: "PATCH", json: { is_active: !user.is_active } }));
    invalidate("users", "groups");
    closeDialogs();
    toast(`用户已${verb}`);
    renderRoute("users");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function renderBugs(renderId) {
  const filters = state.filters.bugs;
  const bulk = state.bulk.bugs;
  setPageActions(
    button(bulk.enabled ? "完成管理" : "批量管理", { variant: bulk.enabled ? "tonal" : "quiet", icon: bulk.enabled ? "check" : "edit", onClick: () => toggleBulkMode("bugs") }),
    iconButton("refresh", "刷新 Bug", () => renderRoute("bugs")),
  );
  const params = new URLSearchParams({ page: String(filters.page), page_size: "20" });
  if (filters.status) params.set("status", filters.status);
  if (filters.app_id) params.set("app_id", filters.app_id);
  if (filters.deleted) params.set("deleted", filters.deleted);
  const [pageData, apps, dashboardSummary, pendingPage, progressPage, verifyingPage, closedPage] = await Promise.all([
    api(`/admin/bugs?${params}`),
    loadAll("apps"),
    api("/admin/dashboard"),
    api("/admin/bugs?status=pending&deleted=false&page_size=1"),
    api("/admin/bugs?status=in_progress&deleted=false&page_size=1"),
    api("/admin/bugs?status=verifying&deleted=false&page_size=1"),
    api("/admin/bugs?status=closed&deleted=false&page_size=1"),
  ]);
  if (!isCurrentRender(renderId)) return;
  reconcileBulkSelection("bugs", pageData.items);
  const openCount = pageData.items.filter((bug) => bug.status !== "closed").length;
  els.bugNavCount.textContent = String(dashboardSummary.open_bugs);
  els.bugNavCount.hidden = dashboardSummary.open_bugs === 0;
  const status = selectInput({ name: "status", value: filters.status, options: [{ value: "", label: "全部状态" }, ...Object.entries(LABELS.bugStatus).map(([value, label]) => ({ value, label }))] });
  const app = selectInput({ name: "app_id", value: filters.app_id, options: [{ value: "", label: "全部应用" }, ...apps.map((item) => ({ value: item.id, label: item.name }))] });
  const deleted = selectInput({ name: "deleted", value: filters.deleted, options: [{ value: "false", label: "当前反馈" }, { value: "true", label: "已删除" }] });
  const toolbar = h("form", { className: "toolbar", onSubmit: (event) => {
    event.preventDefault();
    Object.assign(filters, { status: status.value, app_id: app.value, deleted: deleted.value, page: 1 });
    renderRoute("bugs");
  } }, toolbarField("数据范围", deleted), toolbarField("状态", status), toolbarField("应用", app, true), button("筛选", { type: "submit", variant: "tonal", icon: "search" }), button("清除", { onClick: () => {
    Object.assign(filters, { status: "", app_id: "", deleted: "false", page: 1 });
    renderRoute("bugs");
  } }));
  const bugMetrics = h("section", { className: "metric-grid bug-metric-grid" },
    metricTile("待处理", pendingPage.total, "等待管理员确认与处理"),
    metricTile("处理中", progressPage.total, "已经进入处理流程"),
    metricTile("待验证", verifyingPage.total, "等待反馈人确认结果"),
    metricTile("已关闭", closedPage.total, "已经完成处理记录"),
  );
  if (!pageData.items.length) {
    els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, bugMetrics, toolbar, emptyState("没有匹配的 Bug", "新的用户反馈会在这里出现，并关联具体应用版本。", { icon: "bugs" })));
    return;
  }
  const rows = pageData.items.map((bug) => [
    bulk.enabled ? bulkRowCheckbox("bugs", bug) : null,
    primaryCell(bug.title, `${bug.reference} · ${bug.app_name}`),
    bug.deleted_at ? badge("deleted", true) : badge("bug", bug.status),
    badge("visibility", bug.visibility),
    primaryCell(bug.reporter_name || "未知提交人", `v${bug.version_name}`),
    h("time", { text: formatDate(bug.updated_at) }),
    h("span", { className: "inline-actions" },
      button(bug.deleted_at ? "查看" : "查看与处理", { small: true, variant: "tonal", icon: "eye", onClick: () => openBugDetail(bug.id) }),
      button(bug.deleted_at ? "恢复" : "删除", { small: true, variant: bug.deleted_at ? "quiet" : "danger", icon: bug.deleted_at ? "refresh" : "trash", onClick: () => changeBugDeletion(bug) }),
      bug.deleted_at ? button("永久删除", { small: true, variant: "danger", icon: "trash", onClick: () => openPermanentDelete({
        resource: "bugs", id: bug.id, label: bug.reference, route: "bugs",
        impact: "问题描述、截图附件、评论和全部处理轨迹都会被清除。",
      }) }) : null,
    ),
  ].filter((cell) => cell !== null));
  const summaryNote = h("p", { className: "field-hint", text: filters.deleted === "true"
    ? "已删除的 Bug 不会出现在测试客户端，截图、评论与处理记录仍保留，可随时恢复。"
    : `当前页有 ${openCount} 个未关闭问题。截图与内部评论仅在授权范围内展示。` });
  const headers = ["问题", "状态", "可见性", "提交信息", "最近更新", "操作"];
  if (bulk.enabled) headers.unshift(bulkHeaderCheckbox("bugs", pageData.items));
  els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, bugMetrics, toolbar, summaryNote, bulk.enabled ? bulkSelectionBar("bugs", pageData.items) : null, dataTable(headers, rows), pagination(pageData, (page) => {
    filters.page = page;
    renderRoute("bugs");
  })));
}

async function openBugDetail(bugId) {
  try {
    setLoading(true);
    const bug = await api(`/admin/bugs/${encodeURIComponent(bugId)}`);
    const app = await api(`/admin/apps/${encodeURIComponent(bug.app_id)}`);
    const fixVersion = app.versions.find((version) => version.id === bug.fix_version_id);
    const headerActions = h("div", { className: "action-row" });
    if (bug.deleted_at) {
      headerActions.append(
        button("恢复 Bug", { small: true, variant: "tonal", icon: "refresh", onClick: () => changeBugDeletion(bug) }),
        button("永久删除", { small: true, variant: "danger", icon: "trash", onClick: () => openPermanentDelete({
          resource: "bugs", id: bug.id, label: bug.reference, route: "bugs",
          impact: "问题描述、截图附件、评论和全部处理轨迹都会被清除。",
        }) }),
      );
    } else {
      if (bug.status !== "closed") headerActions.append(button("更新状态", { small: true, variant: "primary", icon: "publish", onClick: () => openBugStatusForm(bug) }));
      headerActions.append(button(bug.visibility === "group" ? "设为私密" : "测试组可见", { small: true, variant: "tonal", icon: "eye", onClick: () => changeBugVisibility(bug) }));
      headerActions.append(button("删除 Bug", { small: true, variant: "danger", icon: "trash", onClick: () => changeBugDeletion(bug) }));
    }
    const header = h("section", { className: "bug-summary-card" },
      h("div", { className: "section-heading" }, h("div", {}, h("span", { className: "bug-reference", text: bug.reference }), h("h3", { text: bug.title })), headerActions),
      h("div", { className: "chip-set" }, badge("bug", bug.status), badge("visibility", bug.visibility), bug.deleted_at ? badge("deleted", true) : null, h("span", { className: "chip", text: `${bug.app_name} v${bug.version_name}` })),
    );
    const facts = h("div", { className: "fact-grid" },
      factTile("提交人", bug.reporter_name || "未知"),
      factTile("设备", bug.device_model || "未提供"),
      factTile("Android", bug.android_version || "未提供"),
      factTile("客户端版本", bug.client_version || "未提供"),
      factTile("修复版本", fixVersion ? `v${fixVersion.version_name} · versionCode ${fixVersion.version_code}` : "未关联"),
      factTile("创建时间", formatDate(bug.created_at)),
      factTile("最近更新", formatDate(bug.updated_at)),
    );
    const issue = h("div", { className: "view-stack" },
      detailSection("问题描述", "用户提交的现象说明。", h("p", { className: "prose", text: bug.description || "未提供描述" })),
      detailSection("复现步骤", "用于验证问题是否稳定发生。", h("p", { className: "prose", text: bug.reproduction_steps || "未提供复现步骤" })),
      detailSection("环境信息", "由客户端随 Bug 一起提交。", facts),
    );
    const attachments = buildBugAttachments(bug);
    const comments = buildBugComments(bug);
    const transitions = buildBugTransitions(bug);
    const resolution = bug.status === "closed" ? detailSection("处理结论", LABELS.resolution[bug.resolution] || "已关闭", h("p", { className: "prose", text: bug.resolution_note || "未填写结论说明" })) : null;
    const deletedNotice = bug.deleted_at ? h("section", { className: "deleted-notice" }, makeIcon("trash", 20), h("div", {}, h("strong", { text: "此 Bug 已删除" }), h("p", { text: `删除时间：${formatDate(bug.deleted_at)}。测试用户无法查看，所有证据与处理记录仍保留。` }))) : null;
    openDetailDialog(`${bug.reference} · Bug 详情`, h("div", { className: "view-stack" }, deletedNotice, header, issue, attachments, comments, transitions, resolution));
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

function factTile(label, value) {
  return h("span", { className: "fact-tile" }, h("span", { text: label }), h("strong", { text: value || "—" }));
}

function buildBugAttachments(bug) {
  let content = h("p", { className: "field-hint", text: "此 Bug 没有上传截图。" });
  if (bug.attachments?.length) {
    const grid = h("div", { className: "attachment-grid" });
    for (const attachment of bug.attachments) {
      const card = h("figure", { className: "attachment-card" });
      const url = safeAssetUrl(attachment.url);
      if (url && String(attachment.content_type).startsWith("image/")) card.append(h("img", { src: url, alt: `${bug.reference} 用户反馈截图`, loading: "lazy" }));
      else card.append(h("span", {}, makeIcon("file"), " 无法预览此附件"));
      card.append(h("span", { text: `${attachment.content_type} · ${formatBytes(attachment.file_size)}` }));
      grid.append(card);
    }
    content = grid;
  }
  return detailSection("截图证据", `共 ${bug.attachments?.length || 0} 个附件。`, content);
}

function buildBugComments(bug) {
  const action = bug.deleted_at ? null : button("添加评论", { small: true, variant: "tonal", icon: "comment", onClick: () => openBugCommentForm(bug) });
  let content = h("p", { className: "field-hint", text: "暂时没有评论。" });
  if (bug.comments?.length) {
    const list = h("ul", { className: "comment-list" });
    for (const comment of bug.comments) {
      list.append(h("li", { className: `comment-item${comment.is_admin_note ? " comment-item--internal" : ""}` },
        h("div", { className: "comment-item__top" }, h("strong", { text: comment.author_name }), h("span", { className: "inline-actions" }, comment.is_admin_note ? h("span", { className: "chip", text: "仅管理员" }) : null, h("time", { text: formatDate(comment.created_at) }))),
        h("p", { text: comment.content }),
      ));
    }
    content = list;
  }
  return detailSection("协作评论", "普通评论对授权测试用户可见；内部备注仅管理员可见。", content, action);
}

function buildBugTransitions(bug) {
  let content = h("p", { className: "field-hint", text: "还没有状态变化记录。" });
  if (bug.transitions?.length) {
    const list = h("ol", { className: "timeline" });
    for (const transition of [...bug.transitions].reverse()) {
      list.append(h("li", { className: "timeline-item" },
        h("div", { className: "timeline-item__top" }, h("strong", { text: `${transition.actor_name} · ${LABELS.bugStatus[transition.to_status] || transition.to_status}` }), h("time", { text: formatDate(transition.created_at) })),
        transition.note ? h("p", { text: transition.note }) : null,
      ));
    }
    content = list;
  }
  return detailSection("状态记录", "每次处理状态变化均保留操作人和说明。", content);
}

async function openBugStatusForm(bug) {
  try {
    setLoading(true);
    const app = await api(`/admin/apps/${encodeURIComponent(bug.app_id)}`);
    const transitions = {
      pending: ["in_progress", "closed"],
      in_progress: ["verifying", "closed"],
      verifying: ["in_progress", "closed"],
      closed: [],
    };
    const allowed = transitions[bug.status] || [];
    if (!allowed.length) throw new ApiError("已关闭的 Bug 不能继续变更状态");
    const status = selectInput({ name: "status", value: allowed[0], options: allowed.map((value) => ({ value, label: LABELS.bugStatus[value] })) });
    const note = textareaInput({ name: "note", maxLength: 5000, placeholder: "记录处理进展、验证要求或关闭原因" });
    const fixVersion = selectInput({ name: "fix_version_id", options: [{ value: "", label: "请选择修复版本" }, ...app.versions.map((version) => ({ value: version.id, label: `v${version.version_name} · versionCode ${version.version_code}` }))] });
    const resolution = selectInput({ name: "resolution", options: [{ value: "", label: "请选择处理结论" }, ...Object.entries(LABELS.resolution).map(([value, label]) => ({ value, label }))] });
    const fixField = field("修复版本", fixVersion, { full: true });
    const resolutionField = field("处理结论", resolution, { full: true });
    const grid = h("div", { className: "form-grid" }, field("目标状态", status, { full: true }), fixField, resolutionField, field("处理说明", note, { full: true }));
    const updateVisibility = () => {
      const isVerifying = status.value === "verifying";
      const isClosing = status.value === "closed";
      fixField.hidden = !isVerifying && !isClosing;
      resolutionField.hidden = !isClosing;
      fixVersion.required = isVerifying || (isClosing && resolution.value === "fixed");
      resolution.required = isClosing;
    };
    status.addEventListener("change", updateVisibility);
    resolution.addEventListener("change", updateVisibility);
    updateVisibility();
    openEntityDialog({
      title: `更新 ${bug.reference} 状态`, body: grid, submitLabel: "保存状态",
      onSubmit: async () => {
        const payload = { status: status.value, note: note.value.trim() };
        if (status.value === "verifying") payload.fix_version_id = fixVersion.value;
        if (status.value === "closed") {
          payload.resolution = resolution.value;
          if (fixVersion.value) payload.fix_version_id = fixVersion.value;
        }
        await api(`/admin/bugs/${encodeURIComponent(bug.id)}/status`, { method: "PATCH", json: payload });
        toast(`Bug 状态已更新为${LABELS.bugStatus[status.value]}`);
        navigate("bugs");
        window.setTimeout(() => openBugDetail(bug.id), 120);
      },
    });
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setLoading(false);
  }
}

async function changeBugVisibility(bug) {
  const visibility = bug.visibility === "group" ? "private" : "group";
  const label = LABELS.visibility[visibility];
  if (!window.confirm(`确定将 ${bug.reference} 设为“${label}”吗？`)) return;
  try {
    await withLoading(() => api(`/admin/bugs/${encodeURIComponent(bug.id)}/visibility`, { method: "PATCH", json: { visibility } }));
    toast(`Bug 可见范围已改为${label}`);
    navigate("bugs");
    await openBugDetail(bug.id);
  } catch (error) {
    toast(error.message, "error");
  }
}

async function changeBugDeletion(bug) {
  const restoring = Boolean(bug.deleted_at);
  const message = restoring
    ? `确定恢复 ${bug.reference} 吗？恢复后会重新按原可见范围向测试用户显示。`
    : `确定删除 ${bug.reference} 吗？删除后测试用户将无法查看，但截图、评论和处理记录会保留，可由管理员恢复。`;
  if (!window.confirm(message)) return;
  try {
    await withLoading(() => api(`/admin/bugs/${encodeURIComponent(bug.id)}/deletion`, { method: "PATCH", json: { deleted: !restoring } }));
    closeDialogs();
    toast(restoring ? "Bug 已恢复" : "Bug 已删除，历史证据仍保留");
    renderRoute("bugs");
  } catch (error) {
    toast(error.message, "error");
  }
}

function openBugCommentForm(bug) {
  const content = textareaInput({ name: "content", required: true, maxLength: 5000, placeholder: "写下排查进展、修复说明或需要用户补充的信息" });
  const internal = h("input", { type: "checkbox", name: "internal" });
  const body = h("div", { className: "form-stack" }, field("评论内容", content), h("label", { className: "choice-item" }, internal, h("span", {}, h("strong", { text: "仅管理员可见" }), h("small", { text: "用于内部排查记录，不向测试用户展示" }))));
  openEntityDialog({
    title: `评论 ${bug.reference}`, body, submitLabel: "发布评论",
    onSubmit: async () => {
      await api(`/admin/bugs/${encodeURIComponent(bug.id)}/comments`, { method: "POST", json: { content: content.value.trim(), internal: internal.checked } });
      toast(internal.checked ? "内部备注已添加" : "评论已发布");
      navigate("bugs");
      window.setTimeout(() => openBugDetail(bug.id), 120);
    },
  });
}

async function renderDownloads(renderId) {
  const filters = state.filters.downloads;
  setPageActions(iconButton("refresh", "刷新下载记录", () => renderRoute("downloads")));
  const params = new URLSearchParams({ page: String(filters.page), page_size: "20" });
  for (const key of ["status", "user_id", "app_id", "version_id"]) if (filters[key]) params.set(key, filters[key]);
  for (const key of ["created_from", "created_to"]) {
    const value = localDateTimeToIso(filters[key]);
    if (value) params.set(key, value);
  }
  const selectedAppPromise = filters.app_id
    ? api(`/admin/apps/${encodeURIComponent(filters.app_id)}`)
    : Promise.resolve(null);
  const [pageData, users, apps, selectedApp] = await Promise.all([
    api(`/admin/downloads?${params}`),
    loadAll("users"),
    loadAll("apps"),
    selectedAppPromise,
  ]);
  if (!isCurrentRender(renderId)) return;
  const userMap = mapById(users);
  const appMap = mapById(apps);
  const status = selectInput({ name: "status", value: filters.status, options: [{ value: "", label: "全部状态" }, ...Object.entries(LABELS.downloadStatus).map(([value, label]) => ({ value, label }))] });
  const user = selectInput({ name: "user_id", value: filters.user_id, options: [{ value: "", label: "全部用户" }, ...users.map((item) => ({ value: item.id, label: `${item.display_name} · ${item.phone}` }))] });
  const app = selectInput({ name: "app_id", value: filters.app_id, options: [{ value: "", label: "全部应用" }, ...apps.map((item) => ({ value: item.id, label: item.name }))] });
  const version = selectInput({ name: "version_id", value: filters.version_id });
  setDownloadVersionOptions(version, selectedApp?.versions || [], filters.version_id, Boolean(filters.app_id));
  const createdFrom = textInput({ name: "created_from", type: "datetime-local", value: filters.created_from });
  const createdTo = textInput({ name: "created_to", type: "datetime-local", value: filters.created_to });
  app.addEventListener("change", async () => {
    const requestedAppId = app.value;
    setDownloadVersionOptions(version, [], "", false, requestedAppId ? "正在加载版本…" : "请先选择应用");
    if (!requestedAppId) return;
    try {
      const detail = await withLoading(() => api(`/admin/apps/${encodeURIComponent(requestedAppId)}`));
      if (!isCurrentRender(renderId) || app.value !== requestedAppId) return;
      setDownloadVersionOptions(version, detail.versions || [], "", true);
    } catch (error) {
      if (!isCurrentRender(renderId) || app.value !== requestedAppId) return;
      setDownloadVersionOptions(version, [], "", false, "版本加载失败");
      toast(error.message, "error");
    }
  });
  const toolbar = h("form", { className: "toolbar", onSubmit: (event) => {
    event.preventDefault();
    if (createdFrom.value && createdTo.value && new Date(createdFrom.value) > new Date(createdTo.value)) {
      toast("结束时间不能早于开始时间", "error");
      return;
    }
    Object.assign(filters, {
      status: status.value,
      user_id: user.value,
      app_id: app.value,
      version_id: version.value,
      created_from: createdFrom.value,
      created_to: createdTo.value,
      page: 1,
    });
    renderRoute("downloads");
  } }, toolbarField("状态", status), toolbarField("用户", user, true), toolbarField("应用", app, true), toolbarField("版本", version), toolbarField("开始时间", createdFrom), toolbarField("结束时间", createdTo), button("筛选", { type: "submit", variant: "tonal", icon: "search" }), button("清除", { onClick: () => {
    Object.assign(filters, { status: "", user_id: "", app_id: "", version_id: "", created_from: "", created_to: "", page: 1 });
    renderRoute("downloads");
  } }));
  if (!pageData.items.length) {
    els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, toolbar, emptyState("没有匹配的下载记录", "测试用户开始下载后，服务端会在这里生成可追溯记录。", { icon: "downloads" })));
    return;
  }
  const rows = pageData.items.map((record) => {
    const userItem = userMap.get(record.user_id);
    const appItem = appMap.get(record.app_id);
    return [
      primaryCell(userItem?.display_name || "未知用户", userItem?.phone || shortId(record.user_id)),
      primaryCell(appItem?.name || "未知应用", `版本 ${shortId(record.version_id)}`),
      badge("download", record.status),
      primaryCell(record.device_model || "未提供设备", record.android_version ? `Android ${record.android_version}` : ""),
      h("span", { className: "mono", text: formatBytes(record.bytes_sent) }),
      h("time", { text: formatDate(record.completed_at || record.created_at) }),
      button("详情", { small: true, variant: "tonal", icon: "eye", onClick: () => openDownloadDetail(record, userItem, appItem) }),
    ];
  });
  els.viewRoot.replaceChildren(h("div", { className: "view-stack" },
    toolbar,
    h("p", { className: "field-hint", text: "“已完成”表示客户端收到了完整字节并提交摘要确认，不代表用户已经完成 Android 安装。" }),
    dataTable(["用户", "应用与版本", "状态", "设备", "发送字节", "发生时间", "操作"], rows),
    pagination(pageData, (page) => { filters.page = page; renderRoute("downloads"); }),
  ));
}

function setDownloadVersionOptions(control, versions, selectedValue = "", enabled = true, emptyLabel = "请先选择应用") {
  const options = enabled
    ? [{ value: "", label: "全部版本" }, ...versions.map((item) => ({ value: item.id, label: `v${item.version_name} · versionCode ${item.version_code}` }))]
    : [{ value: "", label: emptyLabel }];
  control.replaceChildren(...options.map((item) => h("option", { value: item.value, text: item.label, selected: item.value === selectedValue })));
  control.disabled = !enabled;
}

function shortId(value) {
  const text = String(value || "");
  return text ? `${text.slice(0, 8)}…` : "—";
}

function openDownloadDetail(record, user, app) {
  const facts = h("div", { className: "fact-grid" },
    factTile("用户", user ? `${user.display_name} · ${user.phone}` : record.user_id),
    factTile("应用", app?.name || record.app_id),
    factTile("版本 ID", record.version_id),
    factTile("设备", record.device_model || "未提供"),
    factTile("Android", record.android_version || "未提供"),
    factTile("客户端", record.client_version || "未提供"),
    factTile("请求 IP", record.request_ip || "未记录"),
    factTile("发送字节", formatBytes(record.bytes_sent)),
    factTile("开始时间", formatDate(record.created_at)),
    factTile("完成时间", formatDate(record.completed_at)),
  );
  const body = h("div", { className: "view-stack" },
    h("section", { className: "bug-summary-card" }, h("div", { className: "section-heading" }, h("div", {}, h("span", { className: "bug-reference", text: shortId(record.id) }), h("h3", { text: `${app?.name || "应用下载"} · ${LABELS.downloadStatus[record.status] || record.status}` })), badge("download", record.status))),
    detailSection("下载证据", "记录由服务端与客户端在下载流程中共同更新。", facts),
    record.failure_reason ? detailSection("失败原因", "客户端上报的失败或取消说明。", h("p", { className: "prose", text: record.failure_reason })) : null,
  );
  openDetailDialog("下载记录详情", body);
}

async function renderAudit(renderId) {
  const filters = state.filters.audit;
  setPageActions(iconButton("refresh", "刷新审计日志", () => renderRoute("audit")));
  const params = new URLSearchParams({ page: String(filters.page), page_size: "20" });
  if (filters.action) params.set("action", filters.action);
  if (filters.actor_id) params.set("actor_id", filters.actor_id);
  if (filters.reason_code) params.set("reason_code", filters.reason_code);
  if (filters.request_id) params.set("request_id", filters.request_id);
  const [pageData, users] = await Promise.all([api(`/admin/audit-logs?${params}`), loadAll("users")]);
  if (!isCurrentRender(renderId)) return;
  const action = textInput({ name: "action", value: filters.action, placeholder: "例如：admin.version.publish" });
  const actor = selectInput({ name: "actor_id", value: filters.actor_id, options: [{ value: "", label: "全部操作人" }, ...users.map((item) => ({ value: item.id, label: `${item.display_name} · ${item.phone}` }))] });
  const reasonCode = textInput({ name: "reason_code", value: filters.reason_code, placeholder: "例如：csrf_failed" });
  const requestId = textInput({ name: "request_id", value: filters.request_id, placeholder: "完整请求编号" });
  const toolbar = h("form", { className: "toolbar", onSubmit: (event) => {
    event.preventDefault();
    Object.assign(filters, { action: action.value.trim(), actor_id: actor.value, reason_code: reasonCode.value.trim(), request_id: requestId.value.trim(), page: 1 });
    renderRoute("audit");
  } }, toolbarField("精确操作名", action, true), toolbarField("操作人", actor, true), toolbarField("原因代码", reasonCode, true), toolbarField("请求编号", requestId, true), button("筛选", { type: "submit", variant: "tonal", icon: "search" }), button("清除", { onClick: () => {
    Object.assign(filters, { action: "", actor_id: "", reason_code: "", request_id: "", page: 1 });
    renderRoute("audit");
  } }));
  const explanation = h("section", { className: "audit-explainer" },
    makeIcon("info", 22),
    h("div", {}, h("h2", { text: "审计日志是什么？" }), h("p", { text: "它由服务端自动记录谁在何时对账号、测试组、应用、版本或 Bug 做了什么，以及操作成功或失败的原因，用于追踪误操作和排查安全事件。密码、登录令牌和 APK 内容不会写入日志。" })),
  );
  if (!pageData.items.length) {
    els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, explanation, toolbar, emptyState("没有匹配的审计记录", "登录、账户、测试组、发布与 Bug 管理操作会在这里留痕。", { icon: "audit" })));
    return;
  }
  const rows = pageData.items.map((entry) => [
    primaryCell(entry.action, `${entry.entity_type}${entry.entity_id ? ` · ${shortId(entry.entity_id)}` : ""}`),
    primaryCell(entry.actor_name || "系统或未知用户", entry.actor_id ? shortId(entry.actor_id) : "无账户"),
    badge("outcome", entry.outcome),
    primaryCell(entry.reason_code || "—", entry.request_id ? shortId(entry.request_id) : "无请求编号"),
    h("span", { className: "mono", text: entry.request_ip || "—" }),
    h("time", { text: formatDate(entry.created_at) }),
    button("详情", { small: true, variant: "tonal", icon: "eye", onClick: () => openAuditDetail(entry) }),
  ]);
  els.viewRoot.replaceChildren(h("div", { className: "view-stack" }, explanation, toolbar, dataTable(["操作", "操作人", "结果", "原因 / 请求", "请求 IP", "时间", "操作"], rows), pagination(pageData, (page) => {
    filters.page = page;
    renderRoute("audit");
  })));
}

function openAuditDetail(entry) {
  const body = h("div", { className: "view-stack" },
    h("section", { className: "bug-summary-card" }, h("div", { className: "section-heading" }, h("div", {}, h("span", { className: "bug-reference", text: shortId(entry.id) }), h("h3", { text: entry.action })), badge("outcome", entry.outcome))),
    detailSection("审计主体", "记录由服务端生成，详情仅供授权管理员查看。", h("div", { className: "fact-grid" },
      factTile("操作人", entry.actor_name || "系统或未知用户"),
      factTile("操作人 ID", entry.actor_id || "—"),
      factTile("实体类型", entry.entity_type || "—"),
      factTile("实体 ID", entry.entity_id || "—"),
      factTile("结果原因", entry.reason_code || "—"),
      factTile("请求编号", entry.request_id || "—"),
      factTile("请求 IP", entry.request_ip || "—"),
      factTile("发生时间", formatDate(entry.created_at)),
    )),
    detailSection("结构化详情", "敏感凭据不会写入审计详情。", h("pre", { className: "json-block", text: JSON.stringify(entry.details || {}, null, 2) })),
  );
  openDetailDialog("审计日志详情", body);
}

const RENDERERS = Object.freeze({
  dashboard: renderDashboard,
  apps: renderApps,
  groups: renderGroups,
  bugs: renderBugs,
  users: renderUsers,
  downloads: renderDownloads,
  audit: renderAudit,
});

function requestReauthentication() {
  if (state.reauthRequest) return state.reauthRequest.promise;
  let resolveRequest;
  let rejectRequest;
  const promise = new Promise((resolve, reject) => {
    resolveRequest = resolve;
    rejectRequest = reject;
  });
  state.reauthRequest = { promise, resolve: resolveRequest, reject: rejectRequest };
  els.reauthError.hidden = true;
  els.reauthError.textContent = "";
  els.reauthForm.reset();
  if (!els.reauthDialog.open) els.reauthDialog.showModal();
  window.setTimeout(() => els.reauthForm.elements.password?.focus(), 0);
  return promise;
}

function cancelReauthentication(message = "已取消敏感操作") {
  const pending = state.reauthRequest;
  state.reauthRequest = null;
  els.reauthForm.reset();
  els.reauthError.hidden = true;
  if (els.reauthDialog.open) els.reauthDialog.close();
  if (pending) pending.reject(new ApiError(message, 403, "reauthentication_cancelled"));
}

async function handleLogin(event) {
  event.preventDefault();
  const submit = els.loginForm.querySelector("button[type='submit']");
  const formData = new FormData(els.loginForm);
  els.loginError.hidden = true;
  submit.disabled = true;
  setLoading(true);
  try {
    const result = await api("/auth/login", {
      method: "POST",
      retryAuth: false,
      retryReauth: false,
      json: {
        phone: String(formData.get("phone") || "").trim(),
        password: String(formData.get("password") || ""),
        client_name: "web-admin",
      },
    });
    els.loginForm.querySelector("input[name='password']").value = "";
    if (result.user.role !== "admin") {
      try {
        await api("/auth/logout", { method: "POST", retryAuth: false, retryReauth: false });
      } catch {
        // The UI still rejects this session even if server-side logout could not finish.
      }
      throw new ApiError("该账户没有管理后台权限", 403, "admin_required");
    }
    enterConsole(result.user);
  } catch (error) {
    markValidationErrors(els.loginForm, error);
    els.loginForm.querySelector("input[name='password']").value = "";
    els.loginError.textContent = error.message || "登录失败，请检查手机号和密码";
    els.loginError.hidden = false;
  } finally {
    submit.disabled = false;
    setLoading(false);
  }
}

async function handleLogout() {
  els.logoutButton.disabled = true;
  try {
    await withLoading(() => api("/auth/logout", { method: "POST", retryReauth: false }));
  } catch (error) {
    if (error.status !== 401) toast("退出请求未完成，本机界面已清除登录状态", "error");
  } finally {
    els.logoutButton.disabled = false;
    invalidate("apps", "groups", "users");
    showLogin();
  }
}

async function handlePasswordChange(event) {
  event.preventDefault();
  const formData = new FormData(els.passwordForm);
  const currentPassword = String(formData.get("current_password") || "");
  const newPassword = String(formData.get("new_password") || "");
  const confirmPassword = String(formData.get("confirm_password") || "");
  const submit = els.passwordForm.querySelector("button[type='submit']");
  els.passwordError.hidden = true;
  if (newPassword !== confirmPassword) {
    els.passwordError.textContent = "两次输入的新密码不一致";
    els.passwordError.hidden = false;
    return;
  }
  submit.disabled = true;
  setLoading(true);
  try {
    await api("/auth/change-password", { method: "POST", json: { current_password: currentPassword, new_password: newPassword }, retryReauth: false });
    els.passwordForm.reset();
    if (els.passwordDialog.open) els.passwordDialog.close();
    showLogin("密码已更新，请使用新密码重新登录");
  } catch (error) {
    markValidationErrors(els.passwordForm, error);
    els.passwordForm.elements.current_password.value = "";
    els.passwordError.textContent = error.message;
    els.passwordError.hidden = false;
  } finally {
    submit.disabled = false;
    setLoading(false);
  }
}

async function handleEntitySubmit(event) {
  event.preventDefault();
  if (typeof state.entitySubmit !== "function") return;
  els.dialogError.hidden = true;
  els.dialogError.textContent = "";
  els.entityForm.querySelectorAll("[aria-invalid='true']").forEach((node) => node.removeAttribute("aria-invalid"));
  els.dialogSubmit.disabled = true;
  setLoading(true);
  try {
    await state.entitySubmit();
    if (els.entityDialog.open) els.entityDialog.close();
    state.entitySubmit = null;
  } catch (error) {
    markValidationErrors(els.entityForm, error);
    els.dialogError.textContent = error.message || "保存失败，请检查输入后重试";
    els.dialogError.hidden = false;
  } finally {
    els.dialogSubmit.disabled = false;
    setLoading(false);
  }
}

async function handleReauthentication(event) {
  event.preventDefault();
  const pending = state.reauthRequest;
  if (!pending) return;
  const passwordInput = els.reauthForm.elements.password;
  const submit = els.reauthForm.querySelector("button[type='submit']");
  els.reauthError.hidden = true;
  submit.disabled = true;
  setLoading(true);
  try {
    await api("/auth/reauthenticate", { method: "POST", json: { password: String(passwordInput.value || "") }, retryReauth: false });
    passwordInput.value = "";
    state.reauthRequest = null;
    if (els.reauthDialog.open) els.reauthDialog.close();
    pending.resolve();
  } catch (error) {
    markValidationErrors(els.reauthForm, error);
    passwordInput.value = "";
    els.reauthError.textContent = error.message || "密码验证失败";
    els.reauthError.hidden = false;
    passwordInput.focus();
  } finally {
    submit.disabled = false;
    setLoading(false);
  }
}

function wireEvents() {
  els.loginForm.addEventListener("submit", handleLogin);
  els.logoutButton.addEventListener("click", handleLogout);
  els.sidebarNewApp.addEventListener("click", () => openAppForm());
  els.passwordForm.addEventListener("submit", handlePasswordChange);
  els.entityForm.addEventListener("submit", handleEntitySubmit);
  els.reauthForm.addEventListener("submit", handleReauthentication);
  els.primaryNav.addEventListener("click", (event) => {
    const target = event.target.closest("[data-route]");
    if (target) navigate(target.dataset.route);
  });
  window.addEventListener("hashchange", () => renderRoute(currentRoute()));
  document.querySelectorAll("[data-close-dialog]").forEach((node) => node.addEventListener("click", () => els.entityDialog.close()));
  document.querySelectorAll("[data-close-detail]").forEach((node) => node.addEventListener("click", () => els.detailDialog.close()));
  document.querySelectorAll("[data-cancel-reauth]").forEach((node) => node.addEventListener("click", () => cancelReauthentication()));
  els.entityDialog.addEventListener("close", () => {
    els.entityForm.reset();
    state.entitySubmit = null;
  });
  els.passwordDialog.addEventListener("cancel", (event) => event.preventDefault());
  els.reauthDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    cancelReauthentication();
  });
}

async function boot() {
  hydrateStaticIcons();
  wireEvents();
  showLogin();
  setLoading(true);
  try {
    const user = await api("/auth/me", { retryReauth: false });
    enterConsole(user);
  } catch (error) {
    if (error.status !== 401) {
      els.loginError.textContent = "无法恢复登录状态，请重新登录";
      els.loginError.hidden = false;
    }
  } finally {
    setLoading(false);
  }
}

boot();
