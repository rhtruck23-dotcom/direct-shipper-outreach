"""
Global floating chrome: draggable OneNote window (min/max/close) + Jump-to-top.

Injected into the parent Streamlit document so position:fixed sticks to the
viewport. Prefer a single inject_floating_chrome() per Streamlit run (do not
also call inject_notes_shell in the same run — that doubles iframes / lag).

Opening 📝 / typing / tree edits are DOM-only. Persist only on Save via the
hidden Streamlit bridge. Voice-to-text (Web Speech) + in-panel MediaRecorder
embed recordings into the page body as <audio controls>.

Mic APIs run in the *parent* window (not the hidden components.html iframe)
so Chrome user-activation + Permissions-Policy allow microphone access.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import streamlit as st
import streamlit.components.v1 as components

_CHROME_FLAG = "_lt_floating_chrome_injected"
_SHELL_FLAG = "_lt_notes_shell_injected"

# Executed as a <script> in the parent document (top Streamlit page).
# Must not rely on the components.html iframe realm for SpeechRecognition /
# getUserMedia — hidden 1px iframes lose user-activation and mic permission.
_PARENT_VOICE_JS = r"""
(function () {
  if (window.__ltVoiceParentReady) return;
  window.__ltVoiceParentReady = true;

  function hooks() { return window.__ltNotesHooks || null; }
  function voice() {
    if (!window.__ltVoice) {
      window.__ltVoice = {
        recognition: null,
        listening: false,
        recorder: null,
        chunks: [],
        stream: null,
        recording: false
      };
    }
    return window.__ltVoice;
  }

  function ensureMicAllow() {
    try {
      var frames = document.querySelectorAll("iframe");
      for (var i = 0; i < frames.length; i++) {
        var f = frames[i];
        var allow = f.getAttribute("allow") || "";
        if (allow.toLowerCase().indexOf("microphone") === -1) {
          f.setAttribute(
            "allow",
            (allow ? allow + "; " : "") + "microphone; camera; autoplay"
          );
        }
      }
    } catch (e) {}
  }

  window.__ltToggleVoiceToText = function () {
    ensureMicAllow();
    var h = hooks();
    var v = voice();
    if (!h) {
      try { window.alert("Notes voice not ready — reopen the Notes panel."); } catch (e) {}
      return;
    }
    if (v.listening) {
      try { if (v.recognition) v.recognition.stop(); } catch (e) {}
      v.listening = false;
      v.recognition = null;
      h.updateVoiceButtons();
      h.showToast("Voice-to-text stopped");
      return;
    }
    if (v.recording) {
      h.showToast("Stop recording before using voice-to-text", true);
      return;
    }
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      h.showToast("Voice-to-text needs Chrome or Edge (Web Speech API).", true);
      return;
    }
    if (!window.isSecureContext) {
      h.showToast("Microphone requires HTTPS (or localhost).", true);
      return;
    }
    if (!h.selectedPage() || !h.getBody()) {
      h.showToast("Open a page first.", true);
      return;
    }

    function beginSR() {
      var rec = new SR();
      rec.continuous = true;
      rec.interimResults = true;
      rec.lang = (window.navigator.language || "en-US");
      var lastFinal = "";
      rec.onresult = function (ev) {
        var finalChunk = "";
        for (var i = ev.resultIndex; i < ev.results.length; i++) {
          if (ev.results[i].isFinal) {
            finalChunk += ev.results[i][0].transcript;
          }
        }
        finalChunk = (finalChunk || "").trim();
        if (finalChunk && finalChunk !== lastFinal) {
          lastFinal = finalChunk;
          h.insertTextAtCursor(" " + finalChunk);
          h.showToast(
            "Transcribed: " +
              finalChunk.slice(0, 60) +
              (finalChunk.length > 60 ? "…" : "")
          );
        }
      };
      rec.onerror = function (ev) {
        var err = (ev && ev.error) || "unknown";
        if (err === "not-allowed" || err === "service-not-allowed") {
          h.showToast("Mic permission denied — allow microphone for this site.", true);
        } else if (err === "no-speech") {
          h.showToast("No speech heard — try again.", true);
        } else if (err !== "aborted") {
          h.showToast("Voice-to-text error: " + err, true);
        }
        v.listening = false;
        h.updateVoiceButtons();
      };
      rec.onend = function () {
        v.listening = false;
        v.recognition = null;
        h.updateVoiceButtons();
      };
      v.recognition = rec;
      try {
        rec.start();
        v.listening = true;
        h.updateVoiceButtons();
        var body = h.getBody();
        if (body) body.focus();
        h.showToast("Listening… speak now");
      } catch (e) {
        v.listening = false;
        h.updateVoiceButtons();
        h.showToast(
          "Could not start voice-to-text: " + (e && e.message ? e.message : e),
          true
        );
      }
    }

    // Prime mic permission in the parent window, then start Web Speech.
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(function (stream) {
          try {
            stream.getTracks().forEach(function (t) { t.stop(); });
          } catch (e) {}
          beginSR();
        })
        .catch(function (err) {
          var name = (err && err.name) || "";
          if (name === "NotAllowedError" || name === "PermissionDeniedError") {
            h.showToast("Mic permission denied — allow microphone for this site.", true);
          } else if (name === "NotFoundError") {
            h.showToast("No microphone found.", true);
          } else {
            // Fall back to SpeechRecognition alone (some browsers gate only SR).
            beginSR();
          }
        });
    } else {
      beginSR();
    }
  };

  window.__ltToggleRecording = function () {
    ensureMicAllow();
    var h = hooks();
    var v = voice();
    if (!h) {
      try { window.alert("Notes voice not ready — reopen the Notes panel."); } catch (e) {}
      return;
    }
    if (v.recording) {
      if (v.recorder && v.recorder.state !== "inactive") {
        try { v.recorder.stop(); } catch (e) {}
      } else {
        v.recording = false;
        h.stopMediaStream();
        h.updateVoiceButtons();
      }
      return;
    }
    if (v.listening) {
      h.showToast("Stop voice-to-text before recording.", true);
      return;
    }
    if (!h.selectedPage()) {
      h.showToast("Open a page first.", true);
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      h.showToast("Recording needs a modern browser with mic access.", true);
      return;
    }
    if (!window.MediaRecorder) {
      h.showToast("MediaRecorder not supported in this browser.", true);
      return;
    }
    if (!window.isSecureContext) {
      h.showToast("Microphone requires HTTPS (or localhost).", true);
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      v.stream = stream;
      v.chunks = [];
      var mime = "";
      var candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
      for (var i = 0; i < candidates.length; i++) {
        if (window.MediaRecorder.isTypeSupported && window.MediaRecorder.isTypeSupported(candidates[i])) {
          mime = candidates[i];
          break;
        }
      }
      var opts = mime ? { mimeType: mime } : undefined;
      var recorder;
      try {
        recorder = opts ? new window.MediaRecorder(stream, opts) : new window.MediaRecorder(stream);
      } catch (e) {
        h.stopMediaStream();
        h.showToast("Could not start recorder: " + (e && e.message ? e.message : e), true);
        return;
      }
      v.recorder = recorder;
      recorder.ondataavailable = function (ev) {
        if (ev.data && ev.data.size) v.chunks.push(ev.data);
      };
      recorder.onerror = function () {
        h.showToast("Recording failed.", true);
        v.recording = false;
        h.stopMediaStream();
        h.updateVoiceButtons();
      };
      recorder.onstop = function () {
        v.recording = false;
        h.updateVoiceButtons();
        var usedMime = recorder.mimeType || mime || "audio/webm";
        var blob = new window.Blob(v.chunks, { type: usedMime });
        v.chunks = [];
        h.stopMediaStream();
        if (!blob.size) {
          h.showToast("Recording was empty — try again.", true);
          return;
        }
        h.blobToDataUrl(blob).then(function (dataUrl) {
          if (!dataUrl) {
            h.showToast("Could not encode recording.", true);
            return;
          }
          h.embedAudioInPage(dataUrl, usedMime.split(";")[0] || "audio/webm");
          h.showToast("Recording embedded — click Save to persist.");
        }).catch(function (err) {
          h.showToast((err && err.message) || "Failed to embed recording", true);
        });
      };
      try {
        recorder.start(1000);
        v.recording = true;
        h.updateVoiceButtons();
        h.showToast("Recording… click Stop record when done");
      } catch (e2) {
        h.stopMediaStream();
        v.recording = false;
        h.updateVoiceButtons();
        h.showToast("Could not start recording: " + (e2 && e2.message ? e2.message : e2), true);
      }
    }).catch(function (err) {
      var name = (err && err.name) || "";
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        h.showToast("Mic permission denied — allow microphone for this site.", true);
      } else if (name === "NotFoundError") {
        h.showToast("No microphone found.", true);
      } else {
        h.showToast("Mic error: " + (err && err.message ? err.message : name || err), true);
      }
    });
  };

  ensureMicAllow();
})();
"""

# Minimal shell: FAB + three-pane overlay. Opens instantly; tree hydrates later.
_SHELL_HTML = """
<!DOCTYPE html><html><body><script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  if (doc.getElementById("lt-note-fab") && doc.getElementById("lt-onenote-overlay")) {
    win.__ltOpenOneNote = win.__ltOpenOneNote || function () {
      const o = doc.getElementById("lt-onenote-overlay");
      if (!o) return;
      o.classList.add("lt-open");
      o.classList.remove("lt-minimized");
      const chip = doc.getElementById("lt-onenote-chip");
      if (chip) chip.classList.remove("lt-show");
      if (typeof win.__ltRenderOneNote === "function") {
        try { win.__ltRenderOneNote(); } catch (e) {}
      }
    };
    return;
  }
  if (!doc.getElementById("lt-floating-chrome-css")) {
    const style = doc.createElement("style");
    style.id = "lt-floating-chrome-css";
    style.textContent = `
      #lt-note-fab, #lt-jump-top {
        position: fixed !important; z-index: 99999 !important;
        width: 52px; height: 52px; border-radius: 50%; border: none;
        cursor: pointer; box-shadow: 0 8px 28px rgba(11, 61, 74, 0.28);
        display: flex; align-items: center; justify-content: center;
        font-size: 22px; line-height: 1;
        transition: transform 0.15s ease, opacity 0.2s ease;
      }
      #lt-note-fab:hover, #lt-jump-top:hover { transform: scale(1.06); }
      #lt-note-fab { right: 1.25rem; bottom: 1.25rem; background: #7719aa; color: #fff; }
      #lt-jump-top {
        right: 1.25rem; bottom: 5.1rem; background: #0ea5e9; color: #fff;
        opacity: 0; pointer-events: none; visibility: hidden;
      }
      #lt-jump-top.lt-visible { opacity: 1; pointer-events: auto; visibility: visible; }
      #lt-onenote-overlay {
        position: fixed !important; inset: 0; z-index: 100000 !important;
        background: transparent !important;
        display: none; pointer-events: none !important;
        padding: 0; margin: 0; box-sizing: border-box;
        font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      }
      #lt-onenote-overlay.lt-open { display: block !important; }
      #lt-onenote-overlay.lt-minimized #lt-onenote-shell { display: none !important; }
      #lt-onenote-shell {
        position: fixed !important; pointer-events: auto !important;
        left: 120px; top: 72px; width: 900px; height: 620px;
        max-width: calc(100vw - 24px); max-height: calc(100vh - 24px);
        background: #f3f2f1; border-radius: 8px; overflow: hidden;
        box-shadow: 0 24px 64px rgba(0,0,0,0.32);
        display: flex; flex-direction: column; color: #1a1a1a;
      }
      #lt-onenote-shell.lt-maximized {
        left: 12px !important; top: 12px !important;
        width: calc(100vw - 24px) !important; height: calc(100vh - 24px) !important;
        border-radius: 6px;
      }
      #lt-onenote-topbar {
        display: flex; align-items: center; gap: 0.5rem;
        padding: 0.4rem 0.55rem 0.4rem 0.85rem; background: #7719aa; color: #fff;
        flex-shrink: 0; cursor: move; user-select: none; touch-action: none;
      }
      #lt-onenote-topbar h2 { margin: 0; font-size: 1rem; font-weight: 600; flex: 1; cursor: move; }
      #lt-onenote-topbar .lt-win-btns { display: flex; gap: 0.25rem; align-items: center; }
      #lt-onenote-topbar button {
        border: none; background: rgba(255,255,255,0.18); color: #fff;
        border-radius: 4px; padding: 0.2rem 0.55rem; cursor: pointer; font-weight: 600;
        font-size: 0.85rem; line-height: 1.2; min-width: 28px;
      }
      #lt-onenote-chip {
        display: none; position: fixed !important; right: 5.5rem; bottom: 1.4rem;
        z-index: 100001 !important; pointer-events: auto !important;
        background: #7719aa; color: #fff; border: none; border-radius: 999px;
        padding: 0.55rem 1rem; font-weight: 600; font-size: 0.88rem;
        box-shadow: 0 8px 24px rgba(119, 25, 170, 0.35); cursor: pointer;
        font-family: "Segoe UI", system-ui, sans-serif;
      }
      #lt-onenote-chip.lt-show { display: inline-flex !important; align-items: center; gap: 0.35rem; }
      #lt-onenote-body { display: flex; flex: 1; min-height: 0; }
      #lt-onenote-nblist {
        width: 168px; min-width: 140px; background: #2b0a3d; color: #f3e8ff;
        overflow: auto; padding: 0.45rem 0.3rem 1rem; flex-shrink: 0;
      }
      #lt-onenote-mid {
        width: 220px; min-width: 180px; background: #fff;
        border-right: 1px solid #e0e0e0; display: flex; flex-direction: column; flex-shrink: 0;
      }
      #lt-onenote-sectabs {
        display: flex; flex-wrap: wrap; gap: 2px; padding: 0.4rem 0.35rem 0.25rem;
        background: #faf8fc; border-bottom: 1px solid #eee; min-height: 36px;
      }
      #lt-onenote-pagelist { flex: 1; overflow: auto; padding: 0.35rem 0.25rem 1rem; }
      #lt-onenote-editor {
        flex: 1; display: flex; flex-direction: column; align-items: stretch;
        min-width: 0; background: #fff; text-align: left;
      }
      #lt-onenote-empty {
        flex: 1; display: flex; align-items: center; justify-content: center;
        color: #888; font-size: 0.95rem; padding: 2rem; text-align: center;
      }
      #lt-onenote-status { font-size: 0.72rem; color: rgba(255,255,255,0.85); margin-right: 0.5rem; }
      .lt-skel { opacity: 0.55; pointer-events: none; }
      .lt-skel-row {
        height: 28px; margin: 4px 6px; border-radius: 4px;
        background: rgba(255,255,255,0.12);
      }
      .lt-skel-mid .lt-skel-row { background: #eee; }
    `;
    doc.head.appendChild(style);
  }

  const GEOM_KEY = "lt_onenote_geom";
  function loadGeom() {
    try {
      const raw = win.localStorage.getItem(GEOM_KEY);
      if (raw) {
        const g = JSON.parse(raw);
        if (g && typeof g === "object") {
          return Object.assign({ left: null, top: null, width: 900, height: 620, maximized: false }, g);
        }
      }
    } catch (e) {}
    return { left: null, top: null, width: 900, height: 620, maximized: false };
  }
  function saveGeom(partial) {
    try {
      win.localStorage.setItem(GEOM_KEY, JSON.stringify(Object.assign(loadGeom(), partial || {})));
    } catch (e) {}
  }
  function applyGeom() {
    const shell = doc.getElementById("lt-onenote-shell");
    if (!shell) return;
    const g = loadGeom();
    const maxBtn = doc.getElementById("lt-onenote-max");
    if (g.maximized) {
      shell.classList.add("lt-maximized");
      if (maxBtn) { maxBtn.title = "Restore"; maxBtn.textContent = "❐"; }
      return;
    }
    shell.classList.remove("lt-maximized");
    if (maxBtn) { maxBtn.title = "Maximize"; maxBtn.textContent = "□"; }
    const vw = win.innerWidth || 1200;
    const vh = win.innerHeight || 800;
    const w = Math.min(Math.max(Number(g.width) || 900, 420), vw - 24);
    const h = Math.min(Math.max(Number(g.height) || 620, 320), vh - 24);
    let left = g.left, top = g.top;
    if (left == null || top == null || Number.isNaN(Number(left)) || Number.isNaN(Number(top))) {
      left = Math.max(12, Math.round((vw - w) / 2));
      top = Math.max(12, Math.round(vh * 0.1));
    }
    left = Math.min(Math.max(0, Number(left)), vw - 80);
    top = Math.min(Math.max(0, Number(top)), vh - 40);
    shell.style.width = w + "px";
    shell.style.height = h + "px";
    shell.style.left = left + "px";
    shell.style.top = top + "px";
  }
  function showChip(show) {
    let chip = doc.getElementById("lt-onenote-chip");
    if (!chip) {
      chip = doc.createElement("button");
      chip.id = "lt-onenote-chip";
      chip.type = "button";
      chip.textContent = "📓 OneNote";
      chip.title = "Restore Notes";
      chip.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        openPanel();
      });
      doc.body.appendChild(chip);
    }
    if (show) chip.classList.add("lt-show");
    else chip.classList.remove("lt-show");
  }
  function ensureWinChrome() {
    const topbar = doc.getElementById("lt-onenote-topbar");
    if (!topbar) return;
    let btns = topbar.querySelector(".lt-win-btns");
    if (!btns) {
      const oldClose = doc.getElementById("lt-onenote-close");
      if (oldClose) oldClose.remove();
      btns = doc.createElement("div");
      btns.className = "lt-win-btns";
      btns.innerHTML =
        '<button type="button" id="lt-onenote-min" title="Minimize" aria-label="Minimize">─</button>' +
        '<button type="button" id="lt-onenote-max" title="Maximize" aria-label="Maximize">□</button>' +
        '<button type="button" id="lt-onenote-close" title="Close" aria-label="Close">×</button>';
      topbar.appendChild(btns);
    }
    const minBtn = doc.getElementById("lt-onenote-min");
    const maxBtn = doc.getElementById("lt-onenote-max");
    const closeBtn = doc.getElementById("lt-onenote-close");
    if (minBtn) minBtn.onclick = function (e) { e.preventDefault(); e.stopPropagation(); minimizePanel(); };
    if (maxBtn) maxBtn.onclick = function (e) { e.preventDefault(); e.stopPropagation(); toggleMaximize(); };
    if (closeBtn) closeBtn.onclick = function (e) { e.preventDefault(); e.stopPropagation(); closePanel(); };
    if (!topbar.dataset.ltDragBound) {
      topbar.dataset.ltDragBound = "1";
      let dragging = false, sx = 0, sy = 0, ol = 0, ot = 0;
      topbar.addEventListener("pointerdown", function (e) {
        if (e.button !== 0) return;
        if (e.target.closest("button")) return;
        const shell = doc.getElementById("lt-onenote-shell");
        if (!shell || shell.classList.contains("lt-maximized")) return;
        dragging = true;
        sx = e.clientX; sy = e.clientY;
        const rect = shell.getBoundingClientRect();
        ol = rect.left; ot = rect.top;
        try { topbar.setPointerCapture(e.pointerId); } catch (err) {}
        e.preventDefault();
      });
      topbar.addEventListener("pointermove", function (e) {
        if (!dragging) return;
        const shell = doc.getElementById("lt-onenote-shell");
        if (!shell) return;
        shell.style.left = Math.max(0, ol + (e.clientX - sx)) + "px";
        shell.style.top = Math.max(0, ot + (e.clientY - sy)) + "px";
      });
      function endDrag() {
        if (!dragging) return;
        dragging = false;
        const shell = doc.getElementById("lt-onenote-shell");
        if (!shell) return;
        const rect = shell.getBoundingClientRect();
        saveGeom({
          left: Math.round(rect.left), top: Math.round(rect.top),
          width: Math.round(rect.width), height: Math.round(rect.height),
          maximized: false
        });
      }
      topbar.addEventListener("pointerup", endDrag);
      topbar.addEventListener("pointercancel", endDrag);
    }
  }
  function minimizePanel() {
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) return;
    overlay.classList.add("lt-open");
    overlay.classList.add("lt-minimized");
    showChip(true);
  }
  function toggleMaximize() {
    const shell = doc.getElementById("lt-onenote-shell");
    if (!shell) return;
    if (shell.classList.contains("lt-maximized")) {
      shell.classList.remove("lt-maximized");
      saveGeom({ maximized: false });
      applyGeom();
    } else {
      const rect = shell.getBoundingClientRect();
      saveGeom({
        left: Math.round(rect.left), top: Math.round(rect.top),
        width: Math.round(rect.width), height: Math.round(rect.height),
        maximized: true
      });
      shell.classList.add("lt-maximized");
      const maxBtn = doc.getElementById("lt-onenote-max");
      if (maxBtn) { maxBtn.title = "Restore"; maxBtn.textContent = "❐"; }
    }
  }

  function openPanel() {
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) return;
    overlay.classList.add("lt-open");
    overlay.classList.remove("lt-minimized");
    showChip(false);
    ensureWinChrome();
    applyGeom();
    if (typeof win.__ltRenderOneNote === "function") {
      try { win.__ltRenderOneNote(); } catch (e) {}
    }
  }
  function closePanel() {
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (overlay) {
      overlay.classList.remove("lt-open");
      overlay.classList.remove("lt-minimized");
    }
    showChip(false);
  }

  if (!doc.getElementById("lt-jump-top")) {
    const jump = doc.createElement("button");
    jump.id = "lt-jump-top"; jump.type = "button";
    jump.title = "Jump to top"; jump.setAttribute("aria-label", "Jump to top");
    jump.innerHTML = "↑";
    jump.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      try { win.scrollTo({ top: 0, behavior: "smooth" }); } catch (err) {}
      const main = doc.querySelector('[data-testid="stAppViewContainer"]');
      if (main) main.scrollTop = 0;
    });
    doc.body.appendChild(jump);
  }
  if (!doc.getElementById("lt-note-fab")) {
    const fab = doc.createElement("button");
    fab.id = "lt-note-fab"; fab.type = "button";
    fab.title = "OneNote"; fab.setAttribute("aria-label", "Open OneNote");
    fab.innerHTML = "📝";
    fab.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      const overlay = doc.getElementById("lt-onenote-overlay");
      if (!overlay) return;
      if (overlay.classList.contains("lt-minimized")) openPanel();
      else if (overlay.classList.contains("lt-open")) closePanel();
      else openPanel();
    });
    doc.body.appendChild(fab);
  }
  if (!doc.getElementById("lt-onenote-overlay")) {
    const overlay = doc.createElement("div");
    overlay.id = "lt-onenote-overlay";
    overlay.innerHTML = `
      <div id="lt-onenote-shell">
        <div id="lt-onenote-topbar">
          <h2>📓 OneNote</h2>
          <span id="lt-onenote-status">Ready</span>
          <div class="lt-win-btns">
            <button type="button" id="lt-onenote-min" title="Minimize" aria-label="Minimize">─</button>
            <button type="button" id="lt-onenote-max" title="Maximize" aria-label="Maximize">□</button>
            <button type="button" id="lt-onenote-close" title="Close" aria-label="Close">×</button>
          </div>
        </div>
        <div id="lt-onenote-body">
          <div id="lt-onenote-nblist" class="lt-skel">
            <div class="lt-skel-row"></div>
            <div class="lt-skel-row"></div>
          </div>
          <div id="lt-onenote-mid" class="lt-skel-mid">
            <div id="lt-onenote-sectabs" class="lt-skel"><div class="lt-skel-row" style="width:70px"></div></div>
            <div id="lt-onenote-pagelist" class="lt-skel">
              <div class="lt-skel-row"></div>
              <div class="lt-skel-row"></div>
              <div class="lt-skel-row"></div>
            </div>
          </div>
          <div id="lt-onenote-editor">
            <div id="lt-onenote-empty">Select a page — notebooks sync in a moment.</div>
          </div>
        </div>
      </div>`;
    doc.body.appendChild(overlay);
    ensureWinChrome();
    applyGeom();
  } else {
    ensureWinChrome();
  }
  win.__ltOpenOneNote = openPanel;
  win.__ltCloseOneNote = closePanel;
  win.__ltMinimizeOneNote = minimizePanel;
  try {
    if (win.sessionStorage.getItem("lt_onenote_keep_open") === "1") {
      win.sessionStorage.removeItem("lt_onenote_keep_open");
      openPanel();
    }
  } catch (e) {}
})();
</script></body></html>
"""


def inject_notes_shell() -> None:
    """
    Tiny early inject so 📝 FAB exists before heavy page / notes I/O.
    Once per Streamlit script run (caller resets `_lt_notes_shell_done`).
    """
    if st.session_state.get("_lt_notes_shell_done"):
        return
    components.html(_SHELL_HTML, height=1, width=1)
    st.session_state["_lt_notes_shell_done"] = True
    st.session_state[_SHELL_FLAG] = True


def _bridge_widgets() -> tuple[bool, bool]:
    """Hidden Save / Open-signal bridge controls. Returns (save_clicked, open_clicked)."""
    st.markdown(
        """
<style>
  /* Hide Save bridge widgets off-screen but keep them interactive for JS */
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker),
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker) + div,
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker) + div + div,
  div[data-testid="stVerticalBlock"] > div:has(#lt-fab-bridge-marker) + div + div + div {
    position: absolute !important;
    width: 2px !important;
    height: 2px !important;
    overflow: hidden !important;
    opacity: 0.02 !important;
    left: -8000px !important;
    margin: 0 !important;
    padding: 0 !important;
  }
</style>
<div id="lt-fab-bridge-marker"></div>
""",
        unsafe_allow_html=True,
    )
    st.text_area(
        "lt_onenote_payload",
        key="onenote_save_payload",
        height=68,
        label_visibility="collapsed",
    )
    save_clicked = st.button(
        "lt_onenote_save",
        key="onenote_save_btn",
        help="Internal: persist OneNote snapshot",
    )
    open_clicked = st.button(
        "lt_fab_note_open",
        key="fab_note_open",
        help="Internal: request open OneNote panel",
    )
    if open_clicked:
        st.session_state["notes_panel_open"] = True
        st.session_state["onenote_client_open"] = True
    return save_clicked, open_clicked


def inject_floating_chrome(
    *,
    tree: Optional[dict[str, Any]] = None,
    focus_page_id: str = "",
    auto_open: bool = False,
) -> None:
    """
    Inject fixed FABs + full OneNote clone panel once per app render.

    One components.html only — do not also call inject_notes_shell() in the
    same run (that doubles iframes and causes page lag / stale residue).

    tree: {notebooks, sections, pages} from notes.export_tree_for_client()
    focus_page_id: select this page when auto_open
    auto_open: open panel immediately (e.g. sidebar / dashboard reminder)
    """
    # Mark shell as done so a stray early inject_notes_shell() is a no-op
    st.session_state["_lt_notes_shell_done"] = True
    st.session_state[_SHELL_FLAG] = True

    tree = tree or {"notebooks": [], "sections": [], "pages": []}
    tree_json = json.dumps(tree, ensure_ascii=False)
    focus_json = json.dumps(str(focus_page_id or ""))
    auto_json = "true" if auto_open else "false"
    voice_js_literal = json.dumps(_PARENT_VOICE_JS)

    html = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8" /></head><body>
<script>
(function () {{
  const TREE = {tree_json};
  const FOCUS_PAGE = {focus_json};
  const AUTO_OPEN = {auto_json};
  const _ltVoiceSrc = {voice_js_literal};
  const doc = window.parent.document;
  const win = window.parent;
  const SEC_COLORS = ["#7719aa", "#c43e1c", "#217346", "#0078d4", "#ca5010", "#038387", "#8764b8"];

  function uid(prefix) {{
    return prefix + "_" + Math.random().toString(16).slice(2, 12);
  }}
  function nowIso() {{
    return new Date().toISOString().replace(/\\.\\d{{3}}Z$/, "Z");
  }}

  let state = {{
    notebooks: Array.isArray(TREE.notebooks) ? TREE.notebooks.map(function (x) {{ return Object.assign({{}}, x); }}) : [],
    sections: Array.isArray(TREE.sections) ? TREE.sections.map(function (x) {{ return Object.assign({{}}, x); }}) : [],
    pages: Array.isArray(TREE.pages) ? TREE.pages.map(function (x) {{ return Object.assign({{}}, x); }}) : [],
    selectedNbId: "",
    selectedSecId: "",
    selectedPageId: FOCUS_PAGE || "",
    dirty: false,
  }};

  function syncSelectionFromFocus() {{
    if (state.selectedPageId) {{
      const pg = state.pages.find(function (p) {{ return p.id === state.selectedPageId; }});
      if (pg) {{
        state.selectedNbId = pg.notebook_id || state.selectedNbId;
        state.selectedSecId = pg.section_id || state.selectedSecId;
      }}
    }}
    if (!state.selectedNbId && state.notebooks.length) state.selectedNbId = state.notebooks[0].id;
    const secs = sectionsFor(state.selectedNbId);
    if (!state.selectedSecId || !secs.find(function (s) {{ return s.id === state.selectedSecId; }})) {{
      state.selectedSecId = secs[0] ? secs[0].id : "";
    }}
    if (!state.selectedPageId) {{
      const pgs = pagesFor(state.selectedSecId);
      state.selectedPageId = pgs[0] ? pgs[0].id : "";
    }}
  }}
  syncSelectionFromFocus();

  function ensureStyles() {{
    let style = doc.getElementById("lt-floating-chrome-css");
    if (!style) {{
      style = doc.createElement("style");
      style.id = "lt-floating-chrome-css";
      doc.head.appendChild(style);
    }}
    style.textContent = `
      #lt-note-fab, #lt-jump-top {{
        position: fixed !important; z-index: 99999 !important;
        width: 52px; height: 52px; border-radius: 50%; border: none;
        cursor: pointer; box-shadow: 0 8px 28px rgba(11, 61, 74, 0.28);
        display: flex; align-items: center; justify-content: center;
        font-size: 22px; line-height: 1;
        transition: transform 0.15s ease, opacity 0.2s ease;
      }}
      #lt-note-fab:hover, #lt-jump-top:hover {{ transform: scale(1.06); }}
      #lt-note-fab {{ right: 1.25rem; bottom: 1.25rem; background: #7719aa; color: #fff; }}
      #lt-jump-top {{
        right: 1.25rem; bottom: 5.1rem; background: #0ea5e9; color: #fff;
        opacity: 0; pointer-events: none; visibility: hidden;
      }}
      #lt-jump-top.lt-visible {{ opacity: 1; pointer-events: auto; visibility: visible; }}
      #lt-onenote-overlay {{
        position: fixed !important; inset: 0; z-index: 100000 !important;
        background: transparent !important;
        display: none; pointer-events: none !important;
        padding: 0; margin: 0; box-sizing: border-box;
        font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      }}
      #lt-onenote-overlay.lt-open {{ display: block !important; }}
      #lt-onenote-overlay.lt-minimized #lt-onenote-shell {{ display: none !important; }}
      #lt-onenote-shell {{
        position: fixed !important; pointer-events: auto !important;
        left: 120px; top: 72px; width: 900px; height: 620px;
        max-width: calc(100vw - 24px); max-height: calc(100vh - 24px);
        background: #f3f2f1; border-radius: 8px; overflow: hidden;
        box-shadow: 0 24px 64px rgba(0,0,0,0.32);
        display: flex; flex-direction: column; color: #1a1a1a;
      }}
      #lt-onenote-shell.lt-maximized {{
        left: 12px !important; top: 12px !important;
        width: calc(100vw - 24px) !important; height: calc(100vh - 24px) !important;
        border-radius: 6px;
      }}
      #lt-onenote-topbar {{
        display: flex; align-items: center; gap: 0.5rem;
        padding: 0.4rem 0.55rem 0.4rem 0.85rem; background: #7719aa; color: #fff;
        flex-shrink: 0; cursor: move; user-select: none; touch-action: none;
      }}
      #lt-onenote-topbar h2 {{ margin: 0; font-size: 1rem; font-weight: 600; flex: 1; cursor: move; }}
      #lt-onenote-topbar .lt-win-btns {{ display: flex; gap: 0.25rem; align-items: center; }}
      #lt-onenote-topbar button {{
        border: none; background: rgba(255,255,255,0.18); color: #fff;
        border-radius: 4px; padding: 0.2rem 0.55rem; cursor: pointer; font-weight: 600;
        font-size: 0.85rem; line-height: 1.2; min-width: 28px;
      }}
      #lt-onenote-topbar button:hover {{ background: rgba(255,255,255,0.28); }}
      #lt-onenote-chip {{
        display: none; position: fixed !important; right: 5.5rem; bottom: 1.4rem;
        z-index: 100001 !important; pointer-events: auto !important;
        background: #7719aa; color: #fff; border: none; border-radius: 999px;
        padding: 0.55rem 1rem; font-weight: 600; font-size: 0.88rem;
        box-shadow: 0 8px 24px rgba(119, 25, 170, 0.35); cursor: pointer;
        font-family: "Segoe UI", system-ui, sans-serif;
      }}
      #lt-onenote-chip.lt-show {{ display: inline-flex !important; align-items: center; gap: 0.35rem; }}
      #lt-onenote-body {{ display: flex; flex: 1; min-height: 0; }}
      #lt-onenote-nblist {{
        width: 168px; min-width: 140px; background: #2b0a3d; color: #f3e8ff;
        overflow: auto; padding: 0.45rem 0.3rem 1rem; flex-shrink: 0;
      }}
      #lt-onenote-mid {{
        width: 220px; min-width: 180px; background: #fff;
        border-right: 1px solid #e0e0e0; display: flex; flex-direction: column; flex-shrink: 0;
      }}
      #lt-onenote-sectabs {{
        display: flex; flex-wrap: wrap; gap: 2px; padding: 0.4rem 0.35rem 0.25rem;
        background: #faf8fc; border-bottom: 1px solid #eee; min-height: 36px; align-items: center;
      }}
      #lt-onenote-pagelist {{ flex: 1; overflow: auto; padding: 0.35rem 0.25rem 1rem; }}
      #lt-onenote-editor {{
        flex: 1; display: flex; flex-direction: column; align-items: stretch;
        min-width: 0; background: #fff; text-align: left !important;
      }}
      .lt-pane-head {{
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.3rem 0.45rem; font-size: 0.68rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.75;
      }}
      #lt-onenote-nblist .lt-pane-head {{ color: #e9d5ff; }}
      #lt-onenote-pagelist .lt-pane-head, #lt-onenote-mid .lt-pane-head {{ color: #666; }}
      .lt-pane-head button {{
        border: none; background: #7719aa; color: #fff; width: 22px; height: 22px;
        border-radius: 4px; cursor: pointer; font-size: 14px; line-height: 1;
      }}
      #lt-onenote-nblist .lt-pane-head button {{ background: rgba(255,255,255,0.2); }}
      .lt-nb-row {{
        display: flex; align-items: center; gap: 0.2rem;
        padding: 0.35rem 0.4rem; border-radius: 4px; cursor: pointer;
        font-size: 0.86rem; margin: 1px 2px;
      }}
      .lt-nb-row:hover {{ background: rgba(255,255,255,0.1); }}
      .lt-nb-row.lt-active {{ background: rgba(255,255,255,0.18); font-weight: 600; }}
      .lt-sec-tab {{
        border: none; border-radius: 4px 4px 0 0; padding: 0.28rem 0.55rem;
        font-size: 0.78rem; cursor: pointer; color: #fff; max-width: 110px;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        opacity: 0.72;
      }}
      .lt-sec-tab.lt-active {{ opacity: 1; box-shadow: 0 0 0 1px rgba(0,0,0,0.08); }}
      .lt-sec-add {{
        border: 1px dashed #bbb; background: transparent; color: #7719aa;
        border-radius: 4px; width: 24px; height: 24px; cursor: pointer; font-size: 14px;
      }}
      .lt-pg-row {{
        display: flex; align-items: center; gap: 0.25rem;
        padding: 0.4rem 0.45rem; border-radius: 4px; cursor: pointer;
        font-size: 0.88rem; border-left: 3px solid transparent;
      }}
      .lt-pg-row:hover {{ background: #f5f0fa; }}
      .lt-pg-row.lt-active {{ background: #efe6f8; border-left-color: #7719aa; font-weight: 600; }}
      .lt-tree-name {{
        flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        border: none; background: transparent; padding: 0; font: inherit; color: inherit;
        text-align: left; cursor: text;
      }}
      .lt-nb-row .lt-tree-name {{ color: #f3e8ff; }}
      .lt-tree-name:focus {{ outline: 1px solid #c084fc; background: rgba(255,255,255,0.12); border-radius: 2px; padding: 0 2px; }}
      .lt-pg-row .lt-tree-name:focus {{ outline: 1px solid #7719aa; background: #fff; }}
      .lt-tree-del {{
        border: none; background: transparent; color: inherit; cursor: pointer;
        font-size: 0.9rem; padding: 0 3px; opacity: 0.45;
      }}
      .lt-nb-row:hover .lt-tree-del, .lt-pg-row:hover .lt-tree-del {{ opacity: 0.95; }}
      .lt-toolbar {{
        display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center;
        padding: 0.45rem 0.65rem; border-bottom: 1px solid #e5e5e5; background: #fafafa;
      }}
      .lt-toolbar button {{
        border: 1px solid #ccc; background: #fff; border-radius: 5px;
        padding: 0.28rem 0.45rem; cursor: pointer; font-size: 0.82rem; min-width: 28px;
      }}
      .lt-toolbar button:hover {{ background: #f0e6f7; border-color: #7719aa; }}
      .lt-toolbar button.lt-recording {{
        background: #c62828; color: #fff; border-color: #c62828; animation: lt-pulse 1.2s infinite;
      }}
      .lt-toolbar button.lt-listening {{
        background: #1565c0; color: #fff; border-color: #1565c0; animation: lt-pulse 1.2s infinite;
      }}
      @keyframes lt-pulse {{
        0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.65; }}
      }}
      .lt-toolbar input[type="color"] {{
        width: 28px; height: 28px; border: 1px solid #ccc; border-radius: 5px; padding: 0; cursor: pointer;
      }}
      .lt-toolbar input[type="datetime-local"] {{
        border: 1px solid #ccc; border-radius: 5px; padding: 0.2rem 0.35rem; font-size: 0.78rem;
      }}
      #lt-page-body audio.lt-note-audio {{
        display: block; width: 100%; max-width: 480px; margin: 0.5rem 0 0.75rem;
      }}
      #lt-page-body .lt-note-audio-wrap {{
        margin: 0.75rem 0; padding: 0.5rem 0.65rem; background: #f7f3fb;
        border: 1px solid #e4d4f0; border-radius: 6px;
      }}
      #lt-onenote-toast {{
        position: absolute; bottom: 1rem; left: 50%; transform: translateX(-50%);
        background: #323232; color: #fff; padding: 0.45rem 0.9rem; border-radius: 6px;
        font-size: 0.85rem; z-index: 50; opacity: 0; pointer-events: none;
        transition: opacity 0.2s ease; max-width: 90%; text-align: center;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
      }}
      #lt-onenote-toast.lt-show {{ opacity: 1; }}
      .lt-hl-y {{ background: #fff59d !important; }}
      .lt-hl-g {{ background: #c8e6c9 !important; }}
      .lt-hl-p {{ background: #f8bbd0 !important; }}
      .lt-hl-b {{ background: #bbdefb !important; }}
      #lt-page-title {{
        border: none; border-bottom: 1px solid #eee; font-size: 1.35rem; font-weight: 600;
        padding: 0.65rem 1.25rem 0.4rem; width: 100%; max-width: 720px;
        box-sizing: border-box; outline: none; text-align: left !important;
        margin: 0; align-self: flex-start;
      }}
      #lt-page-body {{
        flex: 1; overflow: auto; padding: 0.75rem 1.25rem 1.5rem;
        outline: none; min-height: 180px; line-height: 1.55; font-size: 0.95rem;
        text-align: left !important; direction: ltr; unicode-bidi: plaintext;
        max-width: 720px; width: 100%; box-sizing: border-box;
        margin: 0; align-self: flex-start;
      }}
      #lt-page-body * {{ text-align: left !important; }}
      #lt-page-body:empty:before {{
        content: attr(data-placeholder); color: #999; pointer-events: none;
        text-align: left !important;
      }}
      #lt-onenote-empty {{
        flex: 1; display: flex; align-items: center; justify-content: center;
        color: #888; font-size: 0.95rem; padding: 2rem; text-align: center;
      }}
      #lt-onenote-status {{
        font-size: 0.72rem; color: rgba(255,255,255,0.85); margin-right: 0.5rem;
      }}
    `;
  }}

  function scrollTargets() {{
    const list = [];
    const sels = [
      '[data-testid="stAppViewContainer"]',
      '[data-testid="stMain"]',
      "section.main", ".main", ".stApp",
    ];
    for (const s of sels) {{
      const el = doc.querySelector(s);
      if (el) list.push(el);
    }}
    list.push(doc.scrollingElement || doc.documentElement);
    list.push(doc.body);
    return list;
  }}
  function getScrollY() {{
    let y = win.scrollY || win.pageYOffset || 0;
    for (const el of scrollTargets()) {{
      if (el && typeof el.scrollTop === "number" && el.scrollTop > y) y = el.scrollTop;
    }}
    return y;
  }}
  function scrollToTop() {{
    const opts = {{ top: 0, behavior: "smooth" }};
    try {{ win.scrollTo(opts); }} catch (e) {{}}
    for (const el of scrollTargets()) {{
      try {{
        if (el && typeof el.scrollTo === "function") el.scrollTo(opts);
        else if (el) el.scrollTop = 0;
      }} catch (e) {{}}
    }}
  }}

  function findBridgeButton(label) {{
    const buttons = Array.from(doc.querySelectorAll("button"));
    return (
      buttons.find(function (b) {{ return (b.innerText || "").trim() === label; }}) ||
      buttons.find(function (b) {{ return (b.textContent || "").includes(label); }}) ||
      null
    );
  }}
  function findPayloadTextarea() {{
    const areas = Array.from(doc.querySelectorAll("textarea"));
    return (
      areas.find(function (t) {{
        const lab = (t.getAttribute("aria-label") || "") + (t.id || "");
        return lab.includes("lt_onenote_payload") || lab.includes("onenote_save_payload");
      }}) ||
      areas.find(function (t) {{
        const p = t.closest('[data-testid="stTextArea"]');
        if (!p) return false;
        const txt = p.innerText || "";
        return txt.indexOf("lt_onenote_payload") >= 0;
      }}) ||
      areas[areas.length - 1] ||
      null
    );
  }}
  function setNativeValue(el, value) {{
    try {{
      const tracker = el._valueTracker;
      if (tracker) tracker.setValue("");
    }} catch (e) {{}}
    const proto = el.tagName === "TEXTAREA"
      ? win.HTMLTextAreaElement.prototype
      : win.HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}
  function findPayloadTextareaNearMarker() {{
    const marker = doc.getElementById("lt-fab-bridge-marker");
    if (!marker) return findPayloadTextarea();
    let root = marker.parentElement;
    for (let i = 0; i < 8 && root; i++) {{
      const areas = root.querySelectorAll("textarea");
      if (areas.length) return areas[0];
      root = root.parentElement;
    }}
    return findPayloadTextarea();
  }}

  function selectedPage() {{
    return state.pages.find(function (p) {{ return p.id === state.selectedPageId; }}) || null;
  }}
  function flushEditorToState() {{
    const page = selectedPage();
    if (!page) return;
    const titleEl = doc.getElementById("lt-page-title");
    const bodyEl = doc.getElementById("lt-page-body");
    const remEl = doc.getElementById("lt-page-reminder");
    if (titleEl) page.title = titleEl.value || "";
    if (bodyEl) {{
      page.body_html = bodyEl.innerHTML || "";
      page.body = page.body_html;
    }}
    if (remEl) page.reminder_at = remEl.value ? new Date(remEl.value).toISOString().slice(0, 19) : "";
    page.updated_at = nowIso();
  }}
  function markDirty() {{
    state.dirty = true;
    const st = doc.getElementById("lt-onenote-status");
    if (st) st.textContent = "Unsaved changes";
  }}
  function buildSnapshot(closeAfter) {{
    flushEditorToState();
    return {{
      notebooks: state.notebooks,
      sections: state.sections,
      pages: state.pages.map(function (p) {{
        const copy = Object.assign({{}}, p);
        // Shrink payload: file already on disk — body embed is enough for playback
        if (copy.audio_path && copy.audio_b64) {{
          copy.audio_b64 = "";
        }}
        return copy;
      }}),
      close_after: !!closeAfter,
      transcribe: false,
    }};
  }}
  function persistViaBridge(closeAfter) {{
    const snap = buildSnapshot(closeAfter);
    const payload = JSON.stringify(snap);
    try {{
      win.sessionStorage.setItem("lt_onenote_payload", payload);
      win.sessionStorage.setItem("lt_onenote_keep_open", closeAfter ? "0" : "1");
    }} catch (e) {{}}
    const ta = findPayloadTextareaNearMarker();
    if (ta) {{
      setNativeValue(ta, payload);
    }} else {{
      try {{
        const url = new URL(win.location.href);
        if (payload.length < 1800) {{
          url.searchParams.set("onenote_save", "1");
          url.searchParams.set("onenote_payload", payload);
          win.history.replaceState({{}}, "", url.toString());
        }} else {{
          url.searchParams.set("onenote_save", "1");
          win.history.replaceState({{}}, "", url.toString());
        }}
      }} catch (e) {{}}
    }}
    const btn = findBridgeButton("lt_onenote_save");
    if (btn) {{
      btn.style.pointerEvents = "auto";
      win.setTimeout(function () {{
        btn.click();
        // Bridge click queued Streamlit save — close shell immediately for Save & close
        // (do not wait on round-trip; overlay would keep lt-open across reruns otherwise).
        state.dirty = false;
        const stEl = doc.getElementById("lt-onenote-status");
        if (stEl) stEl.textContent = closeAfter ? "Saved — closing" : "Saving…";
        if (closeAfter) {{
          try {{
            win.sessionStorage.setItem("lt_onenote_keep_open", "0");
            win.sessionStorage.removeItem("lt_onenote_payload");
          }} catch (e) {{}}
          closePanel();
        }}
      }}, 30);
      return;
    }}
    alert("Could not reach Save bridge. Try sidebar Add Note and Save again.");
  }}

  function sectionsFor(nbId) {{
    return state.sections
      .filter(function (s) {{ return s.notebook_id === nbId; }})
      .sort(function (a, b) {{ return (a.order || 0) - (b.order || 0) || (a.name || "").localeCompare(b.name || ""); }});
  }}
  function pagesFor(secId) {{
    return state.pages
      .filter(function (p) {{ return p.section_id === secId; }})
      .sort(function (a, b) {{ return (b.updated_at || "").localeCompare(a.updated_at || ""); }});
  }}

  function addNotebook() {{
    const name = win.prompt("Notebook name", "New notebook");
    if (name === null) return;
    const nb = {{ id: uid("nb"), name: (name || "").trim() || "Untitled", created_at: nowIso(), updated_at: nowIso() }};
    const sec = {{ id: uid("sec"), notebook_id: nb.id, name: "General", order: 0, created_at: nowIso(), updated_at: nowIso() }};
    state.notebooks.push(nb);
    state.sections.push(sec);
    state.selectedNbId = nb.id;
    state.selectedSecId = sec.id;
    state.selectedPageId = "";
    markDirty();
    renderAll();
  }}
  function addSection() {{
    const nbId = state.selectedNbId;
    if (!nbId) return;
    const name = win.prompt("Section name", "New section");
    if (name === null) return;
    const order = sectionsFor(nbId).reduce(function (m, s) {{ return Math.max(m, s.order || 0); }}, -1) + 1;
    const sec = {{ id: uid("sec"), notebook_id: nbId, name: (name || "").trim() || "New section", order: order, created_at: nowIso(), updated_at: nowIso() }};
    state.sections.push(sec);
    state.selectedSecId = sec.id;
    state.selectedPageId = "";
    markDirty();
    renderAll();
  }}
  function addPage() {{
    flushEditorToState();
    const nbId = state.selectedNbId;
    let secId = state.selectedSecId;
    if (!nbId) return;
    if (!secId) {{
      const secs = sectionsFor(nbId);
      if (!secs.length) {{
        const sec = {{ id: uid("sec"), notebook_id: nbId, name: "General", order: 0, created_at: nowIso(), updated_at: nowIso() }};
        state.sections.push(sec);
        secId = sec.id;
        state.selectedSecId = secId;
      }} else {{
        secId = secs[0].id;
        state.selectedSecId = secId;
      }}
    }}
    const page = {{
      id: uid("note"),
      notebook_id: nbId,
      section_id: secId,
      title: "Untitled page",
      body_html: "",
      body: "",
      color: "default",
      reminder_at: "",
      reminder_done: false,
      audio_path: "",
      audio_mime: "",
      audio_b64: "",
      created_at: nowIso(),
      updated_at: nowIso(),
      created_by: "",
    }};
    state.pages.push(page);
    state.selectedPageId = page.id;
    markDirty();
    renderAll();
  }}
  function deleteNotebook(nbId) {{
    if (!win.confirm("Delete this notebook and all its sections/pages?")) return;
    if (state.notebooks.length <= 1) {{ alert("Keep at least one notebook."); return; }}
    state.notebooks = state.notebooks.filter(function (n) {{ return n.id !== nbId; }});
    const secIds = {{}};
    state.sections = state.sections.filter(function (s) {{
      if (s.notebook_id === nbId) {{ secIds[s.id] = true; return false; }}
      return true;
    }});
    state.pages = state.pages.filter(function (p) {{ return p.notebook_id !== nbId; }});
    if (state.selectedNbId === nbId) {{
      state.selectedNbId = state.notebooks[0] ? state.notebooks[0].id : "";
      const secs = sectionsFor(state.selectedNbId);
      state.selectedSecId = secs[0] ? secs[0].id : "";
      const pgs = pagesFor(state.selectedSecId);
      state.selectedPageId = pgs[0] ? pgs[0].id : "";
    }}
    markDirty();
    renderAll();
  }}
  function deleteSection(secId) {{
    if (!win.confirm("Delete this section? Pages move to General.")) return;
    const sec = state.sections.find(function (s) {{ return s.id === secId; }});
    if (!sec) return;
    const generals = sectionsFor(sec.notebook_id).filter(function (s) {{ return s.name === "General" && s.id !== secId; }});
    let generalId = generals[0] && generals[0].id;
    if (!generalId) {{
      const g = {{ id: uid("sec"), notebook_id: sec.notebook_id, name: "General", order: 0, created_at: nowIso(), updated_at: nowIso() }};
      state.sections.push(g);
      generalId = g.id;
    }}
    state.pages.forEach(function (p) {{
      if (p.section_id === secId) p.section_id = generalId;
    }});
    state.sections = state.sections.filter(function (s) {{ return s.id !== secId; }});
    if (state.selectedSecId === secId) state.selectedSecId = generalId;
    markDirty();
    renderAll();
  }}
  function deletePage(pageId) {{
    if (!win.confirm("Delete this page?")) return;
    state.pages = state.pages.filter(function (p) {{ return p.id !== pageId; }});
    if (state.selectedPageId === pageId) {{
      const pgs = pagesFor(state.selectedSecId);
      state.selectedPageId = pgs[0] ? pgs[0].id : "";
    }}
    markDirty();
    renderAll();
  }}

  function execFmt(cmd, val) {{
    try {{ doc.execCommand(cmd, false, val || null); }} catch (e) {{}}
    const body = doc.getElementById("lt-page-body");
    if (body) body.focus();
    markDirty();
  }}
  function highlight(color) {{
    const map = {{ yellow: "#fff59d", green: "#c8e6c9", pink: "#f8bbd0", blue: "#bbdefb" }};
    const hex = map[color] || "#fff59d";
    try {{
      const sel = win.getSelection();
      if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {{
        doc.execCommand("insertHTML", false, '<mark style="background:' + hex + '">highlight</mark>');
      }} else {{
        const range = sel.getRangeAt(0);
        const mark = doc.createElement("mark");
        mark.style.background = hex;
        try {{
          range.surroundContents(mark);
        }} catch (e) {{
          doc.execCommand("insertHTML", false, '<mark style="background:' + hex + '">' + sel.toString() + "</mark>");
        }}
      }}
    }} catch (e) {{}}
    markDirty();
  }}
  function insertBullet() {{ execFmt("insertUnorderedList"); }}

  if (!win.__ltVoice) {{
    win.__ltVoice = {{
      recognition: null,
      listening: false,
      recorder: null,
      chunks: [],
      stream: null,
      recording: false,
    }};
  }}
  const voice = win.__ltVoice;

  function showToast(msg, isError) {{
    const shell = doc.getElementById("lt-onenote-shell");
    if (!shell) {{
      try {{ win.alert(msg); }} catch (e) {{}}
      return;
    }}
    let toast = doc.getElementById("lt-onenote-toast");
    if (!toast) {{
      toast = doc.createElement("div");
      toast.id = "lt-onenote-toast";
      shell.appendChild(toast);
    }}
    toast.textContent = msg || "";
    toast.style.background = isError ? "#b71c1c" : "#323232";
    toast.classList.add("lt-show");
    win.clearTimeout(toast._ltTimer);
    toast._ltTimer = win.setTimeout(function () {{
      toast.classList.remove("lt-show");
    }}, isError ? 4500 : 2800);
    const st = doc.getElementById("lt-onenote-status");
    if (st) st.textContent = msg || "";
  }}

  function insertTextAtCursor(text) {{
    const body = doc.getElementById("lt-page-body");
    if (!body || !text) return;
    body.focus();
    let ok = false;
    try {{ ok = doc.execCommand("insertText", false, text); }} catch (e) {{ ok = false; }}
    if (!ok) {{
      try {{
        const sel = win.getSelection();
        if (sel && sel.rangeCount) {{
          const range = sel.getRangeAt(0);
          range.deleteContents();
          range.insertNode(doc.createTextNode(text));
          range.collapse(false);
          sel.removeAllRanges();
          sel.addRange(range);
          ok = true;
        }}
      }} catch (e2) {{}}
    }}
    if (!ok) body.appendChild(doc.createTextNode(text));
    markDirty();
    flushEditorToState();
  }}

  function embedAudioInPage(dataUrl, mime, quiet) {{
    const body = doc.getElementById("lt-page-body");
    const page = selectedPage();
    if (!body || !page || !dataUrl) return;
    body.querySelectorAll(".lt-note-audio-wrap, audio.lt-note-audio").forEach(function (el) {{
      el.remove();
    }});
    const wrap = doc.createElement("div");
    wrap.className = "lt-note-audio-wrap";
    wrap.setAttribute("contenteditable", "false");
    const label = doc.createElement("p");
    const em = doc.createElement("em");
    em.textContent = "Voice recording";
    label.appendChild(em);
    const audio = doc.createElement("audio");
    audio.className = "lt-note-audio";
    audio.setAttribute("controls", "controls");
    audio.setAttribute("preload", "metadata");
    audio.src = dataUrl;
    wrap.appendChild(label);
    wrap.appendChild(audio);
    body.appendChild(wrap);
    page.audio_b64 = dataUrl;
    page.audio_mime = mime || "audio/webm";
    if (!quiet) page.audio_path = "";
    page.body_html = body.innerHTML;
    page.body = page.body_html;
    if (!quiet) markDirty();
  }}

  function blobToDataUrl(blob) {{
    return new Promise(function (resolve, reject) {{
      const reader = new FileReader();
      reader.onloadend = function () {{ resolve(reader.result || ""); }};
      reader.onerror = function () {{ reject(new Error("Failed to read recording")); }};
      reader.readAsDataURL(blob);
    }});
  }}

  function stopMediaStream() {{
    if (voice.stream) {{
      try {{
        voice.stream.getTracks().forEach(function (t) {{ t.stop(); }});
      }} catch (e) {{}}
      voice.stream = null;
    }}
  }}

  function updateVoiceButtons() {{
    const vBtn = doc.getElementById("lt-btn-voice");
    const rBtn = doc.getElementById("lt-btn-record");
    if (vBtn) {{
      vBtn.classList.toggle("lt-listening", !!voice.listening);
      vBtn.setAttribute("aria-pressed", voice.listening ? "true" : "false");
      vBtn.textContent = voice.listening ? "⏹ Stop" : "🎤 Voice";
      vBtn.title = voice.listening ? "Stop dictation" : "Dictate into the page (Web Speech)";
    }}
    if (rBtn) {{
      rBtn.classList.toggle("lt-recording", !!voice.recording);
      rBtn.setAttribute("aria-pressed", voice.recording ? "true" : "false");
      rBtn.textContent = voice.recording ? "⏹ Stop" : "⏺ Record";
      rBtn.title = voice.recording
        ? "Stop and embed recording on this page"
        : "Record audio and embed player on this page";
    }}
  }}

  function ensureMicAllowOnFrames() {{
    try {{
      if (window.frameElement) {{
        const fe = window.frameElement;
        let allow = fe.getAttribute("allow") || "";
        if (allow.toLowerCase().indexOf("microphone") === -1) {{
          fe.setAttribute("allow", (allow ? allow + "; " : "") + "microphone; camera; autoplay");
        }}
      }}
    }} catch (e) {{}}
    try {{
      doc.querySelectorAll("iframe").forEach(function (f) {{
        let allow = f.getAttribute("allow") || "";
        if (allow.toLowerCase().indexOf("microphone") === -1) {{
          f.setAttribute("allow", (allow ? allow + "; " : "") + "microphone; camera; autoplay");
        }}
      }});
    }} catch (e2) {{}}
  }}

  function installParentVoiceRuntime() {{
    ensureMicAllowOnFrames();
    // Refresh hooks each inject so closures stay current after Streamlit reruns.
    win.__ltNotesHooks = {{
      showToast: showToast,
      insertTextAtCursor: insertTextAtCursor,
      selectedPage: selectedPage,
      markDirty: markDirty,
      embedAudioInPage: embedAudioInPage,
      updateVoiceButtons: updateVoiceButtons,
      blobToDataUrl: blobToDataUrl,
      stopMediaStream: stopMediaStream,
      getBody: function () {{ return doc.getElementById("lt-page-body"); }},
    }};
    if (!doc.getElementById("lt-voice-parent-runtime")) {{
      const s = doc.createElement("script");
      s.id = "lt-voice-parent-runtime";
      s.textContent = _ltVoiceSrc;
      (doc.head || doc.documentElement).appendChild(s);
    }}
  }}

  function bindVoiceButtons() {{
    installParentVoiceRuntime();
    const voiceBtn = doc.getElementById("lt-btn-voice");
    const recBtn = doc.getElementById("lt-btn-record");
    // Inline handlers run in the *parent* document realm (user-activation + mic).
    if (voiceBtn) {{
      voiceBtn.setAttribute(
        "onclick",
        "window.__ltToggleVoiceToText && window.__ltToggleVoiceToText(); return false;"
      );
    }}
    if (recBtn) {{
      recBtn.setAttribute(
        "onclick",
        "window.__ltToggleRecording && window.__ltToggleRecording(); return false;"
      );
    }}
    updateVoiceButtons();
  }}

  function escHtml(s) {{
    return String(s || "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }}
  function escAttr(s) {{ return escHtml(s).replace(/'/g, "&#39;"); }}
  function toLocalInput(iso) {{
    if (!iso) return "";
    try {{
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso).slice(0, 16);
      const pad = function (n) {{ return String(n).padStart(2, "0"); }};
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
        "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }} catch (e) {{ return ""; }}
  }}

  function renderNotebooks() {{
    const rail = doc.getElementById("lt-onenote-nblist");
    if (!rail) return;
    rail.classList.remove("lt-skel");
    let html = '<div class="lt-pane-head"><span>Notebooks</span><button type="button" id="lt-add-nb" title="Add notebook">+</button></div>';
    state.notebooks.forEach(function (nb) {{
      const active = nb.id === state.selectedNbId ? " lt-active" : "";
      html += '<div class="lt-nb-row' + active + '" data-nb="' + nb.id + '">';
      html += '<input class="lt-tree-name" data-rename="nb" data-id="' + nb.id + '" value="' + escAttr(nb.name) + '" />';
      html += '<button type="button" class="lt-tree-del" data-del-nb="' + nb.id + '" title="Delete">×</button>';
      html += "</div>";
    }});
    rail.innerHTML = html;
    const addNb = doc.getElementById("lt-add-nb");
    if (addNb) addNb.onclick = function (e) {{ e.stopPropagation(); addNotebook(); }};
    rail.querySelectorAll(".lt-nb-row").forEach(function (row) {{
      row.addEventListener("click", function (e) {{
        if (e.target.closest("button,input")) return;
        flushEditorToState();
        state.selectedNbId = row.getAttribute("data-nb");
        const secs = sectionsFor(state.selectedNbId);
        state.selectedSecId = secs[0] ? secs[0].id : "";
        const pgs = pagesFor(state.selectedSecId);
        state.selectedPageId = pgs[0] ? pgs[0].id : "";
        renderAll();
      }});
    }});
    rail.querySelectorAll("[data-del-nb]").forEach(function (btn) {{
      btn.onclick = function (e) {{ e.stopPropagation(); deleteNotebook(btn.getAttribute("data-del-nb")); }};
    }});
    rail.querySelectorAll("input.lt-tree-name").forEach(function (inp) {{
      inp.addEventListener("click", function (e) {{ e.stopPropagation(); }});
      inp.addEventListener("change", function () {{
        const id = inp.getAttribute("data-id");
        const val = (inp.value || "").trim() || "Untitled";
        const nb = state.notebooks.find(function (n) {{ return n.id === id; }});
        if (nb) {{ nb.name = val; nb.updated_at = nowIso(); markDirty(); }}
      }});
    }});
  }}

  function renderSectionsAndPages() {{
    const tabs = doc.getElementById("lt-onenote-sectabs");
    const list = doc.getElementById("lt-onenote-pagelist");
    if (!tabs || !list) return;
    const secs = sectionsFor(state.selectedNbId);
    let th = "";
    secs.forEach(function (sec, i) {{
      const active = sec.id === state.selectedSecId ? " lt-active" : "";
      const color = SEC_COLORS[i % SEC_COLORS.length];
      th += '<button type="button" class="lt-sec-tab' + active + '" data-sec="' + sec.id + '" style="background:' + color + '" title="' + escAttr(sec.name) + '">' + escHtml(sec.name) + "</button>";
    }});
    th += '<button type="button" class="lt-sec-add" id="lt-add-sec" title="Add section">+</button>';
    if (state.selectedSecId) {{
      th += '<button type="button" class="lt-sec-add" id="lt-del-sec" title="Delete section" style="color:#c62828;border-color:#e0a0a0">×</button>';
    }}
    tabs.innerHTML = th;

    let ph = '<div class="lt-pane-head"><span>Pages</span><button type="button" id="lt-add-pg" title="Add page">+</button></div>';
    const pgs = pagesFor(state.selectedSecId);
    if (!pgs.length) {{
      ph += '<div style="padding:0.75rem;color:#888;font-size:0.85rem">No pages yet. Click + to add one.</div>';
    }}
    pgs.forEach(function (pg) {{
      const active = pg.id === state.selectedPageId ? " lt-active" : "";
      ph += '<div class="lt-pg-row' + active + '" data-pg="' + pg.id + '">';
      ph += '<input class="lt-tree-name" data-rename="pg" data-id="' + pg.id + '" value="' + escAttr(pg.title || "Untitled page") + '" />';
      ph += '<button type="button" class="lt-tree-del" data-del-pg="' + pg.id + '" title="Delete">×</button>';
      ph += "</div>";
    }});
    list.innerHTML = ph;

    tabs.querySelectorAll("[data-sec]").forEach(function (btn) {{
      btn.onclick = function () {{
        flushEditorToState();
        state.selectedSecId = btn.getAttribute("data-sec");
        const pgs2 = pagesFor(state.selectedSecId);
        state.selectedPageId = pgs2[0] ? pgs2[0].id : "";
        renderAll();
      }};
      btn.ondblclick = function () {{
        const sec = state.sections.find(function (s) {{ return s.id === btn.getAttribute("data-sec"); }});
        if (!sec) return;
        const name = win.prompt("Rename section", sec.name);
        if (name === null) return;
        sec.name = (name || "").trim() || "Untitled section";
        sec.updated_at = nowIso();
        markDirty();
        renderAll();
      }};
    }});
    const addSec = doc.getElementById("lt-add-sec");
    if (addSec) addSec.onclick = function () {{ addSection(); }};
    const delSec = doc.getElementById("lt-del-sec");
    if (delSec) delSec.onclick = function () {{ deleteSection(state.selectedSecId); }};
    const addPg = doc.getElementById("lt-add-pg");
    if (addPg) addPg.onclick = function () {{ addPage(); }};
    list.querySelectorAll(".lt-pg-row").forEach(function (row) {{
      row.addEventListener("click", function (e) {{
        if (e.target.closest("button,input")) return;
        flushEditorToState();
        state.selectedPageId = row.getAttribute("data-pg");
        renderAll();
      }});
    }});
    list.querySelectorAll("[data-del-pg]").forEach(function (btn) {{
      btn.onclick = function (e) {{ e.stopPropagation(); deletePage(btn.getAttribute("data-del-pg")); }};
    }});
    list.querySelectorAll("input.lt-tree-name").forEach(function (inp) {{
      inp.addEventListener("click", function (e) {{ e.stopPropagation(); }});
      inp.addEventListener("change", function () {{
        const id = inp.getAttribute("data-id");
        const val = (inp.value || "").trim() || "Untitled page";
        const pg = state.pages.find(function (p) {{ return p.id === id; }});
        if (pg) {{ pg.title = val; pg.updated_at = nowIso(); markDirty(); }}
      }});
    }});
  }}

  function renderEditor() {{
    const editor = doc.getElementById("lt-onenote-editor");
    if (!editor) return;
    const page = selectedPage();
    if (!page) {{
      editor.innerHTML = '<div id="lt-onenote-empty">Select a page or click <b>+</b> on Pages to add one.</div>';
      return;
    }}
    editor.innerHTML = `
      <div class="lt-toolbar">
        <button type="button" id="lt-fmt-b" title="Bold"><b>B</b></button>
        <button type="button" id="lt-fmt-i" title="Italic"><i>I</i></button>
        <button type="button" class="lt-hl-y" id="lt-hl-y" title="Highlight yellow">Hl</button>
        <button type="button" class="lt-hl-g" id="lt-hl-g" title="Highlight green">Hl</button>
        <button type="button" class="lt-hl-p" id="lt-hl-p" title="Highlight pink">Hl</button>
        <button type="button" class="lt-hl-b" id="lt-hl-b" title="Highlight blue">Hl</button>
        <input type="color" id="lt-text-color" value="#1565c0" title="Text color" />
        <button type="button" id="lt-fmt-ul" title="Bullet list">• List</button>
        <button type="button" id="lt-btn-voice" title="Dictate into the page (Web Speech)">🎤 Voice</button>
        <button type="button" id="lt-btn-record" title="Record audio and embed player on this page">⏺ Record</button>
        <label style="font-size:0.75rem;color:#666;margin-left:0.35rem">Reminder
          <input type="datetime-local" id="lt-page-reminder" />
        </label>
        <span style="flex:1"></span>
        <button type="button" id="lt-btn-save" style="background:#7719aa;color:#fff;border-color:#7719aa">Save</button>
        <button type="button" id="lt-btn-save-close">Save &amp; close</button>
      </div>
      <input id="lt-page-title" type="text" value="${{escAttr(page.title || "")}}" placeholder="Page title" autocomplete="off" />
      <div id="lt-page-body" contenteditable="true" data-placeholder="Start typing…" spellcheck="true"></div>
    `;
    const body = doc.getElementById("lt-page-body");
    if (body) {{
      body.innerHTML = page.body_html || page.body || "";
      body.style.textAlign = "left";
      body.setAttribute("dir", "ltr");
      // Rehydrate embedded player from saved audio_b64 if body lacks one
      if (page.audio_b64 && !body.querySelector("audio.lt-note-audio")) {{
        embedAudioInPage(page.audio_b64, page.audio_mime || "audio/webm", true);
      }}
    }}
    const titleEl = doc.getElementById("lt-page-title");
    if (titleEl) {{
      titleEl.style.textAlign = "left";
      titleEl.setAttribute("dir", "ltr");
    }}
    const rem = doc.getElementById("lt-page-reminder");
    if (rem) rem.value = toLocalInput(page.reminder_at || "");

    doc.getElementById("lt-fmt-b").onclick = function () {{ execFmt("bold"); }};
    doc.getElementById("lt-fmt-i").onclick = function () {{ execFmt("italic"); }};
    doc.getElementById("lt-hl-y").onclick = function () {{ highlight("yellow"); }};
    doc.getElementById("lt-hl-g").onclick = function () {{ highlight("green"); }};
    doc.getElementById("lt-hl-p").onclick = function () {{ highlight("pink"); }};
    doc.getElementById("lt-hl-b").onclick = function () {{ highlight("blue"); }};
    doc.getElementById("lt-text-color").oninput = function (e) {{
      execFmt("foreColor", e.target.value);
    }};
    doc.getElementById("lt-fmt-ul").onclick = function () {{ insertBullet(); }};
    bindVoiceButtons();
    doc.getElementById("lt-btn-save").onclick = function () {{ persistViaBridge(false); }};
    doc.getElementById("lt-btn-save-close").onclick = function () {{ persistViaBridge(true); }};
    if (titleEl) titleEl.oninput = function () {{ markDirty(); }};
    if (body) body.oninput = function () {{ markDirty(); }};
    if (rem) rem.onchange = function () {{ markDirty(); }};
  }}

  function renderAll() {{
    renderNotebooks();
    renderSectionsAndPages();
    renderEditor();
  }}


  const GEOM_KEY = "lt_onenote_geom";
  function loadGeom() {{
    try {{
      const raw = win.localStorage.getItem(GEOM_KEY);
      if (raw) {{
        const g = JSON.parse(raw);
        if (g && typeof g === "object") {{
          return Object.assign({{ left: null, top: null, width: 900, height: 620, maximized: false }}, g);
        }}
      }}
    }} catch (e) {{}}
    return {{ left: null, top: null, width: 900, height: 620, maximized: false }};
  }}
  function saveGeom(partial) {{
    try {{
      win.localStorage.setItem(GEOM_KEY, JSON.stringify(Object.assign(loadGeom(), partial || {{}})));
    }} catch (e) {{}}
  }}
  function applyGeom() {{
    const shell = doc.getElementById("lt-onenote-shell");
    if (!shell) return;
    const g = loadGeom();
    const maxBtn = doc.getElementById("lt-onenote-max");
    if (g.maximized) {{
      shell.classList.add("lt-maximized");
      if (maxBtn) {{ maxBtn.title = "Restore"; maxBtn.textContent = "❐"; }}
      return;
    }}
    shell.classList.remove("lt-maximized");
    if (maxBtn) {{ maxBtn.title = "Maximize"; maxBtn.textContent = "□"; }}
    const vw = win.innerWidth || 1200;
    const vh = win.innerHeight || 800;
    const w = Math.min(Math.max(Number(g.width) || 900, 420), vw - 24);
    const h = Math.min(Math.max(Number(g.height) || 620, 320), vh - 24);
    let left = g.left, top = g.top;
    if (left == null || top == null || Number.isNaN(Number(left)) || Number.isNaN(Number(top))) {{
      left = Math.max(12, Math.round((vw - w) / 2));
      top = Math.max(12, Math.round(vh * 0.1));
    }}
    left = Math.min(Math.max(0, Number(left)), vw - 80);
    top = Math.min(Math.max(0, Number(top)), vh - 40);
    shell.style.width = w + "px";
    shell.style.height = h + "px";
    shell.style.left = left + "px";
    shell.style.top = top + "px";
  }}
  function showChip(show) {{
    let chip = doc.getElementById("lt-onenote-chip");
    if (!chip) {{
      chip = doc.createElement("button");
      chip.id = "lt-onenote-chip";
      chip.type = "button";
      chip.textContent = "📓 OneNote";
      chip.title = "Restore Notes";
      chip.addEventListener("click", function (e) {{
        e.preventDefault(); e.stopPropagation();
        openPanel();
      }});
      doc.body.appendChild(chip);
    }}
    if (show) chip.classList.add("lt-show");
    else chip.classList.remove("lt-show");
  }}
  function ensureWinChrome() {{
    const topbar = doc.getElementById("lt-onenote-topbar");
    if (!topbar) return;
    let btns = topbar.querySelector(".lt-win-btns");
    if (!btns) {{
      const oldClose = doc.getElementById("lt-onenote-close");
      if (oldClose) oldClose.remove();
      btns = doc.createElement("div");
      btns.className = "lt-win-btns";
      btns.innerHTML =
        '<button type="button" id="lt-onenote-min" title="Minimize" aria-label="Minimize">─</button>' +
        '<button type="button" id="lt-onenote-max" title="Maximize" aria-label="Maximize">□</button>' +
        '<button type="button" id="lt-onenote-close" title="Close" aria-label="Close">×</button>';
      topbar.appendChild(btns);
    }}
    const minBtn = doc.getElementById("lt-onenote-min");
    const maxBtn = doc.getElementById("lt-onenote-max");
    const closeBtn = doc.getElementById("lt-onenote-close");
    if (minBtn) minBtn.onclick = function (e) {{ e.preventDefault(); e.stopPropagation(); minimizePanel(); }};
    if (maxBtn) maxBtn.onclick = function (e) {{ e.preventDefault(); e.stopPropagation(); toggleMaximize(); }};
    if (closeBtn) closeBtn.onclick = function (e) {{ e.preventDefault(); e.stopPropagation(); closePanel(); }};
    if (!topbar.dataset.ltDragBound) {{
      topbar.dataset.ltDragBound = "1";
      let dragging = false, sx = 0, sy = 0, ol = 0, ot = 0;
      topbar.addEventListener("pointerdown", function (e) {{
        if (e.button !== 0) return;
        if (e.target.closest("button")) return;
        const shell = doc.getElementById("lt-onenote-shell");
        if (!shell || shell.classList.contains("lt-maximized")) return;
        dragging = true;
        sx = e.clientX; sy = e.clientY;
        const rect = shell.getBoundingClientRect();
        ol = rect.left; ot = rect.top;
        try {{ topbar.setPointerCapture(e.pointerId); }} catch (err) {{}}
        e.preventDefault();
      }});
      topbar.addEventListener("pointermove", function (e) {{
        if (!dragging) return;
        const shell = doc.getElementById("lt-onenote-shell");
        if (!shell) return;
        shell.style.left = Math.max(0, ol + (e.clientX - sx)) + "px";
        shell.style.top = Math.max(0, ot + (e.clientY - sy)) + "px";
      }});
      function endDrag() {{
        if (!dragging) return;
        dragging = false;
        const shell = doc.getElementById("lt-onenote-shell");
        if (!shell) return;
        const rect = shell.getBoundingClientRect();
        saveGeom({{
          left: Math.round(rect.left), top: Math.round(rect.top),
          width: Math.round(rect.width), height: Math.round(rect.height),
          maximized: false
        }});
      }}
      topbar.addEventListener("pointerup", endDrag);
      topbar.addEventListener("pointercancel", endDrag);
    }}
  }}
  function minimizePanel() {{
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) return;
    overlay.classList.add("lt-open");
    overlay.classList.add("lt-minimized");
    showChip(true);
  }}
  function toggleMaximize() {{
    const shell = doc.getElementById("lt-onenote-shell");
    if (!shell) return;
    if (shell.classList.contains("lt-maximized")) {{
      shell.classList.remove("lt-maximized");
      saveGeom({{ maximized: false }});
      applyGeom();
    }} else {{
      const rect = shell.getBoundingClientRect();
      saveGeom({{
        left: Math.round(rect.left), top: Math.round(rect.top),
        width: Math.round(rect.width), height: Math.round(rect.height),
        maximized: true
      }});
      shell.classList.add("lt-maximized");
      const maxBtn = doc.getElementById("lt-onenote-max");
      if (maxBtn) {{ maxBtn.title = "Restore"; maxBtn.textContent = "❐"; }}
    }}
  }}

  function openPanel() {{
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) return;
    overlay.classList.add("lt-open");
    overlay.classList.remove("lt-minimized");
    showChip(false);
    ensureWinChrome();
    applyGeom();
    syncSelectionFromFocus();
    renderAll();
  }}
  function closePanel() {{
    flushEditorToState();
    const overlay = doc.getElementById("lt-onenote-overlay");
    if (overlay) {{
      overlay.classList.remove("lt-open");
      overlay.classList.remove("lt-minimized");
    }}
    showChip(false);
  }}


  function ensureChrome() {{
    ensureStyles();

    let jump = doc.getElementById("lt-jump-top");
    if (!jump) {{
      jump = doc.createElement("button");
      jump.id = "lt-jump-top";
      jump.type = "button";
      jump.title = "Jump to top";
      jump.setAttribute("aria-label", "Jump to top");
      jump.innerHTML = "↑";
      jump.addEventListener("click", function (e) {{
        e.preventDefault(); e.stopPropagation(); scrollToTop();
      }});
      doc.body.appendChild(jump);
    }}

    let fab = doc.getElementById("lt-note-fab");
    if (!fab) {{
      fab = doc.createElement("button");
      fab.id = "lt-note-fab";
      fab.type = "button";
      fab.title = "OneNote";
      fab.setAttribute("aria-label", "Open OneNote");
      fab.innerHTML = "📝";
      fab.addEventListener("click", function (e) {{
        e.preventDefault(); e.stopPropagation();
        const overlay = doc.getElementById("lt-onenote-overlay");
        if (!overlay) return;
        if (overlay.classList.contains("lt-minimized")) openPanel();
        else if (overlay.classList.contains("lt-open")) closePanel();
        else openPanel();
      }});
      doc.body.appendChild(fab);
    }} else {{
      // Rebind FAB to hydrated openPanel (shell may have bound a stub)
      fab.onclick = function (e) {{
        e.preventDefault(); e.stopPropagation();
        const overlay = doc.getElementById("lt-onenote-overlay");
        if (!overlay) return;
        if (overlay.classList.contains("lt-minimized")) openPanel();
        else if (overlay.classList.contains("lt-open")) closePanel();
        else openPanel();
      }};
    }}

    let overlay = doc.getElementById("lt-onenote-overlay");
    if (!overlay) {{
      overlay = doc.createElement("div");
      overlay.id = "lt-onenote-overlay";
      overlay.innerHTML = `
        <div id="lt-onenote-shell">
          <div id="lt-onenote-topbar">
            <h2>📓 OneNote</h2>
            <span id="lt-onenote-status"></span>
            <div class="lt-win-btns">
              <button type="button" id="lt-onenote-min" title="Minimize" aria-label="Minimize">─</button>
              <button type="button" id="lt-onenote-max" title="Maximize" aria-label="Maximize">□</button>
              <button type="button" id="lt-onenote-close" title="Close" aria-label="Close">×</button>
            </div>
          </div>
          <div id="lt-onenote-body">
            <div id="lt-onenote-nblist"></div>
            <div id="lt-onenote-mid">
              <div id="lt-onenote-sectabs"></div>
              <div id="lt-onenote-pagelist"></div>
            </div>
            <div id="lt-onenote-editor"></div>
          </div>
        </div>
      `;
      doc.body.appendChild(overlay);
      ensureWinChrome();
      applyGeom();
    }} else {{
      // Migrate old two-pane shell → three-pane if needed
      const body = doc.getElementById("lt-onenote-body");
      if (body && !doc.getElementById("lt-onenote-nblist")) {{
        body.innerHTML = `
          <div id="lt-onenote-nblist"></div>
          <div id="lt-onenote-mid">
            <div id="lt-onenote-sectabs"></div>
            <div id="lt-onenote-pagelist"></div>
          </div>
          <div id="lt-onenote-editor"></div>`;
      }}
      if (!overlay.classList.contains("lt-open") || !state.dirty) {{
        state.notebooks = Array.isArray(TREE.notebooks) ? TREE.notebooks.map(function (x) {{ return Object.assign({{}}, x); }}) : [];
        state.sections = Array.isArray(TREE.sections) ? TREE.sections.map(function (x) {{ return Object.assign({{}}, x); }}) : [];
        state.pages = Array.isArray(TREE.pages) ? TREE.pages.map(function (x) {{ return Object.assign({{}}, x); }}) : [];
        state.dirty = false;
        if (FOCUS_PAGE) state.selectedPageId = FOCUS_PAGE;
        syncSelectionFromFocus();
      }}
      ensureWinChrome();
      if (overlay.classList.contains("lt-open") && !overlay.classList.contains("lt-minimized")) {{
        applyGeom();
      }}
    }}

    if (!win.__ltJumpScrollBound) {{
      win.__ltJumpScrollBound = true;
      const onScroll = function () {{
        const j = doc.getElementById("lt-jump-top");
        if (!j) return;
        if (getScrollY() > 200) j.classList.add("lt-visible");
        else j.classList.remove("lt-visible");
      }};
      win.addEventListener("scroll", onScroll, {{ passive: true }});
      for (const el of scrollTargets()) {{
        try {{ el.addEventListener("scroll", onScroll, {{ passive: true }}); }} catch (e) {{}}
      }}
      onScroll();
    }}

    win.__ltOpenOneNote = openPanel;
    win.__ltCloseOneNote = closePanel;
    win.__ltMinimizeOneNote = minimizePanel;
    win.__ltRenderOneNote = renderAll;

    const editorEl = doc.getElementById("lt-onenote-editor");
    if (editorEl) editorEl.dataset.hydrated = "1";

    if (AUTO_OPEN || FOCUS_PAGE) {{
      openPanel();
    }} else {{
      try {{
        if (win.sessionStorage.getItem("lt_onenote_keep_open") === "1") {{
          win.sessionStorage.removeItem("lt_onenote_keep_open");
          openPanel();
        }}
      }} catch (e) {{}}
    }}

    const openOverlay = doc.getElementById("lt-onenote-overlay");
    if (openOverlay && openOverlay.classList.contains("lt-open")) {{
      try {{ renderAll(); }} catch (e) {{}}
    }}
  }}

  try {{ ensureChrome(); }} catch (err) {{ console.warn("lt onenote chrome", err); }}
}})();
</script>
</body></html>
"""
    components.html(html, height=1, width=1)
    st.session_state[_CHROME_FLAG] = True
    st.session_state[_SHELL_FLAG] = True
