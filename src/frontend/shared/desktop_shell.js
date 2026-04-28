(function () {
  "use strict";

  function bindDesktopExit() {
    var exitButton = document.getElementById("desktop-exit-button");
    if (!exitButton) {
      return;
    }

    exitButton.addEventListener("click", function () {
      if (window.traceDesktop && typeof window.traceDesktop.quitApp === "function") {
        window.traceDesktop.quitApp();
        return;
      }

      window.close();
    });
  }

  function bindDesktopAuthGuard() {
    if (document.body && document.body.dataset.skipAuthGuard === "true") {
      return;
    }

    if (window.TraceAuth && typeof window.TraceAuth.protectPage === "function") {
      window.TraceAuth.protectPage();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindDesktopExit();
      bindDesktopAuthGuard();
    }, { once: true });
  } else {
    bindDesktopExit();
    bindDesktopAuthGuard();
  }
})();
