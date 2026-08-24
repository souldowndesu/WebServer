(function () {
  "use strict";

  var state = { data: null, loading: false, pendingMode: null, filter: "", toastTimer: null };
  var byId = function (id) { return document.getElementById(id); };
  var elements = {
    service: byId("service-state"), serviceText: byId("service-state-text"),
    metricMode: byId("metric-mode"), metricSelection: byId("metric-selection"), metricAuto: byId("metric-auto"),
    metricNodes: byId("metric-nodes"), metricLatency: byId("metric-latency"),
    providerUpdated: byId("provider-updated"), refreshPage: byId("refresh-page"), refreshProvider: byId("refresh-provider"),
    nodeSearch: byId("node-search"), nodeList: byId("node-list"), tableFrame: byId("table-frame"),
    empty: byId("empty-state"), visibleCount: byId("visible-count"), lastChecked: byId("last-checked"),
    autoRow: byId("auto-row"), autoDescription: byId("auto-description"), selectAuto: byId("select-auto"),
    modeSaved: byId("mode-saved"), errorBanner: byId("error-banner"), errorMessage: byId("error-message"),
    retry: byId("retry"), toast: byId("toast"), dialog: byId("mode-dialog"), dialogCopy: byId("dialog-copy"),
    confirmMode: byId("confirm-mode")
  };

  var labels = { rule: "规则", global: "全局", direct: "直连" };

  function escapeText(value) { return String(value == null ? "" : value); }

  async function api(path, options) {
    var config = options || {};
    var response = await fetch(path, {
      method: config.method || "GET",
      headers: config.body ? { "Content-Type": "application/json" } : {},
      body: config.body ? JSON.stringify(config.body) : undefined,
      cache: "no-store"
    });
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      var error = new Error(payload.error || "request_failed");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function setBusy(button, busy) {
    button.disabled = busy;
    button.dataset.loading = busy ? "true" : "false";
  }

  function showToast(text) {
    window.clearTimeout(state.toastTimer);
    elements.toast.textContent = text;
    elements.toast.hidden = false;
    state.toastTimer = window.setTimeout(function () { elements.toast.hidden = true; }, 2600);
  }

  function showError(message) {
    elements.service.dataset.state = "error";
    elements.serviceText.textContent = "连接失败";
    elements.errorMessage.textContent = message || "请检查代理控制服务是否正在运行。";
    elements.errorBanner.hidden = false;
  }

  function hideError() { elements.errorBanner.hidden = true; }

  function formatTime(value) {
    if (!value) return "尚无记录";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return "时间未知";
    return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  }

  function latencySpeed(value) {
    if (!value) return "unknown";
    if (value < 180) return "fast";
    if (value < 450) return "medium";
    return "slow";
  }

  function renderModes(mode) {
    document.querySelectorAll("[data-mode]").forEach(function (button) {
      var selected = button.dataset.mode === mode;
      button.setAttribute("aria-checked", selected ? "true" : "false");
      button.disabled = state.loading;
    });
  }

  function makeCell(className, text) {
    var cell = document.createElement("td");
    var span = document.createElement("span");
    span.className = className;
    span.textContent = escapeText(text);
    cell.appendChild(span);
    return cell;
  }

  function renderNodes() {
    if (!state.data) return;
    var query = state.filter.trim().toLocaleLowerCase("zh-CN");
    var nodes = state.data.nodes.filter(function (node) {
      return !query || node.name.toLocaleLowerCase("zh-CN").includes(query) || node.type.toLocaleLowerCase("zh-CN").includes(query);
    });
    elements.nodeList.replaceChildren();
    nodes.forEach(function (node) {
      var row = document.createElement("tr");
      var selected = state.data.selection === node.name;
      row.dataset.selected = selected ? "true" : "false";
      row.appendChild(makeCell("node-name", node.name));
      row.appendChild(makeCell("node-type", node.type));

      var statusCell = document.createElement("td");
      var status = document.createElement("span");
      status.className = "node-status";
      status.dataset.state = node.alive ? "alive" : "down";
      status.textContent = node.alive ? "可用" : "不可用";
      statusCell.appendChild(status);
      row.appendChild(statusCell);

      var latencyCell = document.createElement("td");
      var latency = document.createElement("span");
      latency.className = "latency";
      latency.dataset.speed = latencySpeed(node.latency_ms);
      latency.textContent = node.latency_ms ? node.latency_ms + " ms" : "未测";
      latencyCell.appendChild(latency);
      row.appendChild(latencyCell);

      var actionCell = document.createElement("td");
      var action = document.createElement("button");
      action.className = "select-button";
      action.type = "button";
      action.textContent = selected ? "已选择" : "选择";
      action.setAttribute("aria-pressed", selected ? "true" : "false");
      action.disabled = state.loading || selected;
      action.addEventListener("click", function () { selectNode(node.name, action); });
      actionCell.appendChild(action);
      row.appendChild(actionCell);
      elements.nodeList.appendChild(row);
    });

    var empty = nodes.length === 0;
    elements.empty.hidden = !empty;
    elements.nodeList.hidden = empty;
    elements.visibleCount.textContent = query ? "显示 " + nodes.length + " / " + state.data.nodes.length + " 个节点" : "共 " + nodes.length + " 个节点";
  }

  function render(data) {
    state.data = data;
    elements.service.dataset.state = "online";
    elements.serviceText.textContent = "运行正常";
    elements.metricMode.textContent = labels[data.mode] || "未知";
    elements.metricSelection.textContent = data.selection === "AUTO" ? "AUTO" : data.selection || "未选择";
    elements.metricAuto.textContent = data.auto_selection ? "当前线路：" + data.auto_selection : "等待自动选择";
    elements.metricNodes.textContent = String(data.nodes.filter(function (node) { return node.alive; }).length);
    var measured = data.nodes.filter(function (node) { return node.latency_ms; });
    var best = measured.length ? Math.min.apply(null, measured.map(function (node) { return node.latency_ms; })) : null;
    elements.metricLatency.textContent = best ? "最低延迟 " + best + " ms" : "尚未获得延迟";
    elements.providerUpdated.textContent = formatTime(data.provider_updated_at);
    elements.lastChecked.textContent = "检查于 " + formatTime(data.checked_at);
    elements.autoDescription.textContent = data.auto_selection ? "当前自动线路：" + data.auto_selection : "根据延迟自动选择当前线路";

    var autoSelected = data.selection === "AUTO";
    elements.autoRow.dataset.selected = autoSelected ? "true" : "false";
    elements.selectAuto.setAttribute("aria-pressed", autoSelected ? "true" : "false");
    elements.selectAuto.textContent = autoSelected ? "已选择" : "选择";
    elements.selectAuto.disabled = state.loading || autoSelected;
    elements.tableFrame.setAttribute("aria-busy", "false");
    renderModes(data.mode);
    renderNodes();
    hideError();
  }

  async function loadStatus(options) {
    if (state.loading) return;
    state.loading = true;
    setBusy(elements.refreshPage, true);
    try {
      var data = await api("/api/status");
      render(data);
      if (options && options.toast) showToast(options.toast);
    } catch (error) {
      showError(error.message === "controller_unavailable" ? "Mihomo 控制接口暂时不可用。" : "控制页无法读取代理状态。请稍后重试。");
    } finally {
      state.loading = false;
      setBusy(elements.refreshPage, false);
      if (state.data) {
        renderModes(state.data.mode);
        elements.selectAuto.disabled = state.data.selection === "AUTO";
        renderNodes();
      }
    }
  }

  async function changeMode(mode) {
    state.loading = true;
    elements.modeSaved.textContent = "保存中…";
    renderModes(state.data ? state.data.mode : "");
    try {
      await api("/api/mode", { method: "POST", body: { mode: mode } });
      elements.modeSaved.textContent = "已保存";
      state.loading = false;
      await loadStatus({ toast: "模式已切换为" + labels[mode] });
    } catch (error) {
      elements.modeSaved.textContent = "保存失败";
      showError("代理模式切换失败，原有设置未确认改变。");
    } finally {
      state.loading = false;
      window.setTimeout(function () { elements.modeSaved.textContent = ""; }, 2200);
    }
  }

  function requestMode(mode) {
    if (!state.data || mode === state.data.mode || state.loading) return;
    if (mode === "rule") { changeMode(mode); return; }
    state.pendingMode = mode;
    elements.dialogCopy.textContent = mode === "global"
      ? "全局模式会让所有显式使用 7890 端口的流量通过代理。确认继续吗？"
      : "直连模式会暂时绕过代理，GitHub 连接可能再次不稳定。确认继续吗？";
    if (typeof elements.dialog.showModal === "function") elements.dialog.showModal();
    else if (window.confirm(elements.dialogCopy.textContent)) changeMode(mode);
  }

  async function selectNode(name, button) {
    if (state.loading) return;
    state.loading = true;
    if (button) button.disabled = true;
    try {
      await api("/api/selection", { method: "POST", body: { name: name } });
      state.loading = false;
      await loadStatus({ toast: name === "AUTO" ? "已恢复自动选点" : "节点已切换" });
    } catch (error) {
      showError("节点切换失败，请刷新状态后重试。");
    } finally {
      state.loading = false;
    }
  }

  async function refreshProvider() {
    if (state.loading) return;
    state.loading = true;
    setBusy(elements.refreshProvider, true);
    try {
      await api("/api/refresh", { method: "POST", body: {} });
      state.loading = false;
      await loadStatus({ toast: "订阅已更新" });
    } catch (error) {
      showError("订阅更新失败，现有节点仍可继续使用。");
    } finally {
      state.loading = false;
      setBusy(elements.refreshProvider, false);
    }
  }

  document.querySelectorAll("[data-mode]").forEach(function (button) {
    button.addEventListener("click", function () { requestMode(button.dataset.mode); });
  });
  elements.refreshPage.addEventListener("click", function () { loadStatus({ toast: "状态已刷新" }); });
  elements.refreshProvider.addEventListener("click", refreshProvider);
  elements.selectAuto.addEventListener("click", function () { selectNode("AUTO", elements.selectAuto); });
  elements.retry.addEventListener("click", function () { loadStatus(); });
  elements.nodeSearch.addEventListener("input", function () { state.filter = elements.nodeSearch.value; renderNodes(); });
  elements.dialog.addEventListener("close", function () {
    if (elements.dialog.returnValue === "confirm" && state.pendingMode) changeMode(state.pendingMode);
    state.pendingMode = null;
  });

  loadStatus();
  window.setInterval(function () { if (!document.hidden && !state.loading) loadStatus(); }, 15000);
}());
