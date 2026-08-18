/* Agent Receipt viewer behaviour.

   The printer is a fixed header and the paper hangs from it inside a fixed
   clipping window. A receipt taller than the screen drapes off the bottom; the
   user moves it by DRAGGING (or the wheel), the way you would pull a physical
   receipt — there is no scrollbar and the page never scrolls.

   The receipt is intentionally self-contained: in the native viewer the close
   message is bridged to AppKit; in a browser we try window.close(). */
(function () {
  function closeReceipt() {
    try {
      if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.close) {
        window.webkit.messageHandlers.close.postMessage("close");
        return;
      }
    } catch (e) {}
    try { window.close(); } catch (e) {}
  }

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  function run() {
    var closeBtn = document.querySelector("[data-receipt-close]");
    if (closeBtn) closeBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      closeReceipt();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); closeReceipt(); }
    });

    var stage = document.querySelector(".stage");
    var wrap = document.querySelector(".paperwrap");
    var roll = document.querySelector(".paper-roll");
    if (!stage || !wrap || !roll) return;

    var reduce = false;
    try { reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

    // --- Pan state ---------------------------------------------------------
    // pan is the paper's vertical offset in px. 0 = fully "printed out" resting
    // position; more negative pulls the paper up to reveal lower content.
    var pan = 0, minPan = 0, maxPan = 0, draggable = false;
    var mode = "idle", raf = null, vel = 0, target = 0;
    // Panning is locked until the print reveal finishes, so a drag never fights
    // the paper feeding out. Closing still works during printing.
    var ready = reduce;

    function apply() { roll.style.setProperty("--pan", pan.toFixed(2) + "px"); }

    function measure() {
      // Rest top of the roll = its current on-screen top minus whatever pan is
      // applied. Robust to the negative leader margin and any current drag.
      var restTop = roll.getBoundingClientRect().top - pan;
      var overflow = (restTop + roll.offsetHeight) - (window.innerHeight - 64);
      minPan = overflow > 0 ? -overflow : 0;
      maxPan = 0;
      // Always draggable: even a short receipt can be pulled to feed the blank
      // leader out of the slot, and it springs back.
      draggable = true;
      // Keep the 3D bend only while the whole strip fits; long receipts hang flat.
      roll.classList.toggle("is-flat", overflow > 0);
      pan = clamp(pan, minPan, maxPan);
      target = clamp(target, minPan, maxPan);
      apply();
    }

    // Both ends rubber-band: pulling DOWN past rest feeds the blank leader out of
    // the printer, pulling UP past the tail gives a little travel — both spring
    // back. Resistance keeps the overscroll from running away.
    function rubber(v) {
      if (v > maxPan) return maxPan + (v - maxPan) * 0.28;
      if (v < minPan) return minPan + (v - minPan) * 0.28;
      return v;
    }

    function stopAnim() { if (raf) { cancelAnimationFrame(raf); raf = null; } mode = "idle"; }

    function tick() {
      if (mode === "inertia") {
        pan += vel * 16;
        vel *= 0.92;
        // Spring back from either overscrolled end.
        if (pan > maxPan) { pan += (maxPan - pan) * 0.25; vel *= 0.5; }
        else if (pan < minPan) { pan += (minPan - pan) * 0.25; vel *= 0.5; }
        apply();
        if (Math.abs(vel) < 0.02 && pan >= minPan - 0.5 && pan <= maxPan + 0.5) {
          pan = clamp(pan, minPan, maxPan); apply(); stopAnim(); return;
        }
      } else if (mode === "ease") {
        pan += (target - pan) * 0.2;
        apply();
        if (Math.abs(target - pan) < 0.3) { pan = target; apply(); stopAnim(); return; }
      } else { raf = null; return; }
      raf = requestAnimationFrame(tick);
    }
    function startAnim() { if (!raf) raf = requestAnimationFrame(tick); }

    // --- Pointer drag ------------------------------------------------------
    var down = false, moved = false, downTarget = null;
    var startY = 0, startX = 0, startPan = 0, lastY = 0, lastT = 0, pid = null;

    function now() { try { return performance.now(); } catch (e) { return 0; } }

    stage.addEventListener("pointerdown", function (e) {
      if (e.target.closest("[data-receipt-close]") || e.target.closest(".actions") ||
          e.target.closest("[data-copy]")) return;
      down = true; moved = false; downTarget = e.target;
      startY = lastY = e.clientY; startX = e.clientX; startPan = pan;
      lastT = now(); pid = e.pointerId;
      stopAnim(); vel = 0;
      try { stage.setPointerCapture(pid); } catch (err) {}
    });

    stage.addEventListener("pointermove", function (e) {
      if (!down) return;
      var dy = e.clientY - startY;
      if (!moved && (Math.abs(dy) > 4 || Math.abs(e.clientX - startX) > 4)) {
        moved = true;
        if (draggable) { wrap.classList.add("is-grabbing"); document.body.style.userSelect = "none"; }
      }
      if (!moved || !draggable || !ready) return;
      pan = rubber(startPan + dy);
      apply();
      var t = now(), dt = t - lastT;
      if (dt > 0) vel = (e.clientY - lastY) / dt;   // px per ms
      lastY = e.clientY; lastT = t;
    });

    function endDrag(e) {
      if (!down) return;
      down = false;
      try { stage.releasePointerCapture(pid); } catch (err) {}
      wrap.classList.remove("is-grabbing");
      document.body.style.userSelect = "";
      if (!moved) {
        // A genuine click. Close only when it lands on the backdrop, never on
        // the receipt itself, the printer, or the close button.
        if (downTarget && !downTarget.closest(".paper-roll") &&
            !downTarget.closest(".printer") && !downTarget.closest("[data-receipt-close]")) {
          closeReceipt();
        }
        return;
      }
      if (!draggable || !ready) return;
      if (reduce) { pan = clamp(pan, minPan, maxPan); apply(); return; }
      vel = clamp(vel, -2.5, 2.5);
      mode = "inertia"; startAnim();
    }
    stage.addEventListener("pointerup", endDrag);
    stage.addEventListener("pointercancel", endDrag);

    // --- Wheel (still moves the paper, not a page scroll) ------------------
    stage.addEventListener("wheel", function (e) {
      if (!draggable || !ready) return;
      e.preventDefault();
      if (reduce) { pan = clamp(pan - e.deltaY, minPan, maxPan); apply(); return; }
      var base = (mode === "ease") ? target : pan;
      target = clamp(base - e.deltaY, minPan, maxPan);
      mode = "ease"; startAnim();
    }, { passive: false });

    // --- Pull-to-feed ------------------------------------------------------
    // Dragging inside the top/bottom edge zones reels a blank strip out of the
    // roll (resistance builds as if the roll is running out), then springs it
    // back on release. Separate from panning — the zones stop propagation so
    // the stage never starts a pan for the same gesture.
    var MAX_FEED = 260, TEAR_AT = 70;
    var lead = roll.querySelector("[data-lead]");
    var extra = roll.querySelector("[data-extra]");
    var tear = roll.querySelector("[data-tear]");
    var slot = document.querySelector(".printer-slot");

    // A small transient toast, matching the design's pull-to-feed feedback.
    var toastEl = null, toastTimer = null;
    function flash(msg) {
      if (!toastEl) {
        toastEl = document.createElement("div");
        toastEl.className = "ar-toast";
        (stage || document.body).appendChild(toastEl);
      }
      toastEl.textContent = msg;
      toastEl.classList.add("is-shown");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { toastEl.classList.remove("is-shown"); }, 1900);
    }

    function bindPull(zone, strip, isBottom) {
      if (!zone || !strip) return;
      zone.addEventListener("pointerdown", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var startY = e.clientY;
        var base = strip.offsetHeight;
        strip.style.transition = "none";
        roll.classList.add("is-grabbing");
        if (slot) slot.style.filter = "brightness(1.4)";
        try { zone.setPointerCapture(e.pointerId); } catch (err) {}

        function move(ev) {
          var dy = Math.max(0, ev.clientY - startY + base);
          var fed = MAX_FEED * (1 - Math.exp(-dy / MAX_FEED));
          strip.style.height = fed.toFixed(1) + "px";
          if (isBottom && tear) {
            tear.style.opacity = String(Math.max(0, Math.min(1, (fed - TEAR_AT) / 46)));
          }
        }
        function up() {
          zone.removeEventListener("pointermove", move);
          zone.removeEventListener("pointerup", up);
          zone.removeEventListener("pointercancel", up);
          roll.classList.remove("is-grabbing");
          if (slot) slot.style.filter = "";
          var fed = strip.offsetHeight;
          strip.style.transition = "height .9s cubic-bezier(.16,1,.3,1)";
          strip.style.height = "0px";
          if (tear) { tear.style.transition = "opacity .3s ease"; tear.style.opacity = "0"; }
          if (fed >= TEAR_AT) {
            flash(isBottom ? "Paper fed. Nothing to tear — it's digital." : "Fed from the roll.");
          }
        }
        zone.addEventListener("pointermove", move);
        zone.addEventListener("pointerup", up);
        zone.addEventListener("pointercancel", up);
      });
    }
    bindPull(document.querySelector(".pull-top"), lead, false);
    bindPull(document.querySelector(".pull-bottom"), extra, true);

    // --- Action buttons (Save · Print again) -------------------------------
    function nativeSaveImage() {
      try {
        return window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.saveImage;
      } catch (err) { return null; }
    }
    function saveReceipt() {
      if (nativeSaveImage()) {
        // Hide the chrome, let it paint, then ask the native viewer to snapshot
        // the receipt and open a Save panel so the user picks any location.
        stage.classList.add("exporting");
        flash("Choose where to save the image…");
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            try { window.webkit.messageHandlers.saveImage.postMessage("save"); } catch (err) {}
            setTimeout(function () { stage.classList.remove("exporting"); }, 900);
          });
        });
        return;
      }
      // Browser fallback: no native snapshot bridge — save a standalone HTML copy.
      try {
        var html = "<!DOCTYPE html>\n" + document.documentElement.outerHTML;
        var blob = new Blob([html], { type: "text/html" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "agent-receipt.html";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
        flash("Receipt saved.");
      } catch (err) { flash("Save unavailable here."); }
    }
    function reprint() {
      pan = 0; apply(); stopAnim();
      var pr = parseFloat(getComputedStyle(stage).getPropertyValue("--pr")) || 1;
      var anims = [];
      try { anims = roll.getAnimations({ subtree: true }); } catch (err) {}
      anims.forEach(function (a) { try { a.cancel(); a.play(); } catch (err) {} });
      ready = false;
      setTimeout(function () { ready = true; measure(); }, reduce ? 0 : Math.round(4.2 * pr * 1000) + 150);
    }
    // --- Copy the resume command -------------------------------------------
    function copyText(text) {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(
            function () { flash("Copied: " + text); },
            function () { legacyCopy(text); }
          );
          return;
        }
      } catch (err) {}
      legacyCopy(text);
    }
    function legacyCopy(text) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        var ok = document.execCommand("copy");
        ta.remove();
        flash(ok ? "Copied: " + text : "Copy blocked — select it manually");
      } catch (err) { flash("Copy blocked — select it manually"); }
    }
    var copyEl = roll.querySelector("[data-copy]");
    if (copyEl) copyEl.addEventListener("click", function (e) {
      e.preventDefault();
      copyText(copyEl.textContent.trim());
    });

    var actionsBar = stage.querySelector(".actions");
    if (actionsBar) actionsBar.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-action]");
      if (!btn) return;
      var act = btn.getAttribute("data-action");
      if (act === "save") saveReceipt();
      else if (act === "reprint") reprint();
    });

    // --- Measure now and whenever the layout can change --------------------
    measure();
    window.addEventListener("resize", measure);
    // The print reveal is clip-path only (no layout change), so heights are
    // stable immediately. Unlock panning (and re-measure) once the paper has
    // finished feeding out — matches the .paper ar-feed duration (4.2s * --pr).
    var pr = parseFloat(getComputedStyle(stage).getPropertyValue("--pr")) || 1;
    setTimeout(function () { ready = true; measure(); }, reduce ? 0 : Math.round(4.2 * pr * 1000) + 150);
  }

  if (document.readyState === "complete") run();
  else window.addEventListener("load", run);
})();
