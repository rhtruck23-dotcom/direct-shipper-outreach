/**
 * Esign placer — right-click Add text/date/sign posts via Streamlit.setComponentValue.
 * Never uses parent-document textarea/Apply bridge (broken in Cloud iframes).
 */
function sendValue(value) {
  Streamlit.setComponentValue(value);
}

(function () {
  const stage = document.getElementById("stage");
  const overlay = document.getElementById("overlay");
  const menu = document.getElementById("menu");
  const img = document.getElementById("img");

  let PAGE = 0;
  let DEF_W = 0.28;
  let DEF_H = 0.04;
  let NEXT_TYPE = "text";
  let fields = [];
  let pending = null;
  let drag = null;
  let suppressClick = false;
  let lastSrc = "";

  function typeColor(t) {
    if (t === "date") return "#059669";
    if (t === "sign") return "#ea580c";
    return "#2563eb";
  }

  function syncOverlayToImage() {
    if (!img.clientWidth || !img.clientHeight) return;
    overlay.style.left = img.offsetLeft + "px";
    overlay.style.top = img.offsetTop + "px";
    overlay.style.width = img.clientWidth + "px";
    overlay.style.height = img.clientHeight + "px";
  }

  function fracFromEvent(ev) {
    const r = overlay.getBoundingClientRect();
    if (!r.width || !r.height) return { x: 0.1, y_from_top: 0.15 };
    const x = Math.max(0, Math.min(0.95, (ev.clientX - r.left) / r.width));
    const y = Math.max(0, Math.min(0.95, (ev.clientY - r.top) / r.height));
    return { x: x, y_from_top: y };
  }

  function applyBoxStyle(box, f) {
    const y = f.y_from_top != null ? f.y_from_top : f.y || 0;
    box.style.left = (f.x || 0) * 100 + "%";
    box.style.top = y * 100 + "%";
    box.style.width = (f.w || 0.28) * 100 + "%";
    box.style.height = (f.h || 0.04) * 100 + "%";
  }

  function hideMenu() {
    menu.style.display = "none";
    menu.innerHTML = "";
  }

  function emit(obj) {
    const payload = Object.assign({ t: Date.now() }, obj);
    // Dual keys so Python can accept op or action
    if (payload.op && !payload.action) payload.action = payload.op;
    if (payload.action && !payload.op) payload.op = payload.action;
    sendValue(payload);
  }

  function armSuppressClick() {
    // Field pointerdown / drag must never also fire overlay left-click place.
    suppressClick = true;
    setTimeout(function () {
      suppressClick = false;
    }, 160);
  }

  function commitDrag() {
    if (!drag) return;
    const f = fields.find(function (x) {
      return x.id === drag.id;
    });
    const moved = drag.moved;
    drag = null;
    armSuppressClick();
    if (!f || !moved) return;
    emit({
      op: "update",
      id: f.id,
      x: f.x,
      y_from_top: f.y_from_top,
      w: f.w,
      h: f.h,
    });
  }

  function onDragMove(ev) {
    if (!drag) return;
    const r = overlay.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const dx = (ev.clientX - drag.sx) / r.width;
    const dy = (ev.clientY - drag.sy) / r.height;
    if (Math.abs(dx) > 0.002 || Math.abs(dy) > 0.002) drag.moved = true;
    const f = fields.find(function (x) {
      return x.id === drag.id;
    });
    if (!f) return;
    if (drag.mode === "move") {
      f.x = Math.max(0, Math.min(0.95, drag.ox + dx));
      f.y_from_top = Math.max(0, Math.min(0.95, drag.oy + dy));
    } else {
      f.w = Math.max(0.05, Math.min(0.9, drag.ow + dx));
      f.h = Math.max(0.02, Math.min(0.2, drag.oh + dy));
    }
    const box = overlay.querySelector('.lt-field[data-id="' + f.id + '"]');
    if (box) applyBoxStyle(box, f);
  }

  function startDrag(ev, f, mode) {
    ev.preventDefault();
    ev.stopPropagation();
    hideMenu();
    drag = {
      id: f.id,
      mode: mode,
      sx: ev.clientX,
      sy: ev.clientY,
      ox: f.x,
      oy: f.y_from_top,
      ow: f.w,
      oh: f.h,
      moved: false,
    };
    try {
      if (ev.currentTarget && ev.pointerId != null) {
        ev.currentTarget.setPointerCapture(ev.pointerId);
      }
    } catch (e) {}
  }

  function menuRow(label, onPick) {
    const row = document.createElement("div");
    row.className = "row";
    row.setAttribute("role", "button");
    row.textContent = label;
    function fire(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      hideMenu();
      onPick();
    }
    // pointerdown: click can be swallowed after contextmenu in iframes
    row.addEventListener("pointerdown", fire);
    row.addEventListener("mousedown", fire);
    return row;
  }

  function placeMenu(ev) {
    menu.style.display = "block";
    const r = stage.getBoundingClientRect();
    const mw = 168;
    const mh = 140;
    let left = ev.clientX - r.left;
    let top = ev.clientY - r.top;
    if (left + mw > r.width) left = Math.max(0, r.width - mw);
    if (top + mh > r.height) top = Math.max(0, r.height - mh);
    menu.style.left = left + "px";
    menu.style.top = top + "px";
  }

  function showAddMenu(ev, pos) {
    menu.innerHTML = "";
    placeMenu(ev);
    [
      { t: "text", label: "Add text" },
      { t: "date", label: "Add date" },
      { t: "sign", label: "Add sign" },
    ].forEach(function (item) {
      menu.appendChild(
        menuRow(item.label, function () {
          // CRITICAL: setComponentValue — not parent Apply bridge
          emit({
            op: "add",
            type: item.t,
            page: PAGE,
            x: pos.x,
            y: pos.y_from_top,
            y_from_top: pos.y_from_top,
            w: DEF_W,
            h: DEF_H,
            label: item.label.replace("Add ", ""),
            value: "",
            color: "#111827",
          });
        })
      );
    });
  }

  function showFieldMenu(ev, f) {
    menu.innerHTML = "";
    placeMenu(ev);
    if ((f.type || "text") === "text") {
      menu.appendChild(
        menuRow("Edit text", function () {
          emit({ op: "edit", id: f.id });
        })
      );
    }
    menu.appendChild(
      menuRow("Delete field", function () {
        emit({ op: "delete", id: f.id });
      })
    );
  }

  function renderFields() {
    syncOverlayToImage();
    overlay.innerHTML = "";
    fields.forEach(function (f) {
      const box = document.createElement("div");
      box.className = "lt-field";
      box.dataset.id = f.id;
      const col = typeColor(f.type);
      const ink = f.color || "#111827";
      box.style.border = "2px solid " + col;
      applyBoxStyle(box, f);
      const lbl = document.createElement("span");
      lbl.className = "lbl";
      lbl.textContent = f.label || f.type || "Field";
      lbl.style.color = col;
      box.appendChild(lbl);
      if (f.value) {
        const tw = document.createElement("div");
        tw.className = "tw";
        tw.textContent = f.value;
        tw.style.color = ink;
        box.appendChild(tw);
      }
      const handle = document.createElement("div");
      handle.className = "lt-resize";
      handle.title = "Drag to resize";
      handle.style.background = col;
      box.appendChild(handle);
      box.addEventListener("pointerdown", function (ev) {
        if (ev.target === handle) return;
        armSuppressClick();
        startDrag(ev, f, "move");
      });
      handle.addEventListener("pointerdown", function (ev) {
        armSuppressClick();
        startDrag(ev, f, "resize");
      });
      // Stop bubble so a click on a box never places a new field.
      box.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
      });
      box.addEventListener("contextmenu", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        showFieldMenu(ev, f);
      });
      overlay.appendChild(box);
    });
    if (pending) {
      const dot = document.createElement("div");
      const py = pending.y_from_top != null ? pending.y_from_top : pending.y;
      dot.className = "pending-dot";
      dot.style.left = pending.x * 100 + "%";
      dot.style.top = py * 100 + "%";
      overlay.appendChild(dot);
    }
  }

  document.addEventListener("pointermove", onDragMove, true);
  document.addEventListener("pointerup", commitDrag, true);
  document.addEventListener("pointercancel", commitDrag, true);
  document.addEventListener("mousemove", onDragMove, true);
  document.addEventListener("mouseup", commitDrag, true);

  menu.addEventListener("pointerdown", function (ev) {
    ev.stopPropagation();
  });
  menu.addEventListener("mousedown", function (ev) {
    ev.stopPropagation();
  });

  overlay.addEventListener("click", function (ev) {
    if (drag || suppressClick) return;
    hideMenu();
    const pos = fracFromEvent(ev);
    pending = pos;
    renderFields();
    // Left-click: place currently selected type at click (Python also handles)
    emit({
      op: "add",
      type: NEXT_TYPE || "text",
      page: PAGE,
      x: pos.x,
      y: pos.y_from_top,
      y_from_top: pos.y_from_top,
      w: DEF_W,
      h: DEF_H,
      label:
        NEXT_TYPE === "date" ? "Date" : NEXT_TYPE === "sign" ? "Sign" : "Text",
      value: "",
      color: "#111827",
      from: "left_click",
    });
  });

  overlay.addEventListener("contextmenu", function (ev) {
    ev.preventDefault();
    const pos = fracFromEvent(ev);
    pending = pos;
    renderFields();
    showAddMenu(ev, pos);
  });

  function resizeFrame() {
    syncOverlayToImage();
    const h = stage.offsetHeight + 36;
    Streamlit.setFrameHeight(Math.max(200, h));
  }

  img.onload = function () {
    renderFields();
    resizeFrame();
  };
  window.addEventListener("resize", function () {
    syncOverlayToImage();
    resizeFrame();
  });

  function onRender(event) {
    const args = (event.detail && event.detail.args) || {};
    PAGE = parseInt(args.page, 10) || 0;
    DEF_W = typeof args.def_w === "number" ? args.def_w : 0.28;
    DEF_H = typeof args.def_h === "number" ? args.def_h : 0.04;
    NEXT_TYPE = String(args.next_type || "text").toLowerCase();
    fields = Array.isArray(args.fields) ? args.fields : [];
    fields.forEach(function (f) {
      if (f) {
        if (f.value == null) f.value = "";
        if (!f.color) f.color = "#111827";
      }
    });
    const src = args.src || "";
    if (src && src !== lastSrc) {
      lastSrc = src;
      img.src = src;
    } else {
      renderFields();
      resizeFrame();
    }
    if (typeof args.height === "number" && args.height > 0) {
      Streamlit.setFrameHeight(args.height);
    }
  }

  Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
  Streamlit.setComponentReady();
  Streamlit.setFrameHeight(420);
})();
