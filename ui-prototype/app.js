const tabs = [...document.querySelectorAll("[data-view-target]")];
const panels = [...document.querySelectorAll("[data-view]")];
const toast = document.querySelector(".toast");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let toastTimer;

function showToast(message) {
  const activePanel = document.querySelector(".view-panel.is-active");
  const mobileSnackbar = activePanel?.querySelector(".mobile-snackbar");
  if (mobileSnackbar) {
    window.clearTimeout(toastTimer);
    mobileSnackbar.textContent = message;
    mobileSnackbar.setAttribute("aria-hidden", "false");
    mobileSnackbar.classList.add("is-visible");
    toastTimer = window.setTimeout(() => {
      mobileSnackbar.classList.remove("is-visible");
      mobileSnackbar.setAttribute("aria-hidden", "true");
    }, 2800);
    return;
  }

  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.setAttribute("aria-hidden", "false");
  toast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => {
    toast.classList.remove("is-visible");
    toast.setAttribute("aria-hidden", "true");
  }, 2600);
}

function switchView(viewName, updateHash = true) {
  tabs.forEach((tab) => {
    const isActive = tab.dataset.viewTarget === viewName;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-pressed", String(isActive));
  });

  panels.forEach((panel) => {
    const isActive = panel.dataset.view === viewName;
    panel.classList.toggle("is-active", isActive);
    panel.setAttribute("aria-hidden", String(!isActive));
  });

  if (updateHash) {
    window.history.replaceState(null, "", `#${viewName}`);
  }
  window.scrollTo({ top: 0, behavior: reducedMotion.matches ? "auto" : "smooth" });
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.viewTarget));
});

document.querySelectorAll("[data-view-jump]").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.viewJump));
});

document.querySelectorAll("[data-toast]").forEach((button) => {
  button.addEventListener("click", () => showToast(button.dataset.toast));
});

document.querySelectorAll("[data-app-row]").forEach((row) => {
  function selectRow() {
    document.querySelectorAll("[data-app-row]").forEach((candidate) => {
      candidate.classList.remove("is-selected");
      candidate.setAttribute("aria-selected", "false");
    });
    row.classList.add("is-selected");
    row.setAttribute("aria-selected", "true");
    document.querySelector(".admin-shell").classList.remove("detail-closed");
    document.querySelector(".release-dossier").classList.remove("is-closed");
    document.querySelector("#dossier-app-name").textContent = row.dataset.appRow;
  }

  row.addEventListener("click", selectRow);
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectRow();
    }
  });
});

document.querySelector(".close-detail").addEventListener("click", () => {
  document.querySelector(".admin-shell").classList.add("detail-closed");
  document.querySelector(".release-dossier").classList.add("is-closed");
  showToast("应用档案已收起，选择任一应用可重新打开");
});

const searchInput = document.querySelector(".search-field input");
const [statusSelect, groupSelect] = document.querySelectorAll(".compact-select select");

function applyAppFilters() {
  const query = searchInput.value.trim().toLowerCase();
  let visibleCount = 0;
  document.querySelectorAll("[data-app-row]").forEach((row) => {
    const matchesQuery = row.textContent.toLowerCase().includes(query);
    const matchesStatus = statusSelect.value === "全部状态" || row.dataset.status === statusSelect.value;
    const matchesGroup = groupSelect.value === "全部测试组" || row.dataset.group === groupSelect.value;
    const matches = matchesQuery && matchesStatus && matchesGroup;
    row.hidden = !matches;
    if (matches) visibleCount += 1;
  });
  document.querySelector(".result-count").textContent = `共 ${visibleCount} 个应用`;
}

searchInput.addEventListener("input", applyAppFilters);

document.querySelectorAll(".compact-select select").forEach((select) => {
  select.addEventListener("change", () => {
    applyAppFilters();
  });
});

const downloadButton = document.querySelector("#download-button");
const downloadMeta = document.querySelector("#download-meta");

downloadButton.addEventListener("click", () => {
  if (downloadButton.disabled) return;
  if (downloadButton.dataset.state === "complete") {
    showToast("将交给 Android 系统确认安装（原型）");
    return;
  }
  const isRetry = downloadButton.dataset.state === "failed";
  downloadButton.disabled = true;
  downloadButton.setAttribute("aria-busy", "true");
  downloadButton.classList.add("is-progress");
  downloadButton.textContent = isRetry ? "重试中 · 68%" : "下载中 · 68%";
  downloadMeta.textContent = "正在安全下载 APK，请保持页面开启";

  window.setTimeout(() => {
    if (!isRetry) {
      downloadButton.textContent = "下载失败 · 点击重试";
      downloadButton.dataset.state = "failed";
      downloadButton.classList.remove("is-progress");
      downloadButton.disabled = false;
      downloadButton.setAttribute("aria-busy", "false");
      downloadMeta.textContent = "网络连接中断，已保留下载任务";
      showToast("下载未完成，请检查网络后重试");
      return;
    }
    downloadButton.textContent = "打开系统安装界面";
    downloadButton.dataset.state = "complete";
    downloadButton.classList.remove("is-progress");
    downloadButton.disabled = false;
    downloadButton.setAttribute("aria-busy", "false");
    downloadMeta.textContent = "下载完成 · 安装需要系统确认";
    showToast("APK 下载完成，下一步由 Android 系统确认安装");
  }, 1200);
});

const bugForm = document.querySelector("#bug-form");
const titleInput = document.querySelector("#bug-title");
const descriptionInput = document.querySelector("#bug-description");
const result = document.querySelector("#form-result");
const submitButton = bugForm.querySelector("button[type='submit']");
const descriptionCounter = document.querySelector("#description-counter");

descriptionInput.addEventListener("input", () => {
  descriptionCounter.textContent = `${descriptionInput.value.length} / 1000`;
});

document.querySelectorAll("[data-delete-attachment]").forEach((button) => {
  button.addEventListener("click", () => {
    button.closest(".bug-thumb").remove();
    const count = document.querySelectorAll(".bug-thumb").length;
    document.querySelector("#attachment-count").textContent = `${count} / 5`;
    showToast("截图已移除");
  });
});

function setFieldError(field, errorElement, message) {
  field.closest(".form-field").classList.toggle("is-error", Boolean(message));
  field.setAttribute("aria-invalid", String(Boolean(message)));
  errorElement.textContent = message;
}

bugForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (bugForm.dataset.state === "complete") {
    showToast("该反馈已经提交，请勿重复提交");
    return;
  }
  const titleError = document.querySelector("#title-error");
  const descriptionError = document.querySelector("#description-error");
  const hasTitle = titleInput.value.trim().length > 0;
  const hasDescription = descriptionInput.value.trim().length > 0;

  setFieldError(titleInput, titleError, hasTitle ? "" : "请输入问题标题");
  setFieldError(descriptionInput, descriptionError, hasDescription ? "" : "请描述发生了什么以及如何复现");

  if (!hasTitle || !hasDescription) {
    result.textContent = "请完成必填内容后再提交";
    (!hasTitle ? titleInput : descriptionInput).focus();
    return;
  }

  submitButton.disabled = true;
  bugForm.setAttribute("aria-busy", "true");
  submitButton.textContent = "正在上传截图并提交…";
  result.textContent = "内容会绑定到移动审批 2.4.0";
  const isRetry = bugForm.dataset.state === "failed";

  window.setTimeout(() => {
    submitButton.disabled = false;
    bugForm.setAttribute("aria-busy", "false");
    submitButton.textContent = "提交反馈";
    if (!isRetry) {
      bugForm.dataset.state = "failed";
      result.textContent = "网络连接中断，文字与截图已保留，请重试";
      showToast("提交未完成，内容已保留");
      return;
    }
    bugForm.dataset.state = "complete";
    result.textContent = "提交成功 · Bug #BT-1042 已进入待处理";
    showToast("Bug #BT-1042 提交成功");
  }, 1200);
});

[titleInput, descriptionInput].forEach((field) => {
  field.addEventListener("input", () => {
    const errorId = field.getAttribute("aria-describedby");
    const errorElement = document.querySelector(`#${errorId}`);
    if (field.value.trim()) setFieldError(field, errorElement, "");
  });
});

const initialHash = window.location.hash.slice(1);
const initialView = panels.some((panel) => panel.dataset.view === initialHash) ? initialHash : "admin";
switchView(initialView, false);
