/* The scroll system. One script, one IntersectionObserver, one requestAnimationFrame loop for every page.
   It reads the data-fx vocabulary (see docs/ARCHITECTURE.md, "Scroll system"):
     rise      one block comes in once, as it nears the screen
     cascade   each direct child of the parent comes in once, in turn (the first 8 of a batch are staggered)
     count     a number counts up once, inside a box as wide as its final figure
     pin       a tall section holds a scene on screen; --p (0 to 1) says how far through it the reader is
     parallax  a few pixels of drift against the scroll (--py, -1 to 1)
   For rise, cascade and count the script only adds .is-in; for pin and parallax it writes custom properties; the
   stylesheet does the rest with transform and opacity.
   It starts only if reduced motion is off and IntersectionObserver exists, and only then puts fx-on on <html>,
   which is the one class the stylesheet's hidden states depend on. Whatever is already on screen at that moment is
   revealed in the same step, so nothing flashes. A focused element is never left hidden. The scroll and resize
   listeners are passive, the loop stops while the tab is hidden or there is nothing to do, and everything is undone
   on pagehide. Admin and error pages (data-page="none") do not run it at all. */
(() => {
  "use strict";
  const body = document.body;
  const page = body && body.dataset.page;
  if (!page || page === "none") return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!("IntersectionObserver" in window)) return;

  const root = document.documentElement;
  const header = document.querySelector(".site-header");
  const bar = page === "browse" ? document.querySelector(".fx-progress") : null;   // --sp goes on this one node, never on <html>: a custom
                                                                               // property on the root makes the browser restyle every element per frame
  const clamp = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));
  const live = new Set();            // pins and parallax elements that are on screen
  const settle = new Set();          // ones that just left: one last measurement puts them at 0 or 1
  const counting = [];               // counters that are counting up right now
  let raf = 0, docH = 0, condensed = false;

  function put(el, name, value) {    // write a number only when it changed enough to matter
    const v = typeof value === "number" ? value.toFixed(3) : value;
    if (el.__v && el.__v[name] === v) return;
    (el.__v = el.__v || {})[name] = v;
    el.style.setProperty(name, v);
  }

  // ---- one-shot pieces: rise, cascade children, count --------------------------------------------------------
  function startCount(el) {
    const out = el.querySelector(".cnt-live"), n = +el.dataset.to;
    el.__done = true;
    if (!out || !(n > 0)) return;
    out.textContent = "0";
    counting.push({ out, n, t0: performance.now() });
    schedule();
  }
  function reveal(el, i, instant) {
    if (instant) el.classList.add("is-instant");         // no fade (or end one under way): focus must never land in something faint
    if (el.__done || el.classList.contains("is-in")) return;
    if (el.dataset.fx === "count") return startCount(el);
    if (i !== undefined) put(el, "--i", String(Math.min(i, 7)));
    el.classList.add("is-in");
  }

  // ---- scenes: pin and parallax ---------------------------------------------------------------------------------
  function pin(sec) {
    const stage = sec.querySelector(".fx-stage");
    const moving = [...sec.querySelectorAll(".fx-move")];
    let stuck = false, top = 0, stale = true;
    return {
      el: sec, moving,
      measure() {
        if (stale) {
          stuck = !!stage && getComputedStyle(stage).position === "sticky";
          top = header && getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0;
          stale = false;
        }
        const r = sec.getBoundingClientRect();
        // pinned: how far through the taller section; not pinned (phones, .pin-soft): how far the section has come up the screen
        const p = stuck ? (top - r.top) / Math.max(1, sec.offsetHeight - stage.offsetHeight) : (0.9 * (window.innerHeight || 1) - r.top) / (0.6 * (window.innerHeight || 1));
        return { p, top };
      },
      apply({ p, top: t }) { if (sec.__top !== t) { sec.__top = t; sec.style.setProperty("--fx-top", t + "px"); } put(sec, "--p", clamp(p)); },
      stale() { stale = true; },
    };
  }
  function drift(el) {
    return {
      el, moving: [],
      measure(vh) { const r = el.getBoundingClientRect(); return clamp(((r.top + r.height / 2) - vh / 2) / (vh / 2 + r.height / 2), -1, 1); },
      apply(v) { put(el, "--py", v); },
      stale() {},
    };
  }

  // ---- collect everything ----------------------------------------------------------------------------------------
  const vh0 = window.innerHeight || 1;
  const rises = [...document.querySelectorAll('[data-fx="rise"], [data-fx="count"]')];
  const parents = [...document.querySelectorAll('[data-fx="cascade"]')];
  const scenes = new Map();
  document.querySelectorAll('[data-fx="pin"]').forEach((el) => scenes.set(el, pin(el)));
  document.querySelectorAll('[data-fx="parallax"]').forEach((el) => scenes.set(el, drift(el)));

  // counters wait at zero until they come in; what is already on screen is revealed now, before fx-on, so it never hides
  const waiting = [];
  const arrive = (el, i) => { if (el.getBoundingClientRect().top < vh0 * 0.94) reveal(el, i); else waiting.push(el); };
  rises.forEach((el) => { if (el.dataset.fx === "count") el.querySelector(".cnt-live").textContent = "0"; arrive(el); });
  parents.forEach((parent) => [...parent.children].forEach((child, n) => arrive(child, n)));
  root.classList.add("fx-on");
  scenes.forEach((s) => { s.apply(s.measure(vh0)); s.stale(); });

  // ---- the one observer ------------------------------------------------------------------------------------------
  const io = new IntersectionObserver((entries) => {
    let i = 0;
    entries.forEach((e) => {
      const el = e.target, scene = scenes.get(el);
      if (scene) {
        if (e.isIntersecting) { live.add(scene); scene.moving.forEach((m) => m.classList.add("is-animating")); }
        else { live.delete(scene); settle.add(scene); scene.moving.forEach((m) => m.classList.remove("is-animating")); }
      } else if (e.isIntersecting) { reveal(el, i++); io.unobserve(el); }
    });
    schedule();
  }, { rootMargin: "0px 0px -6% 0px" });
  waiting.forEach((el) => io.observe(el));
  scenes.forEach((s, el) => io.observe(el));

  // ---- the loop --------------------------------------------------------------------------------------------------
  function frame(now) {
    raf = 0;
    const vh = window.innerHeight || 1, y = window.pageYOffset || 0;
    const work = [...live, ...settle];
    settle.clear();
    const measured = work.map((s) => s.measure(vh));                 // all reads first
    if (bar) docH = root.scrollHeight;
    work.forEach((s, i) => s.apply(measured[i]));                    // then all writes
    if (header && (y > 40) !== condensed) { condensed = y > 40; header.classList.toggle("is-condensed", condensed); }
    if (bar) put(bar, "--sp", clamp(y / Math.max(1, docH - vh)));
    for (let i = counting.length - 1; i >= 0; i--) {
      const c = counting[i], t = clamp((now - c.t0) / 900);
      c.out.textContent = String(Math.round(c.n * (1 - Math.pow(1 - t, 3))));
      if (t >= 1) counting.splice(i, 1);
    }
    if (counting.length) schedule();
  }
  function schedule() { if (!raf && !document.hidden) raf = requestAnimationFrame(frame); }

  const onResize = () => { scenes.forEach((s) => s.stale()); schedule(); };
  const onVisible = () => { if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else schedule(); };
  // a focused element is never left hidden: bring in every fx ancestor, and show a pinned scene whole
  const onFocus = (e) => {
    for (let n = e.target.closest ? e.target.closest("[data-fx]") : null; n; n = n.parentElement && n.parentElement.closest("[data-fx]")) {
      if (n.dataset.fx === "pin") n.classList.add("is-focus"); else reveal(n, undefined, true);
    }
    for (let n = e.target; n && n !== root; n = n.parentElement) {
      if (n.parentElement && n.parentElement.dataset && n.parentElement.dataset.fx === "cascade") reveal(n, 0, true);
    }
  };
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", onResize, { passive: true });
  document.addEventListener("visibilitychange", onVisible);
  document.addEventListener("focusin", onFocus);
  window.addEventListener("pagehide", () => {
    io.disconnect(); cancelAnimationFrame(raf); raf = 0; live.clear(); settle.clear(); counting.length = 0;
    window.removeEventListener("scroll", schedule); window.removeEventListener("resize", onResize);
    document.removeEventListener("visibilitychange", onVisible); document.removeEventListener("focusin", onFocus);
  }, { once: true });
  schedule();
})();
