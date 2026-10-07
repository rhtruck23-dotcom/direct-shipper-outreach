/**
 * When embedded as a Streamlit custom component, expand the iframe.
 * No-op when running standalone (Vite dev / Vercel).
 */
(function () {
  function applyHeight() {
    if (!window.Streamlit || typeof window.Streamlit.setFrameHeight !== "function") {
      return;
    }
    var h = Math.max(
      960,
      (document.documentElement && document.documentElement.scrollHeight) || 0,
      (document.body && document.body.scrollHeight) || 0
    );
    window.Streamlit.setFrameHeight(h);
  }

  function boot() {
    if (window.Streamlit && typeof window.Streamlit.setComponentReady === "function") {
      window.Streamlit.setComponentReady();
    }
    applyHeight();
  }

  boot();
  window.addEventListener("load", applyHeight);
  window.addEventListener("resize", applyHeight);
  if (typeof ResizeObserver !== "undefined" && document.body) {
    try {
      new ResizeObserver(applyHeight).observe(document.body);
    } catch (_e) {
      /* ignore */
    }
  }
  // Retry briefly — component lib may load just after this script in some builds.
  var tries = 0;
  var timer = setInterval(function () {
    tries += 1;
    boot();
    if (tries >= 20) clearInterval(timer);
  }, 250);
  setInterval(applyHeight, 1500);
})();
