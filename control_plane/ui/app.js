(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const page = $("#page");
  const shell = $("#app-shell");
  const loginView = $("#login-view");
  const sidebar = $("#sidebar");
  const dialog = $("#action-dialog");
  const state = { me: null, route: "overview", plannerView: "week", conversationId: null, blogViewId: null, blogImages: [], poll: null };
  const routeLabels = {
    overview: ["WORKSPACE", "概览"], planner: ["DESKTOP SYNC", "规划"], communications: ["ACCOUNT NETWORK", "通讯"],
    blog: ["PERSONAL PUBLISHING", "博客"], inference: ["REMOTE DISPATCH", "推理任务"], settings: ["ACCOUNT PREFERENCES", "个人设置"],
    proxy: ["GLOBAL RESOURCE", "全局代理"], accounts: ["ADMINISTRATION", "账号池"], reviews: ["CONTENT REVIEW", "博客审核"]
  };
  const adminRoutes = new Set(["proxy", "accounts", "reviews"]);
  const mutationMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[char]);
  const list = value => Array.isArray(value) ? value : [];
  const formatDate = value => value ? new Intl.DateTimeFormat("zh-CN", {dateStyle:"medium", timeStyle:"short"}).format(new Date(value)) : "—";
  const initials = value => String(value || "—").trim().slice(0, 1).toUpperCase();
  const truncate = (value, length = 68) => String(value || "").length > length ? `${String(value).slice(0, length)}…` : String(value || "");
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  function getCookie(name) {
    const prefix = `${name}=`;
    const item = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith(prefix));
    return item ? decodeURIComponent(item.slice(prefix.length)) : "";
  }

  class ApiError extends Error {
    constructor(message, code, status) { super(message); this.code = code; this.status = status; }
  }

  async function api(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = {Accept: "application/json", ...(options.headers || {})};
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (mutationMethods.has(method) && path !== "/api/v1/auth/login") {
      const csrf = getCookie("cp_csrf");
      if (csrf) headers["X-CSRF-Token"] = csrf;
    }
    const response = await fetch(path, {
      method, headers, credentials: "same-origin",
      body: options.body === undefined ? undefined : JSON.stringify(options.body)
    });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const message = data?.error?.message || `请求失败 (${response.status})`;
      if (response.status === 401 && path !== "/api/v1/auth/login") showLogin();
      throw new ApiError(message, data?.error?.code || "request_failed", response.status);
    }
    return data;
  }

  function toast(message, type = "success") {
    const node = document.createElement("div");
    node.className = `toast ${type === "error" ? "error" : ""}`;
    node.textContent = message;
    $("#toast-region").append(node);
    setTimeout(() => node.remove(), 4200);
  }

  function setBusy(busy) {
    page.setAttribute("aria-busy", String(busy));
    $("#refresh-button").disabled = busy;
  }

  function fileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  function openDialog({eyebrow = "CONFIRM", title, fields = [], confirm = "确认", danger = false}) {
    $("#dialog-eyebrow").textContent = eyebrow;
    $("#dialog-title").textContent = title;
    $("#dialog-error").hidden = true;
    $("#dialog-body").innerHTML = fields.map(field => `
      <label class="field"><span>${esc(field.label)}</span>
        ${field.type === "textarea" ? `<textarea name="${esc(field.name)}" ${field.required ? "required" : ""} maxlength="${field.maxlength || 500}">${esc(field.value || "")}</textarea>` :
          field.type === "select" ? `<select name="${esc(field.name)}">${field.options.map(option => `<option value="${esc(option.value)}" ${option.value === field.value ? "selected" : ""}>${esc(option.label)}</option>`).join("")}</select>` :
          `<input name="${esc(field.name)}" type="${field.type || "text"}" value="${esc(field.value || "")}" ${field.required ? "required" : ""} ${field.minlength ? `minlength="${field.minlength}"` : ""} ${field.maxlength ? `maxlength="${field.maxlength}"` : ""}>`}
        ${field.help ? `<small>${esc(field.help)}</small>` : ""}
      </label>`).join("");
    const confirmButton = $("#dialog-confirm");
    confirmButton.textContent = confirm;
    confirmButton.className = `button ${danger ? "danger" : "primary"}`;
    dialog.showModal();
    return new Promise(resolve => {
      const finish = () => {
        dialog.removeEventListener("close", finish);
        if (dialog.returnValue !== "confirmed") return resolve(null);
        const values = Object.fromEntries(new FormData($("#dialog-form")).entries());
        resolve(values);
      };
      dialog.addEventListener("close", finish);
      confirmButton.onclick = event => {
        event.preventDefault();
        const fieldsValid = $$("input,select,textarea", $("#dialog-body")).every(control => control.reportValidity());
        if (fieldsValid) dialog.close("confirmed");
      };
    });
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme || "system";
  }

  function showLogin() {
    state.me = null;
    state.conversationId = null;
    state.blogViewId = null;
    state.blogImages = [];
    clearTimeout(state.poll);
    shell.hidden = true;
    loginView.hidden = false;
    document.title = "登录 · Control Plane";
    $("#login-password").value = "";
  }

  function showApp(me) {
    state.me = me;
    loginView.hidden = true;
    shell.hidden = false;
    const admin = me.account.role === "admin";
    $$('[data-admin]').forEach(node => node.hidden = !admin);
    $("#sidebar-name").textContent = me.profile.nickname;
    $("#sidebar-username").textContent = `@${me.account.username}`;
    $("#sidebar-avatar").textContent = initials(me.profile.nickname);
    applyTheme(me.settings.theme);
    route();
  }

  async function boot() {
    try {
      const health = await api("/api/v1/health");
      $("#setup-notice").hidden = health.initialized;
      $("#login-submit").disabled = !health.initialized;
      if (!health.initialized) return showLogin();
      try { showApp(await api("/api/v1/me")); } catch (error) { if (error.status !== 401) throw error; }
    } catch (error) {
      $("#service-state").innerHTML = "<i></i>服务异常";
      $("#login-error").textContent = error.message;
      $("#login-error").hidden = false;
    }
  }

  function pageHeader(eyebrow, title, description, actions = "") {
    return `<header class="page-head"><div><p class="eyebrow">${esc(eyebrow)}</p><h2>${esc(title)}</h2><p>${esc(description)}</p></div>${actions ? `<div class="page-actions">${actions}</div>` : ""}</header>`;
  }

  function emptyState(title, description, action = "") {
    return `<div class="empty"><div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action ? `<div class="form-actions">${action}</div>` : ""}</div></div>`;
  }

  async function route() {
    if (!state.me) return;
    clearTimeout(state.poll);
    const candidate = (location.hash || "#overview").slice(1);
    state.route = routeLabels[candidate] ? candidate : "overview";
    if (adminRoutes.has(state.route) && state.me.account.role !== "admin") state.route = "overview";
    const [eyebrow, title] = routeLabels[state.route];
    $("#page-eyebrow").textContent = eyebrow;
    $("#page-title").textContent = title;
    document.title = `${title} · Control Plane`;
    $$('[data-route]').forEach(link => link.classList.toggle("active", link.dataset.route === state.route));
    sidebar.classList.remove("open");
    setBusy(true);
    try {
      await renderers[state.route]();
      window.scrollTo(0,0);
      page.focus({preventScroll:true});
    } catch (error) {
      page.innerHTML = `${pageHeader("REQUEST ERROR", "无法加载页面", "后端返回了可恢复错误。")}
        <div class="error-state"><strong>${esc(error.message)}</strong><p>错误代码：${esc(error.code || "unknown")}</p><button class="button secondary" id="retry-page">重试</button></div>`;
      $("#retry-page")?.addEventListener("click", route);
    } finally { setBusy(false); }
  }

  async function renderOverview() {
    const [health, users, connections, tasks, planner] = await Promise.all([
      api("/api/v1/health"), api("/api/v1/users"), api("/api/v1/connections"), api("/api/v1/inference/tasks"), api("/api/v1/planner/snapshot")
    ]);
    if (state.route !== "overview") return;
    const pending = connections.connections.filter(item => item.status === "pending").length;
    const running = tasks.tasks.filter(item => ["queued","running"].includes(item.status)).length;
    const usage = health.message_usage;
    page.innerHTML = `${pageHeader("WORKSPACE", `欢迎回来，${state.me.profile.nickname}`, "这里集中显示账号自己的同步、通讯与任务状态。")}
      <section class="metric-strip">
        <div class="metric"><span>可见账号</span><strong>${users.users.length}</strong><small>账号池成员</small></div>
        <div class="metric"><span>待处理申请</span><strong>${pending}</strong><small>进入通讯处理</small></div>
        <div class="metric"><span>活动任务</span><strong>${running}</strong><small>排队或运行中</small></div>
        <div class="metric"><span>消息容量</span><strong>${Math.round(usage.bytes / 1024)} KiB</strong><small>全站上限 ${Math.round(usage.global_limit_bytes / 1024 / 1024)} MiB</small></div>
      </section>
      <div class="content-grid">
        <section class="section"><header><div><h3>当前账号</h3><p>账号名不可由个人修改；昵称与头像可在设置中维护。</p></div><span class="badge ${state.me.account.role === "admin" ? "warning" : ""}">${state.me.account.role === "admin" ? "管理员" : "普通账号"}</span></header>
          <div class="section-body"><ul class="list">
            <li><span class="avatar">${esc(initials(state.me.profile.nickname))}</span><div class="list-main"><strong>${esc(state.me.profile.nickname)}</strong><span>@${esc(state.me.account.username)}</span></div><button class="button secondary compact" data-go="settings">编辑资料</button></li>
            <li><div class="list-main"><strong>规划同步</strong><span>revision ${esc(planner.snapshot.revision || 0)} · ${planner.snapshot.received_at ? formatDate(planner.snapshot.received_at) : "尚未同步"}</span></div><button class="button secondary compact" data-go="planner">查看</button></li>
            <li><div class="list-main"><strong>推理任务</strong><span>${running ? `${running} 个任务等待电脑监控端处理` : "当前没有活动任务"}</span></div><button class="button secondary compact" data-go="inference">安排任务</button></li>
          </ul></div></section>
        <div class="section-stack">
          <div class="notice"><span class="status-dot"></span><div><strong>账号隔离已启用</strong><span>个人设置、规划、备注、博客和任务按账号目录保存。</span></div></div>
          <section class="section"><header><div><h3>快速入口</h3><p>常用操作</p></div></header><div class="section-body"><div class="form-actions"><button class="button secondary" data-go="communications">查看通讯</button><button class="button primary" data-go="inference">新建任务</button></div></div></section>
        </div>
      </div>`;
    $$('[data-go]').forEach(button => button.addEventListener("click", () => { location.hash = button.dataset.go; }));
  }

  function plannerLabel(item) { return item?.title || item?.name || item?.label || item?.text || item?.id || "未命名项目"; }
  function plannerDate(item) { return String(item?.plannedStart || item?.actualStart || item?.date || item?.day || item?.startDate || item?.scheduledDate || item?.start || "").slice(0, 10); }
  function plannerTime(item) {
    if (item?.plannedStart) return `${String(item.plannedStart).slice(11,16)} · ${Number(item.plannedMinutes || 0)} 分钟`;
    return item?.startTime || item?.time || item?.duration || "";
  }

  async function renderPlanner() {
    const {snapshot} = await api("/api/v1/planner/snapshot");
    if (state.route !== "planner") return;
    const base = new Date();
    const monday = new Date(base); monday.setHours(0,0,0,0); monday.setDate(base.getDate() - ((base.getDay() + 6) % 7));
    const days = Array.from({length:7}, (_, index) => { const date = new Date(monday); date.setDate(monday.getDate()+index); return date; });
    const goals = list(snapshot.goals), actions = list(snapshot.actions), routines = list(snapshot.routines), plans = list(snapshot.plans), records = list(snapshot.completionRecords);
    const actionNames = new Map(actions.map(item => [item.id, plannerLabel(item)]));
    const routineNames = new Map(routines.map(item => [item.id, plannerLabel(item)]));
    const planName = item => item.sourceType === "routine" || item.routineId ? (routineNames.get(item.routineId) || "已删除规划") : (actionNames.get(item.actionId) || "已删除行动");
    const localKey = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
    const plansFor = key => plans.filter(item => plannerDate(item) === key).sort((left,right)=>String(left.plannedStart||"").localeCompare(String(right.plannedStart||"")));
    const planCards = items => items.length ? items.map(item => `<article class="plan-item"><strong>${esc(planName(item))}</strong><small>${esc(plannerTime(item))}</small></article>`).join("") : `<span class="muted">无安排</span>`;
    const library = (items, empty) => items.length ? `<ul class="list">${items.slice(0,8).map(item => `<li><div class="list-main"><strong>${esc(plannerLabel(item))}</strong><small>${esc(item.status || item.category || "")}</small></div></li>`).join("")}</ul>` : `<p class="muted">${esc(empty)}</p>`;
    let board = "";
    if (state.plannerView === "day") {
      const key = localKey(base), items = plansFor(key);
      board = `<section class="day-board"><header><div><p class="eyebrow">TODAY</p><h3>${new Intl.DateTimeFormat("zh-CN",{dateStyle:"full"}).format(base)}</h3></div><span class="badge">${items.length} 项</span></header><div class="day-agenda">${planCards(items)}</div></section>`;
    } else if (state.plannerView === "month") {
      const monthStart = new Date(base.getFullYear(),base.getMonth(),1), gridStart = new Date(monthStart);
      gridStart.setDate(monthStart.getDate()-((monthStart.getDay()+6)%7));
      const monthDays=Array.from({length:42},(_,index)=>{const date=new Date(gridStart);date.setDate(gridStart.getDate()+index);return date;});
      board = `<div class="month-grid">${["一","二","三","四","五","六","日"].map(label=>`<div class="month-weekday">周${label}</div>`).join("")}${monthDays.map(day=>{const key=localKey(day),items=plansFor(key),outside=day.getMonth()!==base.getMonth();return `<section class="month-cell ${outside?"outside":""}"><header><strong>${day.getDate()}</strong><small>${items.length?`${items.length} 项`:""}</small></header>${items.slice(0,3).map(item=>`<span>${esc(planName(item))}</span>`).join("")}${items.length>3?`<small>另 ${items.length-3} 项</small>`:""}</section>`;}).join("")}</div>`;
    } else if (state.plannerView === "stats") {
      const totalMinutes=records.reduce((sum,item)=>sum+Number(item.actualMinutes||item.plannedMinutes||0),0);
      const grouped=new Map();records.forEach(item=>{const name=item.sourceName||item.actionName||item.routineName||"已删除项目";grouped.set(name,(grouped.get(name)||0)+Number(item.actualMinutes||item.plannedMinutes||0));});
      const rows=[...grouped.entries()].sort((a,b)=>b[1]-a[1]).slice(0,10);
      board=`<div class="planner-stats"><section class="metric-strip"><div class="metric"><span>完成记录</span><strong>${records.length}</strong><small>桌面端确认</small></div><div class="metric"><span>实际投入</span><strong>${Math.round(totalMinutes/60*10)/10} h</strong><small>${totalMinutes} 分钟</small></div><div class="metric"><span>目标</span><strong>${goals.length}</strong><small>${actions.length} 个行动</small></div><div class="metric"><span>日常规划</span><strong>${routines.length}</strong><small>只读统计</small></div></section><section class="section"><header><div><h3>投入排行</h3><p>按完成记录中的实际分钟聚合。</p></div></header><div class="section-body">${rows.length?rows.map(([name,minutes])=>`<div class="stat-row"><strong>${esc(name)}</strong><span>${minutes} 分钟</span></div>`).join(""):emptyState("暂无完成记录","电脑端确认安排后会同步到这里。")}</div></section></div>`;
    } else {
      board = `<div class="week-grid">${days.map(day => {const key=localKey(day);return `<section class="day-column"><header class="day-head"><span>${new Intl.DateTimeFormat("zh-CN",{weekday:"short"}).format(day)}</span><strong>${day.getMonth()+1}/${day.getDate()}</strong></header><div class="plan-stack">${planCards(plansFor(key))}</div></section>`;}).join("")}</div>`;
    }
    page.innerHTML = `${pageHeader("IROHAWALENDAR SYNC", "规划", "结构对应电脑端规划应用；网页版只读并显示最新完整快照。", `<button class="button secondary" id="planner-sync-settings">同步设置</button>`)}
      <div class="readonly-banner"><span class="badge">只读</span><div><strong>桌面端是唯一写入源</strong><span>revision ${esc(snapshot.revision || 0)} · ${snapshot.received_at ? `服务器接收于 ${formatDate(snapshot.received_at)}` : "尚未收到桌面同步"}</span></div></div>
      <div class="planner-toolbar"><div class="view-switch" role="group" aria-label="规划视图">${[["day","日"],["week","周"],["month","月"],["stats","统计"]].map(([value,label])=>`<button type="button" class="${state.plannerView===value?"active":""}" data-planner-view="${value}">${label}</button>`).join("")}</div><span class="badge">IrohaWalendar v5</span></div>
      <div class="planner-shell">
        <aside class="planner-library"><section><h3>目标</h3>${library(goals,"尚无目标")}</section><section><h3>行动</h3>${library(actions,"尚无行动")}</section><section><h3>日常规划</h3>${library(routines,"尚无日常规划")}</section></aside>
        <div class="planner-board">${board}</div>
      </div>`;
    $("#planner-sync-settings").addEventListener("click", () => { location.hash = "settings"; });
    $$('[data-planner-view]').forEach(button=>button.addEventListener("click",()=>{state.plannerView=button.dataset.plannerView;renderPlanner().catch(error=>toast(error.message,"error"));}));
  }

  function connectionActions(user) {
    const connection = user.connection;
    if (!connection || connection.status === "rejected") return `<button class="button secondary compact" data-connect="request" data-id="${user.id}">发送申请</button>`;
    if (connection.status === "connected") return `<button class="button secondary compact open-conversation" data-id="${user.id}">打开会话</button>`;
    if (connection.direction === "incoming") return `<button class="button primary compact" data-connect="accept" data-id="${user.id}">接受</button><button class="button secondary compact" data-connect="reject" data-id="${user.id}">拒绝</button>`;
    return `<button class="button secondary compact" data-connect="cancel" data-id="${user.id}">撤回申请</button>`;
  }

  async function renderCommunications() {
    const [{users}, {connections}] = await Promise.all([api("/api/v1/users"), api("/api/v1/connections")]);
    state.users = users;
    const connected = users.filter(user => user.connection?.status === "connected");
    if (state.conversationId && !users.some(user => user.id === state.conversationId)) state.conversationId = null;
    const selected = users.find(user => user.id === state.conversationId);
    let messages = [];
    if (selected?.connection?.status === "connected") messages = (await api(`/api/v1/conversations/${selected.id}/messages?after=0&limit=200`)).messages;
    if (state.route !== "communications") return;
    const mobilePeopleClass = state.conversationId ? "" : "show-people";
    page.innerHTML = `${pageHeader("ACCOUNT NETWORK", "通讯", "所有有效账号彼此可见；双方建立连接后才能交换消息。", `<button class="button secondary" id="show-account-pool">账号池</button>`)}
      <div class="communications ${mobilePeopleClass}">
        <aside class="people-pane"><header><div><strong>账号池</strong><p class="muted">${users.length} 个其他账号</p></div><span class="badge">${connections.filter(item=>item.status==="pending").length} 待处理</span></header>
          <div class="people-list">${users.length ? users.map(user => `<article class="person ${user.id === state.conversationId ? "active" : ""}">
            <span class="avatar">${esc(initials(user.nickname))}</span><button class="person-copy open-conversation" data-id="${user.id}" type="button"><strong>${esc(user.remark || user.nickname)}</strong><small>@${esc(user.username)} · ${user.connection?.status === "connected" ? "已连接" : user.connection?.status === "pending" ? (user.connection.direction === "incoming" ? "申请你" : "等待对方") : "未连接"}</small></button>
            <span class="badge ${user.connection?.status === "connected" ? "success" : user.connection?.status === "pending" ? "warning" : ""}">${user.role === "admin" ? "管理" : "用户"}</span>
          </article>`).join("") : emptyState("账号池为空","管理员尚未创建其他账号。")}</div></aside>
        <section class="conversation">${selected ? `<header class="conversation-head"><div><h3>${esc(selected.remark || selected.nickname)}</h3><p class="muted">@${esc(selected.username)} · ${esc(selected.nickname)}</p></div><div class="row-actions"><button class="button ghost compact" id="edit-remark">设置备注</button>${connectionActions(selected)}</div></header>
          ${selected.connection?.status === "connected" ? `<div class="message-feed" id="message-feed">${messages.length ? messages.map(message => `<article class="message ${message.sender_id === state.me.account.id ? "mine" : ""}"><header><strong>${message.sender_id === state.me.account.id ? "你" : esc(selected.remark || selected.nickname)}</strong><time>${formatDate(message.created_at)}</time></header><p>${esc(message.text)}</p></article>`).join("") : emptyState("开始对话","连接已建立，还没有消息。")}</div>
            <form class="composer" id="message-form"><textarea id="message-text" maxlength="4000" required placeholder="发送消息给 ${esc(selected.remark || selected.nickname)}…"></textarea><footer><button class="button primary" type="submit">发送消息</button></footer></form>` : `<div class="empty"><div><h3>建立连接后开始通讯</h3><p>申请与备注已经可以操作；未连接账号不能读取或发送消息。</p><div class="form-actions">${connectionActions(selected)}</div></div></div>`}` : emptyState("选择账号","在左侧账号池中选择用户，发送申请或打开已连接会话。")}</section>
      </div>`;

    const open = id => { state.conversationId = id; renderCommunications().catch(error => toast(error.message,"error")); };
    $$(".open-conversation").forEach(button => button.addEventListener("click", () => open(button.dataset.id)));
    $$("[data-connect]").forEach(button => button.addEventListener("click", async () => {
      const action = button.dataset.connect, id = button.dataset.id;
      button.disabled = true;
      try {
        if (action === "request") await api("/api/v1/connections/requests", {method:"POST", body:{account_id:id}});
        else await api(`/api/v1/connections/${id}/${action}`, {method:"POST", body:{}});
        toast(action === "accept" ? "连接已建立" : "申请状态已更新");
        await renderCommunications();
      } catch (error) { toast(error.message,"error"); button.disabled = false; }
    }));
    $("#show-account-pool")?.addEventListener("click", () => { state.conversationId = null; renderCommunications(); });
    $("#edit-remark")?.addEventListener("click", async () => {
      const values = await openDialog({eyebrow:"PRIVATE NOTE",title:`备注 ${selected.nickname}`,fields:[{name:"remark",label:"仅自己可见的备注",value:selected.remark,maxlength:120,help:"清空后保存可删除备注。"}],confirm:"保存备注"});
      if (!values) return;
      try { await api(`/api/v1/users/${selected.id}/remark`,{method:"PUT",body:{remark:values.remark}}); toast("备注已保存"); await renderCommunications(); } catch(error){ toast(error.message,"error"); }
    });
    $("#message-form")?.addEventListener("submit", async event => {
      event.preventDefault(); const input = $("#message-text"); const text = input.value.trim(); if (!text) return;
      try { await api(`/api/v1/conversations/${selected.id}/messages`,{method:"POST",body:{text}}); input.value=""; await renderCommunications(); } catch(error){ toast(error.message,"error"); }
    });
    const feed = $("#message-feed"); if (feed) feed.scrollTop = feed.scrollHeight;
    if (selected?.connection?.status === "connected") state.poll = setTimeout(() => { if (state.route === "communications") renderCommunications().catch(()=>{}); }, 7000);
  }

  function renderBlogPreview(manifest) {
    if (!manifest) return emptyState("尚未发布博客","使用左侧编辑器发布结构化图文，或提交自定义 HTML 等待管理员审核。 ");
    if (manifest.mode === "custom" && manifest.custom_revision) return `<div class="preview"><p class="eyebrow">CUSTOM PAGE</p><h1>${esc(manifest.title || "自定义博客")}</h1><p class="dek">自定义页面已通过审核，并在严格 CSP sandbox 中打开。</p><a class="button primary" target="_blank" rel="noopener" href="/blogs/${esc(state.blogViewId || state.me.account.id)}/custom/${esc(manifest.custom_revision)}">打开沙箱页面</a></div>`;
    return `<div class="preview"><p class="eyebrow">STRUCTURED BLOG</p><h1>${esc(manifest.title)}</h1><p class="dek">${esc(manifest.summary)}</p><article>${list(manifest.blocks).map(block => block.type === "image" ? `<figure><img src="${esc(block.src)}" alt="${esc(block.alt)}"><figcaption>${esc(block.alt)}</figcaption></figure>` : `<p>${esc(block.text)}</p>`).join("")}</article></div>`;
  }

  async function renderBlog() {
    const [{users},{reviews}] = await Promise.all([api("/api/v1/users"),api("/api/v1/blog/me/custom/reviews")]);
    const directory = [{...state.me.account, nickname:state.me.profile.nickname}, ...users.filter(user => !user.disabled)];
    if (!state.blogViewId) state.blogViewId = state.me.account.id;
    let manifest = null;
    try { manifest = (await api(`/api/v1/blogs/${state.blogViewId}`)).blog; } catch (error) { if (error.code !== "blog_not_found") throw error; }
    if (state.route !== "blog") return;
    page.innerHTML = `${pageHeader("PERSONAL PUBLISHING", "博客", "发布结构化图文；自定义网页必须经过管理员审核并在沙箱中运行。")}
      <div class="content-grid">
        <div class="section-stack">
          <section class="section"><header><div><h3>结构化博客编辑器</h3><p>文本按空行分段；图片限制为 PNG/JPEG/WebP。</p></div><span class="badge">32 MiB/账号</span></header><form class="section-body section-stack" id="structured-blog-form">
            <label class="field"><span>标题</span><input id="blog-title" maxlength="120" required value="${state.blogViewId === state.me.account.id && manifest?.mode === "structured" ? esc(manifest.title) : ""}"></label>
            <label class="field"><span>摘要</span><textarea id="blog-summary" maxlength="500" required>${state.blogViewId === state.me.account.id && manifest?.mode === "structured" ? esc(manifest.summary) : ""}</textarea></label>
            <label class="field"><span>正文</span><textarea id="blog-body" maxlength="50000" required placeholder="每个空行会创建一个文本段落。">${state.blogViewId === state.me.account.id && manifest?.mode === "structured" ? esc(list(manifest.blocks).filter(block=>block.type==="text").map(block=>block.text).join("\n\n")) : ""}</textarea></label>
            <label class="field"><span>追加图片</span><input id="blog-images" type="file" accept="image/png,image/jpeg,image/webp" multiple><small id="blog-image-count">尚未选择新图片</small></label>
            <div class="form-actions"><button class="button primary" type="submit">发布结构化博客</button></div>
          </form></section>
          <section class="section"><header><div><h3>自定义网页</h3><p>上传完整 HTML；脚本、外链、表单、iframe 与事件属性会被拒绝。</p></div><span class="badge warning">需审核</span></header><form class="section-body section-stack" id="custom-blog-form"><label class="field"><span>HTML 文件</span><input id="custom-blog-file" type="file" accept="text/html,.html" required></label><div class="form-actions"><button class="button secondary" type="submit">提交审核</button></div></form></section>
          <section class="section" id="blog-review-history"><header><div><h3>审核记录</h3><p>只显示自己的状态与管理员备注。</p></div><span class="badge">${reviews.length} 条</span></header><div class="section-body">${reviews.length?`<ul class="list">${reviews.slice(0,8).map(review=>`<li><div class="list-main"><strong>${review.status==="pending"?"等待审核":review.status==="approved"?"已批准":"已拒绝"}</strong><span>${formatDate(review.reviewed_at||review.created_at)}${review.note?` · ${esc(review.note)}`:""}</span></div><code>${esc(review.revision_id.slice(0,8))}</code></li>`).join("")}</ul>`:emptyState("暂无审核记录","提交安全的自定义 HTML 后会显示处理状态。")}</div></section>
        </div>
        <div class="section-stack"><section class="section"><header><div><h3>账号博客</h3><p>选择账号观察已发布内容。</p></div></header><div class="section-body"><select id="blog-account">${directory.map(user=>`<option value="${user.id}" ${user.id===state.blogViewId?"selected":""}>${esc(user.nickname)} (@${esc(user.username)})</option>`).join("")}</select></div></section>
          <section class="section"><header><div><h3>发布预览</h3><p>${manifest ? `更新于 ${formatDate(manifest.updated_at)}` : "该账号尚无公开博客"}</p></div></header><div class="section-body">${renderBlogPreview(manifest)}</div></section></div>
      </div>`;
    $("#blog-account").addEventListener("change", event => { state.blogViewId=event.target.value; renderBlog().catch(error=>toast(error.message,"error")); });
    $("#blog-images").addEventListener("change", async event => {
      try { state.blogImages = await Promise.all([...event.target.files].map(fileAsDataUrl)); $("#blog-image-count").textContent=`已选择 ${state.blogImages.length} 张图片`; } catch(error){ toast("无法读取图片", "error"); }
    });
    $("#structured-blog-form").addEventListener("submit", async event => {
      event.preventDefault();
      const paragraphs=$("#blog-body").value.split(/\n\s*\n/).map(item=>item.trim()).filter(Boolean);
      const blocks=[...paragraphs.map(text=>({type:"text",text})),...state.blogImages.map((data_url,index)=>({type:"image",alt:`博客图片 ${index+1}`,data_url}))];
      try { await api("/api/v1/blog/me",{method:"PUT",body:{title:$("#blog-title").value,summary:$("#blog-summary").value,blocks}}); state.blogImages=[]; state.blogViewId=state.me.account.id; toast("博客已发布"); await renderBlog(); } catch(error){ toast(error.message,"error"); }
    });
    $("#custom-blog-form").addEventListener("submit", async event => {
      event.preventDefault(); const file=$("#custom-blog-file").files[0]; if(!file)return;
      try { const html=await file.text(); await api("/api/v1/blog/me/custom",{method:"POST",body:{html}}); toast("自定义网页已提交审核"); event.target.reset(); await renderBlog(); } catch(error){ toast(error.message,"error"); }
    });
  }

  const taskLabels = {queued:"等待领取",running:"运行中",succeeded:"已完成",failed:"失败",cancelled:"已取消"};
  const taskBadge = status => status === "succeeded" ? "success" : status === "failed" ? "danger" : ["queued","running"].includes(status) ? "warning" : "";

  async function renderInference() {
    const {tasks} = await api("/api/v1/inference/tasks");
    if (state.route !== "inference") return;
    page.innerHTML = `${pageHeader("REMOTE DISPATCH", "推理任务", "服务器只负责排队与回传；电脑监控端领取任务后执行本地推理。")}
      <div class="content-grid">
        <section class="section"><header><div><h3>安排任务</h3><p>只发送指令和白名单参数，不允许路径、命令、URL 或凭据。</p></div><span class="badge">指令端</span></header>
          <form class="section-body section-stack" id="task-form"><label class="field"><span>任务指令</span><textarea id="task-instruction" maxlength="50000" required placeholder="说明目标、输入背景和期望输出格式。"></textarea></label>
            <div class="form-grid"><label class="field"><span>模型</span><input id="task-model" maxlength="120" value="local-reasoning-14b"></label><label class="field"><span>精度</span><select id="task-precision"><option>FP16</option><option>BF16</option><option>FP32</option></select></label><label class="field"><span>Temperature</span><input id="task-temperature" type="number" min="0" max="2" step="0.1" value="0.7"></label><label class="field"><span>Max tokens</span><input id="task-max-tokens" type="number" min="1" max="131072" value="2048"></label><label class="field"><span>优先级</span><select id="task-priority">${Array.from({length:10},(_,index)=>`<option value="${9-index}" ${9-index===5?"selected":""}>${9-index}</option>`).join("")}</select></label><label class="field"><span>Seed</span><input id="task-seed" type="number" placeholder="留空为自动"></label></div>
            <div class="form-actions"><button class="button primary" type="submit">加入队列</button></div></form></section>
        <div class="section-stack">${state.me.account.role === "admin" ? `<section class="section"><header><div><h3>电脑监控端</h3><p>Worker token 只显示一次。</p></div></header><form class="section-body inline-form" id="worker-form"><label class="field"><span>监控端名称</span><input id="worker-name" maxlength="80" required placeholder="Desktop inference monitor"></label><button class="button secondary" type="submit">创建令牌</button></form></section>` : ""}
          <div class="notice warning"><span class="status-dot"></span><div><strong>任务输入不可信</strong><span>电脑端仍需白名单模型、显存和执行环境；服务器不会直接运行算法。</span></div></div></div>
      </div>
      <section class="section"><header><div><h3>最近任务</h3><p>最多显示最近 200 个当前账号任务。</p></div><span class="badge">${tasks.length} 条</span></header>
        <div class="table-wrap">${tasks.length ? `<table class="data-table"><thead><tr><th>状态</th><th>指令</th><th>参数</th><th>优先级</th><th>进度</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${tasks.map(task=>`<tr><td><span class="badge ${taskBadge(task.status)}">${esc(taskLabels[task.status]||task.status)}</span></td><td>${esc(truncate(task.instruction,54))}</td><td><code>${esc(task.parameters?.model||"—")} · ${esc(task.parameters?.precision||"—")}</code></td><td>${task.priority}</td><td><progress class="progress" max="1" value="${Number(task.progress||0)}"></progress><small>${esc(task.phase_label||"")}</small></td><td>${formatDate(task.updated_at)}</td><td><div class="row-actions"><button class="button ghost compact" data-task-view="${task.id}">详情</button>${["queued","running"].includes(task.status)?`<button class="button secondary compact" data-task-cancel="${task.id}">取消</button>`:""}</div></td></tr>`).join("")}</tbody></table>` : emptyState("暂无推理任务","在上方填写指令并加入队列。")}</div></section>`;
    $("#task-form").addEventListener("submit", async event => {
      event.preventDefault(); const seed=$("#task-seed").value;
      const parameters={model:$("#task-model").value,precision:$("#task-precision").value,temperature:Number($("#task-temperature").value),max_tokens:Number($("#task-max-tokens").value)}; if(seed)parameters.seed=Number(seed);
      try { await api("/api/v1/inference/tasks",{method:"POST",body:{instruction:$("#task-instruction").value,priority:Number($("#task-priority").value),parameters}}); toast("任务已加入队列"); await renderInference(); } catch(error){ toast(error.message,"error"); }
    });
    $("#worker-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      try { const {worker}=await api("/api/v1/admin/workers",{method:"POST",body:{name:$("#worker-name").value}}); await openDialog({eyebrow:"ONE-TIME TOKEN",title:"监控端令牌",fields:[{name:"token",label:"只显示一次，请在安全位置复制",value:worker.token}],confirm:"我已复制"}); } catch(error){ toast(error.message,"error"); }
    });
    $$('[data-task-cancel]').forEach(button=>button.addEventListener("click",async()=>{try{await api(`/api/v1/inference/tasks/${button.dataset.taskCancel}/cancel`,{method:"POST",body:{}});toast("任务已取消");await renderInference();}catch(error){toast(error.message,"error");}}));
    $$('[data-task-view]').forEach(button=>button.addEventListener("click",async()=>{try{const {task}=await api(`/api/v1/inference/tasks/${button.dataset.taskView}`);await openDialog({eyebrow:"TASK DETAIL",title:taskLabels[task.status]||task.status,fields:[{name:"instruction",label:"指令",type:"textarea",value:task.instruction},{name:"result",label:"结果 / 错误",type:"textarea",value:task.result?JSON.stringify(task.result,null,2):(task.error||"尚无结果")}],confirm:"关闭"});}catch(error){toast(error.message,"error");}}));
  }

  async function renderSettings() {
    const [me,{devices}] = await Promise.all([api("/api/v1/me"),api("/api/v1/me/devices")]);
    if (state.route !== "settings") return;
    state.me=me;
    page.innerHTML = `${pageHeader("ACCOUNT PREFERENCES", "个人设置", "昵称、头像、主题和桌面同步令牌只影响当前账号。")}
      <div class="content-grid equal">
        <section class="section"><header><div><h3>公开资料</h3><p>账号名不变；昵称和头像对其他登录用户可见。</p></div></header><form class="section-body section-stack" id="profile-form"><label class="field"><span>账号名称</span><input value="${esc(me.account.username)}" disabled></label><label class="field"><span>昵称</span><input id="profile-nickname" maxlength="60" required value="${esc(me.profile.nickname)}"></label><label class="field"><span>头像</span><input id="profile-avatar" type="file" accept="image/png,image/jpeg,image/webp"><small>最多 2 MiB；留空不会删除现有头像。</small></label><div class="form-actions"><button class="button primary" type="submit">保存资料</button></div></form></section>
        <section class="section"><header><div><h3>界面偏好</h3><p>代理不属于个人设置，只有管理员可以操作全局代理。</p></div><span class="badge">账号独立</span></header><form class="section-body section-stack" id="preference-form"><label class="field"><span>主题</span><select id="setting-theme"><option value="system" ${me.settings.theme==="system"?"selected":""}>跟随系统</option><option value="light" ${me.settings.theme==="light"?"selected":""}>浅色</option><option value="dark" ${me.settings.theme==="dark"?"selected":""}>深色</option></select></label><label class="field"><span>语言</span><select id="setting-locale"><option value="zh-CN" ${me.settings.locale==="zh-CN"?"selected":""}>简体中文</option><option value="en-US" ${me.settings.locale==="en-US"?"selected":""}>English</option></select></label><div class="form-actions"><button class="button primary" type="submit">保存偏好</button></div></form></section>
      </div>
      <section class="section"><header><div><h3>桌面同步设备</h3><p>设备令牌原文只显示一次；网页只能读取规划快照。</p></div><button class="button primary compact" id="create-device">添加设备</button></header><div class="table-wrap">${devices.length?`<table class="data-table"><thead><tr><th>设备</th><th>权限</th><th>创建时间</th><th>最后使用</th><th>状态</th><th>操作</th></tr></thead><tbody>${devices.map(device=>`<tr><td>${esc(device.name)}</td><td><code>${esc(device.scope)}</code></td><td>${formatDate(device.created_at)}</td><td>${formatDate(device.last_used_at)}</td><td><span class="badge ${device.revoked_at?"danger":"success"}">${device.revoked_at?"已撤销":"有效"}</span></td><td>${device.revoked_at?"—":`<button class="button secondary compact" data-revoke-device="${device.id}">撤销</button>`}</td></tr>`).join("")}</tbody></table>`:emptyState("尚无同步设备","添加电脑端设备后，用一次性令牌上传 IrohaWalendar v5 快照。")}</div><div class="section-body"><div class="notice"><span class="status-dot"></span><div><strong>运行桌面同步适配器</strong><span>先在 IrohaWalendar 设置中开启本机 API，再创建上方设备令牌；Windows 脚本位于 <code>tools/holiday-planner-sync.ps1</code>，首次启动立即同步，之后只上传变化内容。</span></div></div></div></section>`;
    $("#profile-form").addEventListener("submit",async event=>{event.preventDefault();const file=$("#profile-avatar").files[0];try{const payload={nickname:$("#profile-nickname").value};if(file)payload.avatar_data_url=await fileAsDataUrl(file);await api("/api/v1/me/profile",{method:"PATCH",body:payload});toast("资料已保存");showApp(await api("/api/v1/me"));}catch(error){toast(error.message,"error");}});
    $("#preference-form").addEventListener("submit",async event=>{event.preventDefault();try{await api("/api/v1/me/settings",{method:"PATCH",body:{theme:$("#setting-theme").value,locale:$("#setting-locale").value}});applyTheme($("#setting-theme").value);toast("偏好已保存");state.me=await api("/api/v1/me");}catch(error){toast(error.message,"error");}});
    $("#create-device").addEventListener("click",async()=>{const values=await openDialog({eyebrow:"SYNC DEVICE",title:"添加桌面同步设备",fields:[{name:"name",label:"设备名称",required:true,maxlength:80,value:"IrohaWalendar Desktop"}],confirm:"创建令牌"});if(!values)return;try{const {device}=await api("/api/v1/me/devices",{method:"POST",body:{name:values.name,scope:"planner_sync"}});await openDialog({eyebrow:"ONE-TIME TOKEN",title:"设备令牌",fields:[{name:"token",label:"只显示一次，请复制到电脑端",value:device.token}],confirm:"我已复制"});await renderSettings();}catch(error){toast(error.message,"error");}});
    $$('[data-revoke-device]').forEach(button=>button.addEventListener("click",async()=>{const values=await openDialog({eyebrow:"DESTRUCTIVE ACTION",title:"撤销同步设备",fields:[],confirm:"确认撤销",danger:true});if(!values)return;try{await api(`/api/v1/me/devices/${button.dataset.revokeDevice}`,{method:"DELETE"});toast("设备令牌已撤销");await renderSettings();}catch(error){toast(error.message,"error");}}));
  }

  async function renderProxy() {
    const {proxy}=await api("/api/v1/proxy/status");
    if (state.route !== "proxy") return;
    page.innerHTML=`${pageHeader("GLOBAL RESOURCE","全局代理","只有管理员可以操作。所有明确使用 127.0.0.1:7890 的服务器进程共享当前模式和节点。",`<button class="button secondary" id="proxy-refresh">刷新订阅</button>`)}
      <section class="metric-strip"><div class="metric"><span>控制器</span><strong>${proxy.status==="online"?"在线":"离线"}</strong><small>Unix socket</small></div><div class="metric"><span>当前模式</span><strong>${esc(proxy.mode)}</strong><small>服务器全局</small></div><div class="metric"><span>当前节点</span><strong>${esc(proxy.selection||"—")}</strong><small>AUTO 实际 ${esc(proxy.auto_selection||"—")}</small></div><div class="metric"><span>可用节点</span><strong>${list(proxy.nodes).filter(node=>node.alive).length}</strong><small>共 ${list(proxy.nodes).length} 个</small></div></section>
      <div class="content-grid equal"><section class="section"><header><div><h3>全局模式</h3><p>更改会影响所有使用本机 Mihomo 代理端点的进程。</p></div><span class="badge warning">管理员</span></header><form class="section-body section-stack" id="proxy-mode-form">${[["rule","Rule","按规则分流，推荐"],["global","Global","全部经代理"],["direct","Direct","全部直连"]].map(([value,label,help])=>`<label class="list"><span><input type="radio" name="mode" value="${value}" ${proxy.mode===value?"checked":""}> <strong>${label}</strong> <small>${help}</small></span></label>`).join("")}<div class="form-actions"><button class="button primary" type="submit">应用全局模式</button></div></form></section>
        <section class="section"><header><div><h3>GitHub 节点</h3><p>AUTO 自动选择低延迟节点，也可由管理员手动指定。</p></div></header><form class="section-body section-stack" id="proxy-node-form"><label class="field"><span>节点</span><select id="proxy-node"><option value="AUTO" ${proxy.selection==="AUTO"?"selected":""}>AUTO</option>${list(proxy.nodes).filter(node=>node.name!=="AUTO").map(node=>`<option value="${esc(node.name)}" ${proxy.selection===node.name?"selected":""}>${esc(node.name)} · ${node.alive?`${node.latency_ms??"—"} ms`:"不可用"}</option>`).join("")}</select></label><div class="form-actions"><button class="button primary" type="submit">应用节点</button></div></form></section></div>
      <div class="notice warning"><span class="status-dot"></span><div><strong>代理不会自动接管所有程序</strong><span>所有用户可以共享代理能力，但具体程序仍需显式使用 127.0.0.1:7890 或对应代理配置。</span></div></div>`;
    $("#proxy-mode-form").addEventListener("submit",async event=>{event.preventDefault();const mode=new FormData(event.target).get("mode");try{await api("/api/v1/proxy/mode",{method:"POST",body:{mode}});toast("全局模式已更新");await sleep(350);await renderProxy();}catch(error){toast(error.message,"error");}});
    $("#proxy-node-form").addEventListener("submit",async event=>{event.preventDefault();try{await api("/api/v1/proxy/selection",{method:"POST",body:{name:$("#proxy-node").value}});toast("代理节点已更新");await sleep(350);await renderProxy();}catch(error){toast(error.message,"error");}});
    $("#proxy-refresh").addEventListener("click",async()=>{try{await api("/api/v1/proxy/refresh",{method:"POST",body:{}});toast("已请求刷新订阅");await sleep(800);await renderProxy();}catch(error){toast(error.message,"error");}});
  }

  async function renderAccounts() {
    const {accounts}=await api("/api/v1/admin/accounts");
    if (state.route !== "accounts") return;
    page.innerHTML=`${pageHeader("ADMINISTRATION","账号池","管理员创建、停用、恢复、调整角色或重置密码；密码永远不可读回。")}
      <section class="section"><header><div><h3>创建账号</h3><p>新账号默认拥有独立目录、资料、设置、规划、博客和会话空间。</p></div><span class="badge warning">管理员</span></header><form class="section-body form-grid" id="create-account-form"><label class="field"><span>账号名称</span><input id="new-username" required minlength="3" maxlength="32" placeholder="alice"></label><label class="field"><span>初始密码</span><input id="new-password" type="password" required minlength="12" maxlength="256" autocomplete="new-password"></label><label class="field"><span>角色</span><select id="new-role"><option value="user">普通账号</option><option value="admin">管理员</option></select></label><div class="form-actions"><button class="button primary" type="submit">创建账号</button></div></form></section>
      <section class="section"><header><div><h3>全部账号</h3><p>${accounts.length} 个账号；最后一个有效管理员受保护。</p></div></header><div class="table-wrap"><table class="data-table"><thead><tr><th>账号</th><th>昵称</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead><tbody>${accounts.map(account=>`<tr><td><code>@${esc(account.username)}</code></td><td>${esc(account.nickname)}</td><td><span class="badge ${account.role==="admin"?"warning":""}">${account.role==="admin"?"管理员":"普通账号"}</span></td><td><span class="badge ${account.disabled?"danger":"success"}">${account.disabled?"已停用":"有效"}</span></td><td>${formatDate(account.created_at)}</td><td><div class="row-actions"><button class="button ghost compact" data-account-role="${account.id}" data-role="${account.role}">${account.role==="admin"?"降为用户":"设为管理员"}</button><button class="button secondary compact" data-account-toggle="${account.id}" data-disabled="${account.disabled}">${account.disabled?"恢复":"停用"}</button><button class="button ghost compact" data-account-password="${account.id}" data-name="${esc(account.username)}">重置密码</button></div></td></tr>`).join("")}</tbody></table></div></section>`;
    $("#create-account-form").addEventListener("submit",async event=>{event.preventDefault();try{await api("/api/v1/admin/accounts",{method:"POST",body:{username:$("#new-username").value,password:$("#new-password").value,role:$("#new-role").value}});toast("账号已创建");await renderAccounts();}catch(error){toast(error.message,"error");}});
    $$('[data-account-role]').forEach(button=>button.addEventListener("click",async()=>{const role=button.dataset.role==="admin"?"user":"admin";const values=await openDialog({eyebrow:"ROLE CHANGE",title:"确认变更账号角色",fields:[],confirm:"确认变更",danger:role==="user"});if(!values)return;try{await api(`/api/v1/admin/accounts/${button.dataset.accountRole}`,{method:"PATCH",body:{role}});toast("角色已更新");await renderAccounts();}catch(error){toast(error.message,"error");}}));
    $$('[data-account-toggle]').forEach(button=>button.addEventListener("click",async()=>{const disabled=button.dataset.disabled==="false";const values=await openDialog({eyebrow:"ACCOUNT STATUS",title:disabled?"停用账号":"恢复账号",fields:[],confirm:disabled?"确认停用":"确认恢复",danger:disabled});if(!values)return;try{await api(`/api/v1/admin/accounts/${button.dataset.accountToggle}`,{method:"PATCH",body:{disabled}});toast("账号状态已更新");await renderAccounts();}catch(error){toast(error.message,"error");}}));
    $$('[data-account-password]').forEach(button=>button.addEventListener("click",async()=>{const values=await openDialog({eyebrow:"PASSWORD RESET",title:`重置 @${button.dataset.name} 的密码`,fields:[{name:"password",label:"新密码",type:"password",required:true,minlength:12,maxlength:256,help:"保存后会立即清空该账号所有登录会话。"}],confirm:"重置密码",danger:true});if(!values)return;try{await api(`/api/v1/admin/accounts/${button.dataset.accountPassword}/password`,{method:"POST",body:{password:values.password}});toast("密码已重置");}catch(error){toast(error.message,"error");}}));
  }

  async function renderReviews() {
    const [{reviews},{users}] = await Promise.all([api("/api/v1/admin/blog-reviews"),api("/api/v1/users")]);
    if (state.route !== "reviews") return;
    const names=new Map(users.map(user=>[user.id,user.nickname])); names.set(state.me.account.id,state.me.profile.nickname);
    page.innerHTML=`${pageHeader("CONTENT REVIEW","博客审核","自定义 HTML 必须同时通过自动安全校验和管理员决定。")}
      <div class="notice warning"><span class="status-dot"></span><div><strong>批准不等于放宽沙箱</strong><span>通过后仍禁止脚本、网络、表单、iframe 和同源权限。</span></div></div>
      <section class="section"><header><div><h3>待审核版本</h3><p>${reviews.length} 个版本等待处理。</p></div><span class="badge ${reviews.length?"warning":"success"}">${reviews.length?"待处理":"已清空"}</span></header>${reviews.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>账号</th><th>版本</th><th>提交时间</th><th>操作</th></tr></thead><tbody>${reviews.map(review=>`<tr><td>${esc(names.get(review.account_id)||review.account_id)}</td><td><code>${esc(review.revision_id)}</code></td><td>${formatDate(review.created_at)}</td><td><div class="row-actions"><button class="button primary compact" data-review="approved" data-account="${review.account_id}" data-revision="${review.revision_id}">批准</button><button class="button secondary compact" data-review="rejected" data-account="${review.account_id}" data-revision="${review.revision_id}">拒绝</button></div></td></tr>`).join("")}</tbody></table></div>`:emptyState("没有待审核内容","用户提交自定义 HTML 后会出现在这里。")}</section>`;
    $$('[data-review]').forEach(button=>button.addEventListener("click",async()=>{const decision=button.dataset.review;const values=await openDialog({eyebrow:"CONTENT REVIEW",title:decision==="approved"?"批准自定义网页":"拒绝自定义网页",fields:[{name:"note",label:"审核备注",type:"textarea",maxlength:500,required:decision==="rejected"}],confirm:decision==="approved"?"确认批准":"确认拒绝",danger:decision==="rejected"});if(!values)return;try{await api(`/api/v1/admin/blog-reviews/${button.dataset.account}/${button.dataset.revision}`,{method:"POST",body:{decision,note:values.note||""}});toast("审核结果已保存");await renderReviews();}catch(error){toast(error.message,"error");}}));
  }

  const renderers={overview:renderOverview,planner:renderPlanner,communications:renderCommunications,blog:renderBlog,inference:renderInference,settings:renderSettings,proxy:renderProxy,accounts:renderAccounts,reviews:renderReviews};

  $("#login-form").addEventListener("submit",async event=>{event.preventDefault();const errorNode=$("#login-error"),button=$("#login-submit");errorNode.hidden=true;button.disabled=true;button.textContent="正在验证…";try{await api("/api/v1/auth/login",{method:"POST",body:{username:$("#login-username").value,password:$("#login-password").value}});showApp(await api("/api/v1/me"));}catch(error){errorNode.textContent=error.message;errorNode.hidden=false;}finally{button.disabled=false;button.textContent="进入管理页面";}});
  $("#toggle-password").addEventListener("click",event=>{const input=$("#login-password");input.type=input.type==="password"?"text":"password";event.currentTarget.textContent=input.type==="password"?"显示":"隐藏";});
  $("#logout-button").addEventListener("click",async()=>{try{await api("/api/v1/auth/logout",{method:"POST",body:{}});}catch(error){}showLogin();});
  $("#menu-toggle").addEventListener("click",()=>sidebar.classList.add("open"));
  $("#sidebar-close").addEventListener("click",()=>sidebar.classList.remove("open"));
  $("#sidebar-scrim").addEventListener("click",()=>sidebar.classList.remove("open"));
  $("#refresh-button").addEventListener("click",route);
  window.addEventListener("hashchange",route);
  window.addEventListener("keydown",event=>{if(event.key==="Escape")sidebar.classList.remove("open");});
  boot();
})();
