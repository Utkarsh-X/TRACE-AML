(function (global) {
  "use strict";

  var AUTH_CONFIG_PATH = "/api/v1/auth/config";
  var AUTH_SESSION_PATH = "/api/v1/auth/session";
  var AUTH_GOOGLE_PATH = "/api/v1/auth/google";
  var AUTH_LOGOUT_PATH = "/api/v1/auth/logout";
  var DEFAULT_WORKSPACE_PATH = "/ui/live_ops/index.html";
  var GOOGLE_SCRIPT_SRC = "https://accounts.google.com/gsi/client";
  var _heartbeatTimer = null;
  var _protectStarted = false;

  function _fetchJson(path, init) {
    return fetch(path, Object.assign({
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }, init || {})).then(function (response) {
      return response.text().then(function (body) {
        var parsed = null;
        try {
          parsed = body ? JSON.parse(body) : null;
        } catch (_error) {
          parsed = null;
        }
        return { ok: response.ok, status: response.status, body: parsed, raw: body };
      });
    });
  }

  function _currentPath() {
    return global.location.pathname + (global.location.search || "");
  }

  function _resolveNext(defaultPath) {
    try {
      var params = new URLSearchParams(global.location.search);
      var next = (params.get("next") || "").trim();
      if (next && next.startsWith("/ui/")) {
        return next;
      }
    } catch (_error) { /* ignore */ }
    return defaultPath || DEFAULT_WORKSPACE_PATH;
  }

  function _redirect(path) {
    global.location.replace(path);
  }

  function redirectToAuth(nextPath) {
    var desired = nextPath || _currentPath();
    _redirect("/ui/auth/index.html?next=" + encodeURIComponent(desired));
  }

  function getConfig() {
    return _fetchJson(AUTH_CONFIG_PATH).then(function (result) {
      return result.body || {
        enabled: false,
        ready: false,
        message: "Unable to load desktop auth config.",
      };
    });
  }

  function getSession() {
    return _fetchJson(AUTH_SESSION_PATH);
  }

  function signOut() {
    return _fetchJson(AUTH_LOGOUT_PATH, { method: "POST" });
  }

  function submitGoogleCredential(credential) {
    return _fetchJson(AUTH_GOOGLE_PATH, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ credential: credential }),
    });
  }

  function ensureGoogleScript() {
    return new Promise(function (resolve, reject) {
      if (global.google && global.google.accounts && global.google.accounts.id) {
        resolve(global.google);
        return;
      }

      var existing = document.querySelector('script[data-trace-google-gis="true"]');
      if (existing) {
        existing.addEventListener("load", function () { resolve(global.google); }, { once: true });
        existing.addEventListener("error", reject, { once: true });
        return;
      }

      var script = document.createElement("script");
      script.src = GOOGLE_SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.dataset.traceGoogleGis = "true";
      script.addEventListener("load", function () { resolve(global.google); }, { once: true });
      script.addEventListener("error", reject, { once: true });
      document.head.appendChild(script);
    });
  }

  function _startHeartbeat(intervalSeconds) {
    if (_heartbeatTimer) {
      clearInterval(_heartbeatTimer);
    }

    _heartbeatTimer = global.setInterval(function () {
      getSession().then(function (result) {
        if (!result.ok) {
          redirectToAuth();
        }
      }).catch(function () {
        redirectToAuth();
      });
    }, Math.max(15, Number(intervalSeconds) || 60) * 1000);
  }

  function protectPage() {
    if (_protectStarted) {
      return Promise.resolve();
    }
    _protectStarted = true;

    function onAuthExpired() {
      redirectToAuth();
    }

    global.addEventListener("trace:auth-expired", onAuthExpired);

    return getConfig().then(function (config) {
      if (!config.enabled) {
        return;
      }

      return getSession().then(function (result) {
        if (!result.ok) {
          redirectToAuth();
          return;
        }
        var payload = result.body || {};
        _startHeartbeat(payload.validation_interval_seconds || config.validation_interval_seconds);
      }).catch(function () {
        redirectToAuth();
      });
    });
  }

  function bootstrapAuthPage(options) {
    var opts = options || {};
    var nextPath = _resolveNext(opts.defaultNext || DEFAULT_WORKSPACE_PATH);
    var statusNode = document.getElementById("auth-status");
    var detailNode = document.getElementById("auth-detail");
    var buttonHost = document.getElementById("google-button");
    var shellNode = document.getElementById("auth-shell");

    function setStatus(title, detail, tone) {
      if (statusNode) statusNode.textContent = title || "";
      if (detailNode) detailNode.textContent = detail || "";
      if (shellNode) {
        shellNode.dataset.authTone = tone || "neutral";
      }
    }

    function redirectToWorkspace() {
      _redirect(nextPath);
    }

    getConfig().then(function (config) {
      if (!config.enabled) {
        setStatus("Authorization disabled", "This build is not enforcing Google sign-in. Loading workspace...", "ok");
        global.setTimeout(redirectToWorkspace, 300);
        return;
      }

      if (!config.ready) {
        setStatus("Authorization not configured", config.message || "Google client ID or policy URL is missing in this build.", "error");
        return;
      }

      getSession().then(function (sessionResult) {
        if (sessionResult.ok) {
          redirectToWorkspace();
          return;
        }

        setStatus("Operator sign-in required", config.message || "Use an approved Google account to continue.", "neutral");
        return ensureGoogleScript().then(function () {
          if (!(global.google && global.google.accounts && global.google.accounts.id)) {
            throw new Error("Google Identity Services did not load.");
          }

          global.google.accounts.id.initialize({
            client_id: config.client_id,
            callback: function (response) {
              setStatus("Validating access", "Checking Google identity and remote approval policy...", "neutral");
              submitGoogleCredential(response.credential).then(function (result) {
                if (!result.ok) {
                  setStatus("Access denied", (result.body && result.body.detail) || "This account is not approved for this build.", "error");
                  return;
                }
                setStatus("Access granted", "Desktop session validated. Loading workspace...", "ok");
                global.setTimeout(redirectToWorkspace, 200);
              }).catch(function () {
                setStatus("Validation failed", "Desktop authorization could not be completed.", "error");
              });
            },
          });

          if (buttonHost) {
            buttonHost.innerHTML = "";
            global.google.accounts.id.renderButton(buttonHost, {
              theme: "outline",
              size: "large",
              shape: "pill",
              text: "signin_with",
              width: 320,
            });
          }
        }).catch(function () {
          setStatus(
            "Google sign-in unavailable",
            "The sign-in provider could not be loaded. This build requires a working network connection.",
            "error"
          );
        });
      });
    }).catch(function () {
      setStatus("Authorization bootstrap failed", "Desktop authorization could not be initialized.", "error");
    });
  }

  global.TraceAuth = {
    bootstrapAuthPage: bootstrapAuthPage,
    getConfig: getConfig,
    getSession: getSession,
    protectPage: protectPage,
    redirectToAuth: redirectToAuth,
    signOut: signOut,
  };
})(typeof window !== "undefined" ? window : globalThis);
