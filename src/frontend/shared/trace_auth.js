(function (global) {
  "use strict";

  var AUTH_CONFIG_PATH = "/api/v1/auth/config";
  var AUTH_SESSION_PATH = "/api/v1/auth/session";
  var AUTH_LOGOUT_PATH = "/api/v1/auth/logout";
  var AUTH_BROWSER_START_PATH = "/api/v1/auth/browser/start";
  var AUTH_BROWSER_STATUS_PATH = "/api/v1/auth/browser/status";
  var DEFAULT_WORKSPACE_PATH = "/ui/live_ops/index.html";
  var _heartbeatTimer = null;
  var _browserAuthPollTimer = null;
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

  function _postJson(path, payload) {
    return _fetchJson(path, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload || {}),
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

  function _stopBrowserAuthPoll() {
    if (_browserAuthPollTimer) {
      clearInterval(_browserAuthPollTimer);
      _browserAuthPollTimer = null;
    }
  }

  function _launchExternalAuth(url) {
    if (global.traceDesktop && typeof global.traceDesktop.openExternal === "function") {
      return Promise.resolve(global.traceDesktop.openExternal(url));
    }

    if (typeof global.open === "function") {
      global.open(url, "_blank", "noopener");
      return Promise.resolve({ ok: true });
    }

    global.location.href = url;
    return Promise.resolve({ ok: true });
  }

  function _renderAuthButton(buttonHost, onClick) {
    _renderActionButton(buttonHost, {
      label: "Continue with Google",
      iconMarkup: [
        '<span class="auth-button__icon" aria-hidden="true">',
        '<svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">',
        '<path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.5 3.9-5.5 3.9-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.7 3.5 14.6 2.5 12 2.5A9.5 9.5 0 0 0 2.5 12 9.5 9.5 0 0 0 12 21.5c5.5 0 9.1-3.8 9.1-9.2 0-.6-.1-1.1-.2-1.6z"/>',
        '<path fill="#34A853" d="M3.6 7.6l3.2 2.3A6 6 0 0 1 12 6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.7 3.5 14.6 2.5 12 2.5c-3.6 0-6.7 2-8.4 5.1z"/>',
        '<path fill="#FBBC05" d="M2.5 12c0 1.5.4 3 1.1 4.3l3.6-2.8a5.8 5.8 0 0 1-.3-1.5c0-.5.1-1 .3-1.5L3.6 7.6A9.5 9.5 0 0 0 2.5 12z"/>',
        '<path fill="#4285F4" d="M12 21.5c2.5 0 4.6-.8 6.2-2.3l-3-2.4c-.8.6-1.9 1.1-3.2 1.1-2.5 0-4.7-1.7-5.4-4L3 16.3a9.5 9.5 0 0 0 9 5.2z"/>',
        "</svg>",
        "</span>",
      ].join(""),
      onClick: onClick,
    });
  }

  function _renderActionButton(buttonHost, options) {
    if (!buttonHost) {
      return;
    }

    buttonHost.innerHTML = "";

    var button = document.createElement("button");
    button.type = "button";
    button.className = "auth-button";
    button.innerHTML = (options.iconMarkup || "") + '<span class="auth-button__label">' + String(options.label || "") + "</span>";
    button.addEventListener("click", options.onClick);
    buttonHost.appendChild(button);
  }

  function _pollBrowserAuth(flowId, statusPath, onUpdate) {
    _stopBrowserAuthPoll();
    _browserAuthPollTimer = global.setInterval(function () {
      _fetchJson((statusPath || AUTH_BROWSER_STATUS_PATH) + "?flow_id=" + encodeURIComponent(flowId)).then(function (result) {
        if (!result.ok) {
          if (result.status === 404 || result.status === 409) {
            _stopBrowserAuthPoll();
            onUpdate({
              kind: "failed",
              detail: (result.body && result.body.detail) || "Authorization request expired. Start sign-in again.",
            });
          }
          return;
        }

        var payload = result.body || {};
        if (payload.status === "authenticated") {
          _stopBrowserAuthPoll();
          onUpdate({
            kind: "authenticated",
            payload: payload,
          });
          return;
        }

        if (payload.status === "failed") {
          _stopBrowserAuthPoll();
          onUpdate({
            kind: "failed",
            detail: payload.detail || "Access was denied for this desktop build.",
          });
        }
      }).catch(function () {
        // Keep polling during transient network/backend jitter.
      });
    }, 1500);
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
    var activeButton = null;
    var activeFlowId = "";
    var idleTitle = "Operator sign-in required";
    var idleDetail = "Use an approved Google account to continue.";

    function setStatus(title, detail, tone) {
      if (statusNode) statusNode.textContent = title || "";
      if (detailNode) detailNode.textContent = detail || "";
      if (shellNode) {
        shellNode.dataset.authTone = tone || "neutral";
      }
    }

    function setButtonDisabled(disabled) {
      if (activeButton) {
        activeButton.disabled = !!disabled;
      }
    }

    function syncActiveButton() {
      activeButton = buttonHost && buttonHost.children ? buttonHost.children[0] : null;
    }

    function resetToIdle(config) {
      activeFlowId = "";
      _stopBrowserAuthPoll();
      setStatus(idleTitle, idleDetail, "neutral");
      renderSignInButton(config);
    }

    function renderCancelButton(config) {
      _renderActionButton(buttonHost, {
        label: "Cancel sign-in",
        onClick: function () {
          resetToIdle(config);
        },
      });
      syncActiveButton();
    }

    function renderSignInButton(config) {
      _renderAuthButton(buttonHost, function () {
        setButtonDisabled(true);
        setStatus(
          "Opening Google sign-in",
          "Launching your default browser so you can sign in with an approved account.",
          "neutral"
        );

        _postJson(config.browser_start_path || AUTH_BROWSER_START_PATH, {
          next: nextPath,
        }).then(function (result) {
          if (!result.ok) {
            setButtonDisabled(false);
            setStatus(
              "Authorization unavailable",
              (result.body && result.body.detail) || "TRACE-AML could not start the browser sign-in flow.",
              "error"
            );
            return;
          }

          var payload = result.body || {};
          var authUrl = payload.auth_url || "";
          var flowId = payload.flow_id || "";
          if (!authUrl || !flowId) {
            setButtonDisabled(false);
            setStatus(
              "Authorization unavailable",
              "TRACE-AML did not receive a valid browser sign-in handoff.",
              "error"
            );
            return;
          }

          _launchExternalAuth(authUrl).then(function () {
            activeFlowId = flowId;
            setStatus(
              "Awaiting browser approval",
              "Complete Google sign-in in your default browser. This desktop window will unlock automatically after approval.",
              "neutral"
            );
            renderCancelButton(config);
            _pollBrowserAuth(flowId, config.browser_status_path || AUTH_BROWSER_STATUS_PATH, function (update) {
              if (!activeFlowId || activeFlowId !== flowId) {
                return;
              }
              if (update.kind === "authenticated") {
                activeFlowId = "";
                setStatus(
                  "Access granted",
                  "Desktop session validated. Loading workspace...",
                  "ok"
                );
                global.setTimeout(function () {
                  _redirect((update.payload && update.payload.next) || nextPath);
                }, 250);
                return;
              }

              activeFlowId = "";
              setStatus("Access denied", update.detail, "error");
              renderSignInButton(config);
            });
          }).catch(function () {
            setButtonDisabled(false);
            setStatus(
              "Browser launch failed",
              "TRACE-AML could not open your default browser for Google sign-in.",
              "error"
            );
          });
        }).catch(function () {
          setButtonDisabled(false);
          setStatus(
            "Authorization unavailable",
            "TRACE-AML could not contact the local authorization service.",
            "error"
          );
        });
      });
      syncActiveButton();
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

        idleTitle = "Operator sign-in required";
        idleDetail = config.message || "Use an approved Google account to continue.";
        setStatus(idleTitle, idleDetail, "neutral");
        renderSignInButton(config);
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
