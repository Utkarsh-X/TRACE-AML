const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName, ownerDocument, id = "") {
    this.tagName = String(tagName || "div").toUpperCase();
    this.ownerDocument = ownerDocument;
    this.id = id;
    this.dataset = {};
    this.textContent = "";
    this._innerHTML = "";
    this.children = [];
    this.listeners = new Map();
    this.disabled = false;
    this.className = "";
    this.type = "";
  }

  get innerHTML() {
    return this._innerHTML;
  }

  set innerHTML(value) {
    this._innerHTML = String(value || "");
    this.textContent = this._innerHTML.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    if (!this._innerHTML) {
      this.children = [];
    }
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener(type, handler) {
    const handlers = this.listeners.get(type) || [];
    handlers.push(handler);
    this.listeners.set(type, handlers);
  }

  click() {
    const handlers = this.listeners.get("click") || [];
    for (const handler of handlers) {
      handler({ preventDefault() {} });
    }
  }
}

class FakeDocument {
  constructor() {
    this.elements = new Map();
    this.head = new FakeElement("head", this, "head");
    this.body = new FakeElement("body", this, "body");
  }

  createElement(tagName) {
    return new FakeElement(tagName, this);
  }

  getElementById(id) {
    return this.elements.get(id) || null;
  }

  register(id) {
    const element = new FakeElement("div", this, id);
    this.elements.set(id, element);
    return element;
  }

  querySelector() {
    return null;
  }
}

async function flushMicrotasks() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  await Promise.resolve();
}

async function run() {
  const document = new FakeDocument();
  const authStatus = document.register("auth-status");
  const authDetail = document.register("auth-detail");
  const buttonHost = document.register("google-button");
  const shell = document.register("auth-shell");

  const openedUrls = [];
  const fetchCalls = [];
  const responses = [
    {
      ok: true,
      status: 200,
      body: {
        enabled: true,
        ready: true,
        message: "Approved accounts only.",
        browser_start_path: "/api/v1/auth/browser/start",
      },
    },
    {
      ok: false,
      status: 401,
      body: { detail: "Authentication is required." },
    },
    {
      ok: true,
      status: 200,
      body: {
        status: "ready",
        flow_id: "flow-123",
        auth_url: "https://accounts.google.com/o/oauth2/v2/auth?state=abc",
        next: "/ui/live_ops/index.html",
      },
    },
  ];

  async function fetchStub(url, init = {}) {
    fetchCalls.push({ url, init });
    const next = responses.shift();
    if (!next) {
      throw new Error(`Unexpected fetch: ${url}`);
    }
    return {
      ok: next.ok,
      status: next.status,
      async text() {
        return next.body ? JSON.stringify(next.body) : "";
      },
    };
  }

  const location = {
    pathname: "/ui/auth/index.html",
    search: "?next=%2Fui%2Flive_ops%2Findex.html",
    replacedWith: "",
    replace(target) {
      this.replacedWith = target;
    },
  };

  const window = {
    location,
    document,
    fetch: fetchStub,
    setTimeout(fn) {
      fn();
      return 1;
    },
    clearTimeout() {},
    setInterval() {
      return 1;
    },
    clearInterval() {},
    addEventListener() {},
    dispatchEvent() {},
    traceDesktop: {
      openExternal(url) {
        openedUrls.push(url);
        return Promise.resolve({ ok: true });
      },
    },
    URLSearchParams,
    console,
  };

  const context = vm.createContext({
    window,
    document,
    fetch: fetchStub,
    location,
    URLSearchParams,
    console,
    setTimeout: window.setTimeout,
    clearTimeout: window.clearTimeout,
    setInterval: window.setInterval,
    clearInterval: window.clearInterval,
    globalThis: window,
  });

  const source = fs.readFileSync(
    path.join(__dirname, "..", "..", "src", "frontend", "shared", "trace_auth.js"),
    "utf-8",
  );
  vm.runInContext(source, context);

  assert.ok(window.TraceAuth, "TraceAuth should be exposed on window");

  window.TraceAuth.bootstrapAuthPage({ defaultNext: "/ui/live_ops/index.html" });
  await flushMicrotasks();

  assert.equal(buttonHost.children.length, 1, "auth page should render a custom sign-in button");
  const button = buttonHost.children[0];
  assert.match(button.textContent, /google/i);

  button.click();
  await flushMicrotasks();

  assert.deepEqual(openedUrls, ["https://accounts.google.com/o/oauth2/v2/auth?state=abc"]);
  assert.equal(authStatus.textContent.length > 0, true);
  assert.equal(shell.dataset.authTone === "neutral" || shell.dataset.authTone === "ok", true);
  assert.equal(fetchCalls[2].url, "/api/v1/auth/browser/start");

  console.log("auth flow tests passed");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
