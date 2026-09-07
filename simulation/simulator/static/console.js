"use strict";

(() => {
  const API = "/console/api";
  const SELECTED_RUN_KEY = "shopsteward.console.selectedRun";
  const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER;
  const PRESETS = {
    standard: { cash: "1000.00", stock: 20, demand: 60 },
    "cash-tight": { cash: "500.00", stock: 20, demand: 60 },
    "well-stocked": { cash: "1000.00", stock: 100, demand: 60 },
  };

  const ERROR_GUIDANCE = {
    STALE_SEQUENCE: "场景已被其他操作更新。控制台已刷新当前源序号，请核对后重新提交。",
    SEQUENCE_CONFLICT: "场景已被其他操作更新。控制台已刷新当前源序号，请核对后重新提交。",
    SOURCE_CHANGED: "场景已被其他操作更新。控制台已刷新当前源序号，请核对后重新提交。",
    SCENARIO_MODE_MISMATCH: "此操作不适用于当前场景。SC01 只能推进固定剧本，SANDBOX 使用业务触发表单。",
    INSUFFICIENT_STOCK: "现货不足。请降低销售数量，或等待已批准采购到货。",
    EXCESS_RECEIPT: "到货数量超过订单剩余数量，请按订单的剩余数量填写。",
    RECEIPT_QUANTITY_INVALID: "到货数量无效，请填写不超过订单剩余数量的正整数，或留空收取全部。",
    ORDER_NOT_FOUND: "该订单不属于当前场景或已不存在，请刷新订单列表。",
    SCENARIO_FINISHED: "SC01 固定剧本已执行完毕，可创建新场景继续演示。",
    SCENARIO_STEP_BLOCKED: "下一步的业务前置尚未满足，请检查待收订单和模拟时间。",
    HORIZON_EXCEEDED: "本次操作会越过活动期，场景未发生变化。",
    SCENARIO_HORIZON_EXCEEDED: "本次操作会越过活动期，场景未发生变化。",
    INVALID_CURSOR: "分页位置已经失效，请刷新后重新读取。",
    CONSOLE_LOCAL_ONLY: "控制台仅接受本机同源访问，请从模拟器提供的 /console/ 页面操作。",
    VALIDATION_ERROR: "输入未通过服务校验，请检查数量、金额和时间范围。",
  };

  const state = {
    status: null,
    runs: [],
    nextCursor: null,
    selectedRunId: null,
    detail: null,
    events: [],
    eventAfter: 0,
    eventHasMore: false,
    eventSourceHead: 0,
    selectionEpoch: 0,
    selectionController: null,
    pendingRetry: null,
    activeWrites: new Set(),
    listLoading: false,
  };

  const $ = (id) => document.getElementById(id);

  class ApiError extends Error {
    constructor(message, { code = "REQUEST_FAILED", status = 0, uncertain = false, payload = null } = {}) {
      super(message);
      this.name = "ApiError";
      this.code = code;
      this.status = status;
      this.uncertain = uncertain;
      this.payload = payload;
    }
  }

  function makeElement(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function replaceChildren(id, children) {
    const target = $(id);
    target.replaceChildren(...children);
  }

  function asInteger(raw, label, { min = 0, max = MAX_SAFE_INTEGER } = {}) {
    const value = typeof raw === "number" ? raw : Number(String(raw).trim());
    if (!Number.isSafeInteger(value) || value < min || value > max) {
      throw new Error(`${label}必须是 ${min} 到 ${max} 之间的整数。`);
    }
    return value;
  }

  function yuanToMinor(raw, label) {
    const value = String(raw).trim();
    if (!/^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(value)) {
      throw new Error(`${label}须为非负元金额，最多两位小数。`);
    }
    const [yuan, decimal = ""] = value.split(".");
    const minor = Number(yuan) * 100 + Number(decimal.padEnd(2, "0"));
    if (!Number.isSafeInteger(minor)) throw new Error(`${label}金额过大。`);
    return minor;
  }

  function minorToYuan(raw) {
    const value = Number(raw);
    if (!Number.isFinite(value)) return "—";
    return new Intl.NumberFormat("zh-CN", {
      style: "currency",
      currency: "CNY",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value / 100);
  }

  function formatNumber(raw) {
    const value = Number(raw);
    return Number.isFinite(value) ? new Intl.NumberFormat("zh-CN").format(value) : "—";
  }

  function formatDateTime(raw, { compact = false } = {}) {
    if (!raw) return "—";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return String(raw);
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: compact ? undefined : "2-digit",
      hour12: false,
    }).format(date);
  }

  function shorten(value, length = 16) {
    const text = String(value || "");
    if (text.length <= length) return text;
    const side = Math.max(4, Math.floor((length - 1) / 2));
    return `${text.slice(0, side)}…${text.slice(-side)}`;
  }

  function selectedSequence() {
    requireLoadedRun();
    const sequence = Number(state.detail?.last_sequence);
    if (!Number.isSafeInteger(sequence) || sequence < 0) {
      throw new Error("当前源序号尚未加载，请先刷新场景。");
    }
    return sequence;
  }

  function requireLoadedRun(expectedScenario) {
    const runId = state.detail?.scenario_run_id;
    if (!runId || runId !== state.selectedRunId) {
      throw new ApiError("场景详情仍在加载，请等待当前源状态显示后再操作。", { code: "RUN_NOT_READY" });
    }
    if (expectedScenario && state.detail?.scenario !== expectedScenario) {
      throw new ApiError("当前场景不支持此操作。", { code: "SCENARIO_MODE_MISMATCH" });
    }
    return runId;
  }

  function getStock(detail = state.detail) {
    const stocks = detail?.state?.stocks;
    return Array.isArray(stocks) && stocks.length ? stocks[0] : {};
  }

  async function readResponse(response) {
    const type = response.headers.get("content-type") || "";
    if (response.status === 204) return null;
    if (type.includes("application/json")) return response.json();
    const text = await response.text();
    return text ? { detail: text } : null;
  }

  function errorInfo(payload, status) {
    const detail = payload?.detail ?? payload?.error ?? payload;
    if (typeof detail === "string") return { code: `HTTP_${status}`, message: detail };
    if (Array.isArray(detail)) {
      return {
        code: "VALIDATION_ERROR",
        message: detail.map((item) => item?.msg || String(item)).join("；"),
      };
    }
    if (detail && typeof detail === "object") {
      return {
        code: detail.code || payload?.code || `HTTP_${status}`,
        message: detail.message || detail.reason || payload?.message || `请求返回 HTTP ${status}`,
      };
    }
    return { code: `HTTP_${status}`, message: `请求返回 HTTP ${status}` };
  }

  async function getJson(path, { signal } = {}) {
    let response;
    try {
      response = await fetch(`${API}${path}`, {
        method: "GET",
        headers: { Accept: "application/json" },
        signal,
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new ApiError("无法连接本地控制台服务。请确认模拟器仍在运行。", { code: "NETWORK_ERROR" });
    }
    const payload = await readResponse(response);
    if (!response.ok) {
      const info = errorInfo(payload, response.status);
      throw new ApiError(info.message, { ...info, status: response.status, payload });
    }
    return payload;
  }

  function newAttempt(path, body, label, onSuccess) {
    return {
      path,
      body: structuredClone(body),
      label,
      key: crypto.randomUUID(),
      onSuccess,
    };
  }

  async function sendAttempt(attempt) {
    let response;
    try {
      response = await fetch(`${API}${attempt.path}`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Simulator-Console": "1",
          "Idempotency-Key": attempt.key,
        },
        body: JSON.stringify(attempt.body),
      });
    } catch (error) {
      throw new ApiError("连接在确认写入结果前中断。为避免重复写入，请使用原请求重试。", {
        code: "WRITE_RESULT_UNKNOWN",
        uncertain: true,
      });
    }

    let payload;
    try {
      payload = await readResponse(response);
    } catch (error) {
      throw new ApiError("服务已响应，但无法确认写入结果。请使用原请求重试。", {
        code: "WRITE_RESULT_UNKNOWN",
        status: response.status,
        uncertain: true,
      });
    }
    if (!response.ok) {
      const info = errorInfo(payload, response.status);
      const uncertain = response.status >= 500;
      throw new ApiError(
        uncertain ? `${info.message} 写入结果可能未知，请使用原请求重试。` : info.message,
        { ...info, status: response.status, uncertain, payload },
      );
    }
    return payload;
  }

  async function postJson(path, body, label, onSuccess) {
    if (state.pendingRetry) {
      showAlert("仍有结果未知的写入", "请先使用原请求重试，确认结果后再提交新的写入。", { retry: true });
      throw new ApiError("存在待确认写入。", { code: "PENDING_RETRY" });
    }
    const attempt = newAttempt(path, body, label, onSuccess);
    return executeAttempt(attempt);
  }

  async function executeAttempt(attempt) {
    const writeToken = attempt.key;
    if (state.activeWrites.has(writeToken)) return null;
    state.activeWrites.add(writeToken);
    updateWriteControls();
    let writeConfirmed = false;
    try {
      const payload = await sendAttempt(attempt);
      writeConfirmed = true;
      if (state.pendingRetry?.key === attempt.key) state.pendingRetry = null;
      hideAlert();
      if (attempt.onSuccess) await attempt.onSuccess(payload);
      return payload;
    } catch (error) {
      if (writeConfirmed) {
        showApiError(error, `${attempt.label}已确认，但后续读取未完成`);
      } else if (error instanceof ApiError && error.uncertain) {
        state.pendingRetry = attempt;
        showPendingRetryAlert(error);
      } else if (error instanceof ApiError && [409, 412].includes(error.status)) {
        if (state.pendingRetry?.key === attempt.key) state.pendingRetry = null;
        showApiError(error, `${attempt.label}未执行`);
        await refreshSelected({ quiet: true });
      } else {
        if (state.pendingRetry?.key === attempt.key) state.pendingRetry = null;
        showApiError(error, `${attempt.label}未执行`);
      }
      throw error;
    } finally {
      state.activeWrites.delete(writeToken);
      updateWriteControls();
    }
  }

  function showAlert(title, message, { retry = false } = {}) {
    $("global-alert-title").textContent = title;
    $("global-alert-message").textContent = message;
    $("retry-write").hidden = !retry;
    $("dismiss-alert").hidden = retry;
    $("global-alert").hidden = false;
  }

  function hideAlert({ force = false } = {}) {
    if (state.pendingRetry && !force) return;
    $("global-alert").hidden = true;
  }

  function showPendingRetryAlert(error) {
    const attempt = state.pendingRetry;
    if (!attempt) return;
    const reason = error
      ? `${error.code} · ${error.message}`
      : "写入结果仍未确认。";
    showAlert(
      `${attempt.label}的结果尚未确认`,
      `${reason} 本次幂等键和请求内容已保留，不会在重试时生成新键。`,
      { retry: true },
    );
  }

  function showApiError(error, title = "请求未完成") {
    const code = error?.code || "REQUEST_FAILED";
    const guidance = ERROR_GUIDANCE[code];
    const message = guidance || error?.message || "发生未知错误，请刷新后重试。";
    if (state.pendingRetry) {
      toast(`${title}：${code} · ${message}`, { error: true });
      showPendingRetryAlert();
      return;
    }
    showAlert(title, `${code} · ${message}`);
  }

  function toast(message, { error = false } = {}) {
    const node = makeElement("div", `toast${error ? " is-error" : ""}`, message);
    $("toast-region").append(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  function updateWriteControls() {
    const blocked = Boolean(state.pendingRetry) || state.activeWrites.size > 0;
    const controlsReady = Boolean(state.detail?.scenario_run_id)
      && state.detail.scenario_run_id === state.selectedRunId;
    document.querySelectorAll("form button[type='submit']").forEach((button) => {
      const form = button.closest("form");
      const isTrigger = form?.matches("#sale-form, #demand-form, #receipt-form, #advance-form");
      const formBusy = form?.getAttribute("aria-busy") === "true";
      button.disabled = blocked || formBusy || (isTrigger && !controlsReady);
    });
    $("retry-write").disabled = state.activeWrites.size > 0;
  }

  async function loadStatus() {
    const pill = $("service-status");
    const dot = pill.querySelector(".status-dot");
    try {
      const status = await getJson("/status");
      state.status = status;
      const simulatorReady = status?.simulator_ready === true;
      pill.querySelector("span:last-child").textContent = simulatorReady ? "模拟器在线" : "模拟器未就绪";
      dot.className = `status-dot ${simulatorReady ? "status-dot--ok" : "status-dot--bad"}`;
      const backendText = status?.backend_configured
        ? `后端：${status.backend_status || "已配置"}${status.backend_url ? ` · ${status.backend_url}` : ""}`
        : "后端：未配置";
      pill.title = `${backendText}；数据类型：${status?.synthetic ? "合成" : "未声明"}`;
    } catch (error) {
      pill.querySelector("span:last-child").textContent = "控制台不可用";
      dot.className = "status-dot status-dot--bad";
      pill.title = error.message;
      throw error;
    }
  }

  async function loadRuns({ append = false } = {}) {
    if (state.listLoading) return;
    state.listLoading = true;
    $("load-more-runs").disabled = true;
    try {
      const before = append && state.nextCursor ? `?before=${encodeURIComponent(state.nextCursor)}` : "";
      const page = await getJson(`/runs${before}`);
      const items = Array.isArray(page?.items) ? page.items : [];
      if (append) {
        const known = new Set(state.runs.map((run) => run.scenario_run_id));
        state.runs.push(...items.filter((run) => !known.has(run.scenario_run_id)));
      } else {
        state.runs = items;
      }
      state.nextCursor = page?.next_cursor || null;
      renderRuns();
    } finally {
      state.listLoading = false;
      $("load-more-runs").disabled = false;
    }
  }

  function renderRuns() {
    const nodes = state.runs.map((run) => {
      const button = makeElement("button", `run-card${run.scenario_run_id === state.selectedRunId ? " is-selected" : ""}`);
      button.type = "button";
      button.dataset.runId = run.scenario_run_id;
      button.dataset.scenario = run.scenario;
      button.setAttribute("aria-pressed", String(run.scenario_run_id === state.selectedRunId));
      const dot = makeElement("span", "run-card-dot");
      dot.setAttribute("aria-hidden", "true");
      const body = makeElement("span");
      body.append(makeElement("span", "run-card-title", run.label || `${run.scenario} 场景`));
      const meta = makeElement("span", "run-card-meta");
      meta.append(
        makeElement("span", null, `${run.scenario} · ${formatDateTime(run.created_at, { compact: true })}`),
        makeElement("span", null, `#${formatNumber(run.last_sequence)}`),
      );
      body.append(meta);
      button.append(dot, body);
      button.addEventListener("click", () => selectRun(run.scenario_run_id));
      return button;
    });
    if (!nodes.length) nodes.push(makeElement("p", "sidebar-empty", "尚无持久场景。可在上方创建第一个 SANDBOX。"));
    replaceChildren("run-list", nodes);
    $("run-count").textContent = String(state.runs.length);
    $("load-more-runs").hidden = !state.nextCursor;
  }

  async function selectRun(runId, { quiet = false } = {}) {
    if (!runId) return;
    state.selectedRunId = runId;
    state.detail = null;
    state.events = [];
    state.eventAfter = 0;
    state.eventHasMore = false;
    state.selectionEpoch += 1;
    const epoch = state.selectionEpoch;
    if (state.selectionController) state.selectionController.abort();
    state.selectionController = new AbortController();
    updateWriteControls();
    try {
      localStorage.setItem(SELECTED_RUN_KEY, runId);
    } catch (_) {
      // Storage may be disabled; selection still works for this page session.
    }
    renderRuns();
    $("empty-state").hidden = true;
    $("run-workspace").hidden = false;
    renderDetailLoading();

    const signal = state.selectionController.signal;
    try {
      const [detail, events, backend] = await Promise.all([
        getJson(`/runs/${encodeURIComponent(runId)}`, { signal }),
        getJson(`/runs/${encodeURIComponent(runId)}/events?after_sequence=0&limit=100`, { signal }),
        getJson(`/runs/${encodeURIComponent(runId)}/backend`, { signal }).catch((error) => {
          if (error.name === "AbortError") throw error;
          return { status: "unavailable", _read_error: error.message };
        }),
      ]);
      if (epoch !== state.selectionEpoch) return;
      state.detail = detail;
      applyEventPage(events, { replace: true });
      renderDetail();
      renderBackend(backend);
      updateWriteControls();
    } catch (error) {
      if (error.name === "AbortError") return;
      if (!quiet) showApiError(error, "无法打开场景");
      if (state.runs.length && !state.runs.some((run) => run.scenario_run_id === runId)) {
        try { localStorage.removeItem(SELECTED_RUN_KEY); } catch (_) {}
      }
    }
  }

  function renderDetailLoading() {
    $("sandbox-controls").hidden = true;
    $("sc01-controls").hidden = true;
    $("load-more-events").hidden = true;
    $("load-more-events").disabled = false;
    ["metric-cash", "metric-receivables", "metric-stock", "metric-transit", "metric-demand"].forEach((id) => {
      $(id).textContent = "读取中";
      $(id).classList.add("skeleton");
    });
    $("backend-status-badge").textContent = "读取中";
    $("backend-message").textContent = "正在读取后端同步状态…";
    replaceChildren("event-list", [makeElement("p", "list-empty", "正在读取来源事件…")]);
  }

  function renderDetail() {
    const detail = state.detail;
    if (!detail) return;
    const stateView = detail.state || {};
    const stock = getStock(detail);
    const scenario = detail.scenario || detail.configuration?.scenario || "—";
    const title = detail.label || `${scenario} 场景`;
    const sequence = Number(detail.last_sequence);
    const initialForecast = detail.initial_snapshot?.initial_forecast || {};
    const start = initialForecast.horizon_start;
    const end = initialForecast.horizon_end;

    $("run-scenario-badge").textContent = scenario;
    $("run-scenario-badge").classList.toggle("is-sc01", scenario === "SC01");
    $("run-sync-badge").textContent = `源序号 ${Number.isFinite(sequence) ? sequence : "—"}`;
    $("run-title").textContent = title;
    $("run-subtitle").textContent = `RUN ${detail.scenario_run_id}  ·  STORE ${detail.store_id}`;
    $("run-simulation-time").textContent = formatDateTime(detail.simulation_time || stateView.simulation_time);
    $("run-horizon").textContent = start || end ? `${formatDateTime(start, { compact: true })} → ${formatDateTime(end, { compact: true })}` : "—";
    $("run-step").textContent = scenario === "SC01" ? `第 ${formatNumber(detail.step_index ?? 0)} 步` : "自由触发";
    $("control-sequence").textContent = Number.isFinite(sequence) ? String(sequence) : "—";

    const metrics = {
      "metric-cash": minorToYuan(stateView.cash_minor),
      "metric-receivables": minorToYuan(stateView.receivables_minor),
      "metric-stock": formatNumber(stock.on_hand),
      "metric-transit": formatNumber(stock.in_transit),
      "metric-demand": formatNumber(stock.remaining_demand),
    };
    Object.entries(metrics).forEach(([id, value]) => {
      $(id).classList.remove("skeleton");
      $(id).textContent = value;
    });

    $("sandbox-controls").hidden = scenario !== "SANDBOX";
    $("sc01-controls").hidden = scenario !== "SC01";
    $("demand-remaining").value = Number.isFinite(Number(stock.remaining_demand)) ? String(stock.remaining_demand) : "";
    renderOrders();
    updateImpactPreviews();
    renderEvents();
  }

  function pendingOrders() {
    const orders = Array.isArray(state.detail?.orders) ? state.detail.orders : [];
    return orders.filter((order) => {
      const remaining = Number(order.remaining_quantity);
      const status = String(order.status || "").toUpperCase();
      return order.action_id && remaining > 0 && !["REJECTED", "CANCELLED", "COMPLETED"].includes(status);
    });
  }

  function renderOrders() {
    const orders = pendingOrders();
    $("receipt-available").hidden = !orders.length;
    $("receipt-empty").hidden = Boolean(orders.length);
    const select = $("receipt-order");
    const current = select.value;
    const options = orders.map((order) => {
      const option = document.createElement("option");
      option.value = order.action_id;
      option.textContent = `${shorten(order.action_id, 15)} · 已收 ${formatNumber(order.received_quantity)}/${formatNumber(order.quantity)} · 剩余 ${formatNumber(order.remaining_quantity)}`;
      option.dataset.remaining = String(order.remaining_quantity);
      option.dataset.eta = order.eta || "";
      option.dataset.totalMinor = String(order.total_minor ?? "");
      return option;
    });
    select.replaceChildren(...options);
    if (orders.some((order) => order.action_id === current)) select.value = current;
    updateReceiptImpact();
  }

  function applyEventPage(page, { replace = false } = {}) {
    const events = Array.isArray(page?.events) ? page.events : [];
    state.events = replace ? events : [...state.events, ...events];
    state.eventAfter = Number(page?.last_sequence ?? state.eventAfter) || state.eventAfter;
    state.eventHasMore = page?.has_more === true;
    state.eventSourceHead = Number(page?.source_head_sequence ?? state.eventSourceHead) || 0;
  }

  function eventDescription(event) {
    const payload = event?.payload || {};
    switch (event?.event_type) {
      case "SALE_RECORDED":
        return [`销售 ${formatNumber(payload.quantity)} 件`, `成交单价 ${minorToYuan(payload.unit_price_minor)}`];
      case "DEMAND_REVISED":
        return [`剩余需求调整为 ${formatNumber(payload.remaining_demand)} 件`, payload.forecast_version ? `预测 ${shorten(payload.forecast_version, 24)}` : "预测事实已更新"];
      case "GOODS_RECEIVED":
        return [`到货 ${formatNumber(payload.quantity)} 件`, `订单 ${shorten(payload.action_id, 24)}`];
      case "PURCHASE_ACCEPTED":
        return [`采购受理 ${formatNumber(payload.quantity)} 件`, `金额 ${minorToYuan(payload.total_minor)} · 订单 ${shorten(payload.action_id, 18)}`];
      default: {
        const fields = ["quantity", "remaining_demand", "action_id", "sku_id"]
          .filter((key) => payload[key] !== undefined)
          .map((key) => `${key}: ${payload[key]}`);
        return [event?.event_type || "未知事件", fields.join(" · ") || "无摘要字段"];
      }
    }
  }

  function eventLabel(type) {
    return {
      SALE_RECORDED: "销售记录",
      DEMAND_REVISED: "需求修订",
      GOODS_RECEIVED: "采购到货",
      PURCHASE_ACCEPTED: "采购受理",
    }[type] || type || "未知事件";
  }

  function renderEvents() {
    if (!state.events.length) {
      replaceChildren("event-list", [makeElement("p", "list-empty", "当前场景还没有来源事件。")]);
      $("event-range").textContent = `源头序号 ${state.eventSourceHead || 0}`;
      $("load-more-events").hidden = true;
      return;
    }
    const nodes = state.events.map((event) => {
      const row = makeElement("article", "event-row");
      row.append(makeElement("span", "event-sequence", String(event.sequence)));
      const type = makeElement("div", "event-type");
      type.append(makeElement("strong", null, eventLabel(event.event_type)), makeElement("span", null, event.event_type));
      const description = eventDescription(event);
      const payload = makeElement("div", "event-payload");
      payload.append(makeElement("strong", null, description[0]), makeElement("span", null, description[1]));
      const time = makeElement("div", "event-time");
      time.append(
        makeElement("strong", null, `模拟 ${formatDateTime(event.simulation_time)}`),
        document.createTextNode(`发生 ${formatDateTime(event.occurred_at)}`),
      );
      row.append(type, payload, time);
      return row;
    });
    replaceChildren("event-list", nodes);
    const first = state.events[0]?.sequence;
    const last = state.events[state.events.length - 1]?.sequence;
    $("event-range").textContent = `已显示 #${first}–#${last} · 源头 #${state.eventSourceHead}`;
    $("load-more-events").hidden = !state.eventHasMore;
  }

  function backendStatusCopy(value, readError) {
    const map = {
      ok: ["已连接", "is-ok", "下方是后端当前 HTTP 快照；源头与后端快照读取时间可能不同。"],
      not_imported: ["尚未导入", "is-warning", "该场景尚未由后端导入。独立创建的场景不会自动被后端发现。"],
      unavailable: ["暂不可用", "is-bad", readError || "后端依赖暂不可用，请确认 API 与业务 worker 正在运行。"],
      not_configured: ["未配置", "is-warning", "模拟器未配置后端连接。源场景仍可独立操作。"],
    };
    return map[value] || [value || "未知", "is-warning", "后端返回了未识别的观察状态。"];
  }

  function renderBackend(observation = {}) {
    const [label, className, message] = backendStatusCopy(observation.status, observation._read_error);
    const badge = $("backend-status-badge");
    badge.className = `backend-status ${className}`;
    badge.textContent = label;
    $("backend-message").textContent = message;
    const sourceHead = Number(state.detail?.last_sequence);
    const backendSequence = Number(observation.source_sequence);
    $("backend-source-head").textContent = Number.isFinite(sourceHead) ? String(sourceHead) : "—";
    $("backend-source-sequence").textContent = Number.isFinite(backendSequence) ? String(backendSequence) : "—";
    $("backend-lag").textContent = Number.isFinite(sourceHead) && Number.isFinite(backendSequence)
      ? `${Math.max(0, sourceHead - backendSequence)} 个事件`
      : "—";
    $("backend-read-at").textContent = formatDateTime(new Date().toISOString(), { compact: true });

    renderDashboardSummary(observation.dashboard);
    renderObjectList("backend-missions", observation.missions, "暂无 Mission", "mission");
    renderObjectList("backend-plans", observation.plans, "暂无 Plan", "plan");
    renderObjectList("backend-alerts", observation.alerts, "暂无 Alert", "alert");
  }

  function renderDashboardSummary(dashboard) {
    if (!dashboard || typeof dashboard !== "object") {
      replaceChildren("backend-dashboard", [makeElement("p", "compact-empty", "暂无经营快照")]);
      return;
    }
    const view = dashboard.state && typeof dashboard.state === "object" ? dashboard.state : dashboard;
    const stock = Array.isArray(view.stocks) ? view.stocks[0] || {} : (view.stock || {});
    const candidates = [
      ["可用现金", view.available_cash_minor, minorToYuan],
      ["现金", view.cash_minor, minorToYuan],
      ["预留现金", view.reserved_cash_minor, minorToYuan],
      ["现货", stock.on_hand ?? view.on_hand, formatNumber],
      ["在途", stock.in_transit ?? view.in_transit, formatNumber],
      ["剩余需求", stock.remaining_demand ?? view.remaining_demand, formatNumber],
      ["后端业务版本", view.state_version, formatNumber],
    ].filter(([, value]) => value !== undefined && value !== null);
    if (!candidates.length) {
      replaceChildren("backend-dashboard", [makeElement("p", "compact-empty", "后端快照没有可展示的摘要字段")]);
      return;
    }
    const nodes = candidates.slice(0, 7).map(([label, value, formatter]) => {
      const row = makeElement("div", "compact-kv");
      row.append(makeElement("span", null, label), makeElement("span", null, formatter(value)));
      return row;
    });
    replaceChildren("backend-dashboard", nodes);
  }

  function renderObjectList(id, collection, emptyText, kind) {
    const items = Array.isArray(collection) ? collection : [];
    if (!items.length) {
      replaceChildren(id, [makeElement("p", "compact-empty", emptyText)]);
      return;
    }
    const nodes = items.slice(0, 6).map((rawItem, index) => {
      const item = kind === "plan" && rawItem?.plan && typeof rawItem.plan === "object" ? rawItem.plan : rawItem;
      const card = makeElement("article", "compact-item");
      let title = item?.title || item?.name || item?.objective || item?.kind || item?.type || `记录 ${index + 1}`;
      const status = item?.status || item?.state || item?.severity || "状态未标注";
      const idValue = item?.id || item?.plan_id || item?.mission_id || item?.alert_id;
      const details = [status, idValue ? shorten(idValue, 24) : null];
      if (kind === "plan") {
        title = idValue ? `方案 ${shorten(idValue, 18)}` : title;
        const candidates = Array.isArray(item?.candidates) ? item.candidates : [];
        const recommended = candidates.find((candidate) => candidate?.id === item?.recommended_candidate_id);
        const quantity = item?.proposed_purchase?.quantity ?? recommended?.quantity;
        details.push(quantity === undefined || quantity === null ? "推荐数量未返回" : `推荐 ${formatNumber(quantity)} 件`);
      }
      card.append(makeElement("strong", null, String(title)), makeElement("span", null, details.filter(Boolean).join(" · ")));
      if (kind === "plan" && item?.explanation) {
        card.append(makeElement("span", "compact-item-note", String(item.explanation)));
      }
      return card;
    });
    replaceChildren(id, nodes);
  }

  async function refreshSelected({ quiet = false } = {}) {
    if (!state.selectedRunId) return;
    await selectRun(state.selectedRunId, { quiet });
  }

  async function refreshAll() {
    const button = $("refresh-all");
    button.disabled = true;
    button.classList.add("is-loading");
    try {
      const tasks = [loadStatus(), loadRuns()];
      if (state.selectedRunId) tasks.push(refreshSelected({ quiet: true }));
      await Promise.all(tasks);
      toast("已读取最新状态");
    } catch (error) {
      showApiError(error, "刷新未完成");
    } finally {
      button.disabled = false;
      button.classList.remove("is-loading");
    }
  }

  function setFormBusy(form, busy) {
    const submit = form.querySelector("button[type='submit']");
    if (!submit) return;
    submit.classList.toggle("is-loading", busy);
    form.setAttribute("aria-busy", String(busy));
    updateWriteControls();
  }

  async function handleWriteForm(form, work) {
    if (form.getAttribute("aria-busy") === "true") return;
    setFormBusy(form, true);
    try {
      await work();
    } catch (error) {
      if (!(error instanceof ApiError)) showAlert("输入有误", error.message);
    } finally {
      setFormBusy(form, false);
    }
  }

  function buildScenarioBody() {
    const scenario = $("scenario-type").value;
    if (scenario === "SC01") return { scenario: "SC01" };
    const leadDays = asInteger($("seed-lead").value, "交期", { min: 0, max: 106751991 });
    const label = $("seed-label").value.trim();
    const body = {
      scenario: "SANDBOX",
      parameters: {
        cash_minor: yuanToMinor($("seed-cash").value, "初始现金"),
        on_hand: asInteger($("seed-stock").value, "初始库存"),
        remaining_demand: asInteger($("seed-demand").value, "剩余需求"),
        unit_price_minor: yuanToMinor($("seed-cost").value, "采购单价"),
        minimum_order_quantity: asInteger($("seed-moq").value, "最小订购量", { min: 1 }),
        pack_size: asInteger($("seed-pack").value, "包装量", { min: 1 }),
        lead_time_seconds: leadDays * 86400,
        horizon_days: asInteger($("seed-horizon").value, "活动期", { min: 1, max: 36500 }),
      },
    };
    if (label) body.label = label;
    return body;
  }

  async function handleCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    await handleWriteForm(form, async () => {
      const body = buildScenarioBody();
      const linked = document.querySelector("input[name='create-mode']:checked")?.value === "linked";
      $("create-progress").textContent = linked ? "正在请求后端创建并等待任务完成…" : "正在创建持久场景…";
      const finishCreation = async (result) => {
        let runId = result?.scenario_run_id;
        if (linked) {
          const jobId = result?.job_run_id || result?.job_id || result?.id;
          if (!jobId) throw new ApiError("联动创建已受理，但响应中没有 job_run_id。", { code: "INVALID_JOB_RESPONSE" });
          $("create-progress").textContent = `后端任务 ${shorten(jobId, 22)} 正在运行…`;
          const job = await pollLinkedJob(jobId);
          const references = job?.result?.references || job?.references || [];
          runId = references.find((ref) => ref?.type === "scenario")?.id;
          if (!runId) throw new ApiError("后端任务完成，但结果中没有 scenario 引用。", { code: "MISSING_SCENARIO_REFERENCE" });
        }
        if (!runId) throw new ApiError("创建响应中没有 scenario_run_id。", { code: "INVALID_CREATE_RESPONSE" });
        await loadRuns();
        await selectRun(runId);
        $("create-progress").textContent = "";
        toast(linked ? "联动场景已创建" : "场景已创建");
      };
      await postJson(
        linked ? "/linked-runs" : "/runs",
        body,
        linked ? "联动场景创建" : "场景创建",
        finishCreation,
      );
    });
  }

  function jobState(job) {
    return String(job?.status || job?.state || job?.job_status || "").toUpperCase();
  }

  async function pollLinkedJob(jobId) {
    for (let count = 0; count < 90; count += 1) {
      const job = await getJson(`/jobs/${encodeURIComponent(jobId)}`);
      const status = jobState(job);
      if (["SUCCEEDED", "SUCCESS", "COMPLETED", "DONE"].includes(status)) return job;
      if (["FAILED", "ERROR", "CANCELLED", "CANCELED"].includes(status)) {
        throw new ApiError(job?.error?.message || job?.message || `后端任务以 ${status} 结束。`, { code: `JOB_${status}` });
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    throw new ApiError("后端任务仍在运行。任务没有被取消，可稍后刷新场景列表确认结果。", { code: "JOB_POLL_TIMEOUT" });
  }

  async function afterTrigger(result, successMessage, runId) {
    if (state.selectedRunId === runId) await refreshSelected({ quiet: true });
    await loadRuns();
    const range = result?.first_sequence && result?.last_sequence
      ? ` · 事件 #${result.first_sequence}–#${result.last_sequence}`
      : "";
    toast(`${successMessage}${range}`);
  }

  async function handleSale(event) {
    event.preventDefault();
    const form = event.currentTarget;
    await handleWriteForm(form, async () => {
      const runId = requireLoadedRun("SANDBOX");
      const body = {
        kind: "sale",
        expected_sequence: selectedSequence(),
        quantity: asInteger($("sale-quantity").value, "销售数量", { min: 1 }),
        unit_price_minor: yuanToMinor($("sale-price").value, "成交单价"),
        advance_seconds: asInteger($("sale-advance").value, "推进小时") * 3600,
      };
      await postJson(`/runs/${encodeURIComponent(runId)}/triggers`, body, "销售触发", (result) => afterTrigger(result, "销售事实已提交", runId));
    });
  }

  async function handleDemand(event) {
    event.preventDefault();
    const form = event.currentTarget;
    await handleWriteForm(form, async () => {
      const runId = requireLoadedRun("SANDBOX");
      const body = {
        kind: "demand",
        expected_sequence: selectedSequence(),
        remaining_demand: asInteger($("demand-remaining").value, "剩余需求"),
        advance_seconds: asInteger($("demand-advance").value, "推进小时") * 3600,
      };
      await postJson(`/runs/${encodeURIComponent(runId)}/triggers`, body, "需求修订", (result) => afterTrigger(result, "需求事实已提交", runId));
    });
  }

  async function handleReceipt(event) {
    event.preventDefault();
    const form = event.currentTarget;
    await handleWriteForm(form, async () => {
      const runId = requireLoadedRun("SANDBOX");
      const actionId = $("receipt-order").value;
      if (!actionId) throw new Error("请选择一个待收订单。");
      const body = { kind: "receipt", expected_sequence: selectedSequence(), action_id: actionId };
      const rawQuantity = $("receipt-quantity").value.trim();
      if (rawQuantity) body.quantity = asInteger(rawQuantity, "到货数量", { min: 1 });
      await postJson(`/runs/${encodeURIComponent(runId)}/triggers`, body, "到货登记", (result) => afterTrigger(result, "到货事实已提交", runId));
    });
  }

  async function handleAdvance(event) {
    event.preventDefault();
    const form = event.currentTarget;
    await handleWriteForm(form, async () => {
      const runId = requireLoadedRun("SC01");
      const body = { steps: asInteger($("advance-steps").value, "推进步数", { min: 1, max: 100 }) };
      await postJson(`/runs/${encodeURIComponent(runId)}/advance`, body, "SC01 推进", (result) => afterTrigger(result, "SC01 已推进", runId));
    });
  }

  async function loadMoreEvents() {
    if (!state.selectedRunId || !state.eventHasMore) return;
    const button = $("load-more-events");
    button.disabled = true;
    const epoch = state.selectionEpoch;
    try {
      const runId = state.selectedRunId;
      const after = state.eventAfter;
      const signal = state.selectionController?.signal;
      const page = await getJson(`/runs/${encodeURIComponent(runId)}/events?after_sequence=${after}&limit=100`, { signal });
      if (epoch !== state.selectionEpoch || runId !== state.selectedRunId) return;
      applyEventPage(page);
      renderEvents();
    } catch (error) {
      if (error.name === "AbortError") return;
      showApiError(error, "事件分页读取失败");
    } finally {
      if (epoch === state.selectionEpoch) button.disabled = false;
    }
  }

  function updateImpactPreviews() {
    const stock = getStock();
    try {
      const quantity = asInteger($("sale-quantity").value, "销售数量", { min: 1 });
      const price = yuanToMinor($("sale-price").value, "成交单价");
      const remaining = Number(stock.on_hand) - quantity;
      $("sale-impact").textContent = remaining < 0
        ? `现货仅 ${formatNumber(stock.on_hand)} 件，本次销售将因库存不足被拒绝。`
        : `预计现货 ${formatNumber(stock.on_hand)} → ${formatNumber(remaining)}；应收增加 ${minorToYuan(quantity * price)}。`;
    } catch (_) {
      $("sale-impact").textContent = "填写有效数量与最多两位小数的元金额。";
    }
    try {
      const next = asInteger($("demand-remaining").value, "剩余需求");
      $("demand-impact").textContent = `剩余需求 ${formatNumber(stock.remaining_demand)} → ${formatNumber(next)}；现金与库存不变。`;
    } catch (_) {
      $("demand-impact").textContent = "剩余需求必须为非负整数。";
    }
    updateReceiptImpact();
  }

  function updateReceiptImpact() {
    const option = $("receipt-order")?.selectedOptions?.[0];
    if (!option) return;
    const remaining = Number(option.dataset.remaining);
    const raw = $("receipt-quantity").value.trim();
    const quantity = raw && /^\d+$/.test(raw) ? Number(raw) : remaining;
    const eta = option.dataset.eta;
    $("receipt-impact").textContent = `本次登记 ${formatNumber(quantity)} 件；模拟时间会在需要时推进至 ETA ${formatDateTime(eta)}。订单剩余 ${formatNumber(remaining)} 件。`;
  }

  function applyPreset() {
    const preset = PRESETS[$("preset").value];
    if (!preset) return;
    $("seed-cash").value = preset.cash;
    $("seed-stock").value = String(preset.stock);
    $("seed-demand").value = String(preset.demand);
  }

  function updateScenarioFields() {
    const sandbox = $("scenario-type").value === "SANDBOX";
    $("sandbox-fields").hidden = !sandbox;
  }

  function updateCreateModeHelp() {
    const linked = document.querySelector("input[name='create-mode']:checked")?.value === "linked";
    $("create-mode-help").textContent = linked
      ? "创建并导入后成为后端当前经营环境；已打开的产品前端会自动切换并同步数据。"
      : "立即写入模拟器；后端不会自动导入。";
  }

  function toggleCreatePanel() {
    const button = $("toggle-create");
    const panel = $("create-panel");
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    button.textContent = expanded ? "展开" : "收起";
    panel.hidden = expanded;
  }

  function wireEvents() {
    $("refresh-all").addEventListener("click", refreshAll);
    $("toggle-create").addEventListener("click", toggleCreatePanel);
    $("preset").addEventListener("change", applyPreset);
    $("scenario-type").addEventListener("change", updateScenarioFields);
    document.querySelectorAll("input[name='create-mode']").forEach((radio) => radio.addEventListener("change", updateCreateModeHelp));
    $("create-run-form").addEventListener("submit", handleCreate);
    $("sale-form").addEventListener("submit", handleSale);
    $("demand-form").addEventListener("submit", handleDemand);
    $("receipt-form").addEventListener("submit", handleReceipt);
    $("advance-form").addEventListener("submit", handleAdvance);
    $("load-more-runs").addEventListener("click", () => loadRuns({ append: true }).catch((error) => showApiError(error, "场景分页读取失败")));
    $("load-more-events").addEventListener("click", loadMoreEvents);
    $("dismiss-alert").addEventListener("click", () => hideAlert({ force: true }));
    $("retry-write").addEventListener("click", async () => {
      const attempt = state.pendingRetry;
      if (!attempt) return;
      try {
        await executeAttempt(attempt);
        toast(`${attempt.label}已通过原幂等键确认`);
      } catch (_) {
        // executeAttempt keeps the same attempt visible when the result remains uncertain.
      }
    });
    ["sale-quantity", "sale-price", "demand-remaining"].forEach((id) => $(id).addEventListener("input", updateImpactPreviews));
    ["receipt-order", "receipt-quantity"].forEach((id) => $(id).addEventListener("input", updateReceiptImpact));
  }

  async function start() {
    wireEvents();
    updateScenarioFields();
    updateCreateModeHelp();
    if (window.matchMedia("(max-width: 860px)").matches) toggleCreatePanel();
    try {
      await Promise.all([loadStatus(), loadRuns()]);
    } catch (error) {
      showApiError(error, "控制台启动失败");
      renderRuns();
      return;
    }

    let storedRun = null;
    try { storedRun = localStorage.getItem(SELECTED_RUN_KEY); } catch (_) {}
    if (storedRun) {
      await selectRun(storedRun, { quiet: false });
    } else if (state.runs.length) {
      await selectRun(state.runs[0].scenario_run_id, { quiet: true });
    }
  }

  start();
})();
