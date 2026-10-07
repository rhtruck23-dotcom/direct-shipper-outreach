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
      920,
      (document.documentElement && document.documentElement.scrollHeight) || 0,
      (document.body && document.body.scrollHeight) || 0
    );
    window.Streamlit.setFrameHeight(h);
  }

  if (window.Streamlit && typeof window.Streamlit.setComponentReady === "function") {
    window.Streamlit.setComponentReady();
  }
  applyHeight();
  window.addEventListener("load", applyHeight);
  window.addEventListener("resize", applyHeight);
  if (typeof ResizeObserver !== "undefined" && document.body) {
    try {
      new ResizeObserver(applyHeight).observe(document.body);
    } catch (_e) {
      /* ignore */
    }
  }
  setInterval(applyHeight, 1500);
})();
