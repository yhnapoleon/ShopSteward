"use strict";

// Run with: node simulation/tests/console_ui_regression.cjs
// Load the actual console code with DOM/fetch mocks; no browser, services or DB.
const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function harness() {
  const nodes = new Map();
  function element(id = "") {
    return {
      id, hidden: false, disabled: false, value: "1", textContent: "",
      attrs: {}, dataset: {}, children: [], selectedOptions: [],
      classList: { add() {}, remove() {}, toggle() {} },
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      remove() {}, addEventListener() {},
      setAttribute(key, value) { this.attrs[key] = value; },
      getAttribute(key) { return this.attrs[key]; },
      closest() { return this.form || null; },
      matches() { return ["sale-form", "demand-form", "receipt-form", "advance-form"].includes(this.id); },
      querySelector() { return get(`${id}-submit`); },
    };
  }
  function get(id) {
    if (!nodes.has(id)) nodes.set(id, element(id));
    return nodes.get(id);
  }
  const submitButtons = ["create-run-form", "sale-form", "demand-form", "receipt-form", "advance-form"]
    .map((id) => {
      const button = get(`${id}-submit`);
      button.form = get(id);
      return button;
    });
  const context = {
    console, structuredClone, AbortController, crypto: webcrypto,
    document: {
      getElementById: get,
      querySelectorAll: () => submitButtons,
      createElement: () => element(),
      createTextNode: (text) => ({ textContent: text }),
    },
    localStorage: { setItem() {}, removeItem() {} },
    window: { setTimeout() {} },
    fetch: async () => { throw new Error("Mock network disconnected"); },
  };
  vm.createContext(context);
  const filename = path.resolve(__dirname, "../simulator/static/console.js");
  const original = fs.readFileSync(filename, "utf8");
  const entrypoint = "  start();";
  assert.equal(original.split(entrypoint).length, 2, "Console startup hook must occur exactly once");
  const source = original.replace(entrypoint, `  globalThis.test = {
    state, executeAttempt, showApiError, ApiError, selectRun,
    handleAdvance, loadMoreEvents, applyEventPage
  };`);
  vm.runInContext(source, context, { filename });
  return { context, get, ...context.test };
}

function jsonResponse(status, value) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => value,
  };
}

async function retrySurvivesReadErrorsAndUnlocksOnDefinitiveFailure() {
  const h = harness();
  const attempt = {
    key: "original-key", path: "/runs/A/triggers", label: "sale",
    body: { kind: "sale", expected_sequence: 0, quantity: 1, unit_price_minor: 2000 },
  };
  const requests = [];
  h.context.fetch = async (url, options) => {
    requests.push({ url, key: options.headers["Idempotency-Key"], body: options.body });
    throw new Error("Mock response lost");
  };
  await assert.rejects(h.executeAttempt(attempt), (error) => error.uncertain === true);
  assert.equal(h.state.pendingRetry, attempt);
  assert.equal(h.get("retry-write").hidden, false);
  assert.equal(h.get("create-run-form-submit").disabled, true);

  h.showApiError(new h.ApiError("Mock read failed"), "refresh failed");
  assert.equal(h.state.pendingRetry, attempt);
  assert.equal(h.get("retry-write").hidden, false, "Read errors must retain the retry action");
  assert.equal(h.get("dismiss-alert").hidden, true);

  h.context.fetch = async (url, options) => {
    requests.push({ url, key: options.headers["Idempotency-Key"], body: options.body });
    return jsonResponse(409, { error: { code: "SOURCE_CHANGED" } });
  };
  await assert.rejects(h.executeAttempt(attempt), (error) => error.status === 409);
  assert.deepEqual(requests[1], requests[0], "Retry must preserve the original path, key and body");
  assert.equal(h.state.pendingRetry, null, "Definitive failure resolves the pending attempt");
  assert.equal(h.get("retry-write").hidden, true);
  assert.equal(h.get("create-run-form-submit").disabled, false);
}

async function loadingSelectionCannotAdvanceTheWrongRun() {
  const h = harness();
  h.state.selectedRunId = "A";
  h.state.detail = { scenario: "SC01", scenario_run_id: "A" };
  h.get("run-title").textContent = "SC01 A";
  h.get("sc01-controls").hidden = false;
  const posts = [];
  h.context.fetch = async (url, options) => {
    if (options.method === "POST") posts.push(url);
    return new Promise(() => {}); // Hold the new selection's reads in flight.
  };
  void h.selectRun("B");
  assert.equal(h.state.selectedRunId, "B");
  assert.equal(h.state.detail, null);
  assert.equal(h.get("sc01-controls").hidden, true);
  assert.equal(h.get("advance-form-submit").disabled, true);
  // Invoke the handler directly as well: correctness must not depend only on CSS/disabled.
  await h.handleAdvance({ preventDefault() {}, currentTarget: h.get("advance-form") });
  assert.equal(posts.length, 0, "SC01 must not write while the selected detail is unavailable");
}

async function stalePaginationCannotPolluteAReopenedRun() {
  const h = harness();
  h.state.selectedRunId = "A";
  h.state.selectionController = new AbortController();
  h.state.eventHasMore = true;
  h.state.eventAfter = 200;
  let resolveOldPage;
  let oldSignal;
  h.context.fetch = async (url, options) => {
    if (url.includes("after_sequence=200")) {
      oldSignal = options.signal;
      // Deliberately ignore abort to exercise the epoch guard even after a late response.
      return new Promise((resolve) => { resolveOldPage = resolve; });
    }
    return new Promise(() => {});
  };
  const oldRequest = h.loadMoreEvents();
  assert.equal(h.get("load-more-events").disabled, true);
  void h.selectRun("B");
  void h.selectRun("A");
  assert.equal(oldSignal.aborted, true);
  assert.equal(h.get("load-more-events").disabled, false, "New selection owns an unlocked pager");
  const firstPage = Array.from({ length: 100 }, (_, index) => ({ sequence: index + 1 }));
  h.applyEventPage({ events: firstPage, last_sequence: 100, has_more: true, source_head_sequence: 300 }, { replace: true });
  resolveOldPage(jsonResponse(200, {
    events: [{ sequence: 201 }], last_sequence: 300, has_more: false, source_head_sequence: 300,
  }));
  await oldRequest;
  assert.equal(h.state.events, firstPage, "Old pagination must not append to the reopened run");
  assert.equal(h.state.eventAfter, 100);
  assert.equal(h.state.eventHasMore, true);
  assert.equal(h.get("load-more-events").disabled, false);
}

(async () => {
  for (const test of [
    retrySurvivesReadErrorsAndUnlocksOnDefinitiveFailure,
    loadingSelectionCannotAdvanceTheWrongRun,
    stalePaginationCannotPolluteAReopenedRun,
  ]) {
    await test();
    console.log(`PASS ${test.name}`);
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
