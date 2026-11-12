/* Project Store motion layer. Progressive enhancement only: every page works and reads the same without it.
   No timers: the loader is paced by requestAnimationFrame and CSS animation events, and everything this file
   starts is cancelled on pagehide. */
(() => {
  "use strict";

  const root = document.documentElement;
  const cleanups = [];
  window.addEventListener("pagehide", () => { cleanups.splice(0).forEach((fn) => fn()); }, { once: true });

  // ---- intro loader -------------------------------------------------------------------------------------------
  // motion-boot.js adds .intro-run to <html> on the first page of a session. The CSS plays the scene and fades
  // the loader out at about 1.2s; this only counts up the percentage, then removes the class (display: none).
  function runLoader() {
    const loader = document.querySelector("[data-loader]");
    const pct = loader && loader.querySelector("[data-loader-pct]");
    if (!pct) return;
    const DURATION = 1180;
    const start = performance.now();
    let frame = 0;
    const finish = () => { cancelAnimationFrame(frame); root.classList.remove("intro-run"); };
    const tick = (now) => {
      const t = Math.min(1, (now - start) / DURATION);
      pct.textContent = String(Math.round((1 - Math.pow(1 - t, 2.2)) * 100));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    // animationend bubbles up from the scene's own animations, so only the loader's own exit counts
    const onEnd = (e) => {
      if (e.target !== loader || e.animationName !== "loader-out") return;
      loader.removeEventListener("animationend", onEnd);
      finish();
    };
    loader.addEventListener("animationend", onEnd);
    cleanups.push(() => cancelAnimationFrame(frame));
  }

  if (root.classList.contains("intro-run")) runLoader();
})();
