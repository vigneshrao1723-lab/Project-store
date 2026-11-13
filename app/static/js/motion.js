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
  // the loader out at about 1.0s; this only counts up the percentage, then removes the class (display: none).
  function runLoader() {
    const loader = document.querySelector("[data-loader]");
    const pct = loader && loader.querySelector("[data-loader-pct]");
    if (!pct) return;
    const DURATION = 1000;
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

  // ---- category interactions ----------------------------------------------------------------------------------
  // One card at a time is "active": the pointer is over it (fine pointers only), it has keyboard focus, or a pointer
  // is pressed on it. .is-active is the only thing this file sets; the CSS draws everything. Nothing here ever
  // calls preventDefault or delays a click: links and forms behave exactly as without this file.
  const media = (q) => (window.matchMedia ? window.matchMedia(q) : { matches: false, addEventListener() {} });
  const calm = media("(prefers-reduced-motion: reduce)");
  const finePointer = media("(hover: hover) and (pointer: fine)");
  const CARDS = '[data-motion="tile"], [data-motion="hero-plate"], [data-motion="plate"]';
  const PRESSABLE = '[data-press], [data-motion="tile"]';
  const ctl = new AbortController();
  const opts = { signal: ctl.signal };
  let active = null;
  let pressed = null;

  const focusVisible = (el) => { try { return el.matches(":focus-visible"); } catch (_) { return true; } };
  const cardOf = (node) => {
    if (!node || !node.closest) return null;
    const own = node.closest(CARDS);
    if (own) return own;
    // keyboard focus inside the purchase box plays the product plate's motif (the box itself never moves)
    return node.closest('[data-motion="buybox"]') ? document.querySelector('[data-motion="plate"]') : null;
  };
  const sameGroup = (card, node) => !!node && (card.contains(node) || cardOf(node) === card);

  // will-change only while the cover is actually transitioning
  function flagAnimating(el) {
    const cover = el.querySelector(".cover");
    if (!cover) return;
    cover.classList.add("is-animating");
    const done = (e) => {
      if (e.target !== cover || e.propertyName !== "transform") return;
      cover.classList.remove("is-animating");
      cover.removeEventListener("transitionend", done);
    };
    cover.addEventListener("transitionend", done);
  }
  function setActive(el, on) { flagAnimating(el); el.classList.toggle("is-active", on); }
  function activate(el) {
    if (calm.matches || active === el || !el.querySelector(".fx-panel")) return;   // sold-out tiles have no panel and stay quiet
    deactivate();
    active = el;
    setActive(el, true);
  }
  function deactivate() {
    if (!active) return;
    const el = active;
    active = null;
    setActive(el, false);
  }

  document.addEventListener("pointerover", (e) => {
    if (e.pointerType === "touch" || !finePointer.matches) return;
    const card = cardOf(e.target);
    if (card) activate(card);
  }, opts);
  document.addEventListener("pointerout", (e) => {
    if (e.pointerType === "touch") return;
    const card = cardOf(e.target);
    if (!card || card !== active || sameGroup(card, e.relatedTarget)) return;
    if (card.contains(document.activeElement) && focusVisible(document.activeElement)) return;   // keyboard focus keeps it
    deactivate();
  }, opts);
  document.addEventListener("focusin", (e) => {
    if (!e.target.matches || !focusVisible(e.target)) return;
    const card = cardOf(e.target);
    if (card) activate(card);
  }, opts);
  document.addEventListener("focusout", (e) => {
    const card = cardOf(e.target);
    if (card && card === active && !sameGroup(card, e.relatedTarget)) deactivate();
  }, opts);
  document.addEventListener("pointerdown", (e) => {
    if (e.button > 0) return;
    const press = e.target.closest ? e.target.closest(PRESSABLE) : null;
    if (press && !calm.matches) { press.classList.add("is-pressed"); pressed = press; }
    const card = cardOf(e.target);
    if (card) activate(card);
  }, opts);
  const release = (e) => {
    if (pressed) { pressed.classList.remove("is-pressed"); pressed = null; }
    if (e.pointerType === "touch") deactivate();                         // no hover on touch: rest when the finger lifts
  };
  document.addEventListener("pointerup", release, opts);
  document.addEventListener("pointercancel", release, opts);             // a scroll gesture cancels the press
  calm.addEventListener("change", () => { if (calm.matches) deactivate(); }, opts);
  cleanups.push(() => { ctl.abort(); deactivate(); if (pressed) pressed.classList.remove("is-pressed"); });
})();
