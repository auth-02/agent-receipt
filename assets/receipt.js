/* Auto-scroll the page in lockstep with the print animation, so the receipt
   feeds out of view like paper off a printer. Reads the real animation timing
   from the CSS (honouring the --pr print speed), scrolls from top to bottom
   over that span, and bows out the moment the reader scrolls by hand. */
(function () {
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  function run() {
    var maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    if (maxScroll <= 0) return;

    // Total animation span = latest (delay + active duration) on the sheet.
    var endMs = 0;
    var anims = document.getAnimations ? document.getAnimations() : [];
    for (var i = 0; i < anims.length; i++) {
      try {
        var t = anims[i].effect.getComputedTiming();
        var e = (t.delay || 0) + (t.activeDuration || 0);
        if (e > endMs) endMs = e;
      } catch (err) { /* ignore */ }
    }
    if (!endMs) endMs = 4000;

    var cancelled = false;
    function stop() { cancelled = true; }
    ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (ev) {
      window.addEventListener(ev, stop, { passive: true, once: true });
    });

    var start = performance.now();
    (function step(now) {
      if (cancelled) return;
      var frac = (now - start) / endMs;
      if (frac > 1) frac = 1;
      window.scrollTo(0, (document.documentElement.scrollHeight - window.innerHeight) * frac);
      if (frac < 1) requestAnimationFrame(step);
    })(start);
  }

  if (document.readyState === "complete") run();
  else window.addEventListener("load", run);
})();
