/* The scroll system. One script, one IntersectionObserver, one requestAnimationFrame loop for every page.
   It reads the data-fx vocabulary (see docs/ARCHITECTURE.md, "Scroll system"):
     rise from-left from-right zoom flip clip    one block comes in once, as it nears the screen
     cascade                                     each direct child of the parent comes in once, in turn
     words lines                                 a text block comes in word by word / line by line
     count                                       a number counts up once, inside a box as wide as its final figure
     pin hscroll                                 a tall section holds a scene (or a sideways shelf) on screen; --p says how far
     parallax draw                               a few pixels of drift (--py) / a line that draws as you scroll (--d)
     tilt magnetic                               pointer feedback on fine pointers only
   For the one-shot words the script only adds .is-in; for scenes it writes custom properties; the stylesheet does the
   rest with transform, opacity, clip-path and stroke-dashoffset.
   It starts only if reduced motion is off and IntersectionObserver exists, and only then puts fx-on on <html>, the one
   class the stylesheet's hidden states depend on. Whatever is already on screen at that moment is revealed in the same
   step, so nothing flashes. A focused element is never left hidden. The scroll and resize listeners are passive, the
   loop stops while the tab is hidden or there is nothing to do, and everything is undone on pagehide. Error pages
   (data-page="none") do not run it; admin pages run only the one-shot words (no scenes, no pointer effects). */
(() => {
  "use strict";
  // TO TURN AN EFFECT OFF: list its name here, e.g. ["tilt", "magnetic", "toasts"]. A data-fx word is then treated as
  // already in place; every name also becomes an fx-off-<name> class on <html>, which the stylesheets and fx-ui.js
  // check for the effects that are not data-fx words. One list for the whole site. The names are in docs/ARCHITECTURE.md:
  //   words:   rise from-left from-right zoom flip clip lines words count cascade pin hscroll parallax draw tilt magnetic marquee
  //   others:  rail stepper inputs shake toasts cart downloads forms drift bob timeline focus-ring press wipe lift
  const OFF = [];
  // The same list can come from the server: app/fx.json is written into <html data-fx-off="...">. Both are merged.
  ((document.documentElement.dataset && document.documentElement.dataset.fxOff) || "").split(/\s+/).forEach((n) => { if (n && OFF.indexOf(n) < 0) OFF.push(n); });
  OFF.forEach((n) => document.documentElement.classList.add("fx-off-" + n));

  const body = document.body;
  const page = body && body.dataset.page;
  if (!page || page === "none") return;
  if (page === "admin" && OFF.indexOf("admin-motion") >= 0) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!("IntersectionObserver" in window)) return;

  const root = document.documentElement;
  // adaptive quality: a weak device (few cores, little memory, or measured under 45 fps for half a second) gets fx-lite,
  // which turns off only the heaviest effects (pinned sticky stages become scroll-linked, the sideways shelf becomes a
  // swipe row, big parallax stops). ?fx=lite or ?fx=full in the address forces either way, for testing.
  const forced = /[?&]fx=(lite|full)\b/.exec(window.location.search || "");
  const lite = forced ? forced[1] === "lite" : (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4;
  if (lite) root.classList.add("fx-lite");
  let probing = !lite && !forced && !document.hidden, probeN = 0, probeT0 = 0;

  const scenic = page !== "admin";                 // admin pages get the one-shot words only
  const header = document.querySelector(".site-header");
  const bar = page === "browse" ? document.querySelector(".fx-progress") : null;   // --sp goes on this one node, never on <html>:
  const rail = page === "browse" ? document.querySelector(".rail") : null;         // a custom property on the root makes the browser restyle everything per frame
  const clamp = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));
  // tuning knobs set in fx-tuning.css (--tilt-max in degrees, --magnet-max in px); read once
  const knob = (name, fallback) => {
    try { const cs = typeof getComputedStyle === "function" ? getComputedStyle(root) : null; const v = cs && cs.getPropertyValue ? parseFloat(cs.getPropertyValue(name)) : NaN; return v >= 0 ? v : fallback; } catch (e) { return fallback; }
  };
  const tiltMax = knob("--tilt-max", 6), magnetMax = knob("--magnet-max", 6);
  const ONE = ["rise", "from-left", "from-right", "zoom", "flip", "clip", "words", "lines", "count"];
  const SCENES = ["pin", "hscroll", "parallax", "draw"];
  const live = new Set();            // scenes that are on screen
  const settle = new Set();          // ones that just left: one last measurement puts them at 0 or 1
  const counting = [];               // counters that are counting up right now
  const cleanups = [];
  let raf = 0, docH = 0, condensed = false;

  function put(el, name, value) {    // write a number only when it changed enough to matter
    const v = typeof value === "number" ? value.toFixed(3) : value;
    if (el.__v && el.__v[name] === v) return;
    (el.__v = el.__v || {})[name] = v;
    el.style.setProperty(name, v);
  }

  // ---- one-shot pieces ----------------------------------------------------------------------------------------
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

  // ---- scenes ----------------------------------------------------------------------------------------------------
  function pin(sec) {
    const stage = sec.querySelector(".fx-stage");
    const track = sec.querySelector(".hs-track");
    const moving = [...sec.querySelectorAll(".fx-move")];
    let stuck = false, top = 0, stale = true;
    return {
      el: sec, moving,
      measure() {
        const vh = window.innerHeight || 1;
        if (stale) {
          stuck = !!stage && getComputedStyle(stage).position === "sticky";
          top = header && getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0;
          if (track && stuck) {                      // a sideways shelf: how far the track travels, and the height that buys
            const shift = Math.max(0, track.scrollWidth - stage.clientWidth);
            sec.style.setProperty("--hs", shift + "px");
            sec.style.setProperty("--hs-h", (stage.offsetHeight + shift) + "px");
          }
          stale = false;
        }
        const r = sec.getBoundingClientRect();
        // pinned: how far through the taller section; not pinned (phones, fx-lite, .pin-soft): how far it has come up the screen
        const p = stuck ? (top - r.top) / Math.max(1, sec.offsetHeight - stage.offsetHeight) : (0.9 * vh - r.top) / (0.6 * vh);
        return { p, top };
      },
      apply({ p, top: t }) {
        if (sec.__top !== t) { sec.__top = t; sec.style.setProperty("--fx-top", t + "px"); }
        put(sec, "--p", clamp(p));
        if (sec.__pre !== p < 0.2) { sec.__pre = p < 0.2; sec.classList.toggle("is-pre", sec.__pre); }       // before the scene starts, its headline is truly hidden
      },
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
  function trace(el) {                               // a drawn line: 0 when the block is entering, 1 when it has mostly passed the middle
    return {
      el, moving: [],
      measure(vh) { const r = el.getBoundingClientRect(); return clamp((0.85 * vh - r.top) / (0.5 * vh + 0.6 * r.height)); },
      apply(v) { put(el, "--d", v); },
      stale() {},
    };
  }

  // ---- collect everything ----------------------------------------------------------------------------------------
  const vh0 = window.innerHeight || 1;
  const all = [...document.querySelectorAll("[data-fx]")];
  const active = (names) => all.filter((el) => names.indexOf(el.dataset.fx) >= 0 && OFF.indexOf(el.dataset.fx) < 0);
  const rises = active(ONE);
  const parents = active(["cascade"]);
  const scenes = new Map();
  if (scenic) {
    active(["pin", "hscroll"]).forEach((el) => scenes.set(el, pin(el)));
    active(["parallax"]).forEach((el) => scenes.set(el, drift(el)));
    active(["draw"]).forEach((el) => scenes.set(el, trace(el)));
  }
  // switched-off variants are simply already in place
  all.filter((el) => OFF.indexOf(el.dataset.fx) >= 0).forEach((el) => {
    if (el.dataset.fx === "cascade") [...el.children].forEach((c) => c.classList.add("is-in")); else el.classList.add("is-in");
  });
  // text blocks: number their words or lines so the stylesheet can stagger them
  rises.forEach((el) => {
    const kids = el.dataset.fx === "words" ? el.querySelectorAll(".w") : el.dataset.fx === "lines" ? el.querySelectorAll(".ln") : [];
    [...kids].forEach((k, i) => put(k, "--i", String(Math.min(i, 29))));
  });

  // counters wait at zero until they come in; what is already on screen is revealed now, before fx-on, so it never hides
  const waiting = [], late = [];
  const arrive = (el, i) => {
    if (el.getBoundingClientRect().top >= vh0 * 0.94) waiting.push(el);
    else if (el.dataset.fx === "words" || el.dataset.fx === "lines") late.push(el);     // a headline on screen at load plays its entrance
    else reveal(el, i);
  };
  rises.forEach((el) => { if (el.dataset.fx === "count") el.querySelector(".cnt-live").textContent = "0"; arrive(el); });
  parents.forEach((parent) => [...parent.children].forEach((child, n) => arrive(child, n)));
  root.classList.add("fx-on");
  if (late.length) { void root.offsetHeight; late.forEach((el) => reveal(el)); }      // hidden state committed first, so the transition runs
  scenes.forEach((s) => { s.apply(s.measure(vh0)); s.stale(); });

  // ---- pointer feedback: fine pointers only, written straight onto the one element under the pointer ------------
  const fine = window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  if (fine && scenic) {
    const on = (el, type, fn) => { el.addEventListener(type, fn); cleanups.push(() => el.removeEventListener(type, fn)); };
    active(["tilt"]).forEach((el) => {              // a few degrees of 3D lean and a flat spotlight disc that follows the pointer
      let r = null;
      on(el, "pointerenter", () => { r = el.getBoundingClientRect(); el.classList.add("is-tilting"); });
      on(el, "pointermove", (e) => {
        r = r || el.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        put(el, "--ry", clamp((x - 0.5) * 2 * tiltMax, -tiltMax, tiltMax)); put(el, "--rx", clamp((0.5 - y) * 2 * tiltMax, -tiltMax, tiltMax));
        put(el, "--mx", e.clientX - r.left + "px"); put(el, "--my", e.clientY - r.top + "px");
      });
      on(el, "pointerleave", () => { r = null; el.classList.remove("is-tilting"); put(el, "--rx", 0); put(el, "--ry", 0); });
    });
    active(["magnetic"]).forEach((el) => {          // a button leans up to 6 px toward the pointer
      let r = null;
      on(el, "pointerenter", () => { r = el.getBoundingClientRect(); });
      on(el, "pointermove", (e) => {
        r = r || el.getBoundingClientRect();
        put(el, "--tx", clamp((e.clientX - (r.left + r.width / 2)) / (r.width / 2), -1, 1) * magnetMax + "px");
        put(el, "--ty", clamp((e.clientY - (r.top + r.height / 2)) / (r.height / 2), -1, 1) * magnetMax + "px");
      });
      on(el, "pointerleave", () => { r = null; put(el, "--tx", "0px"); put(el, "--ty", "0px"); });
    });
  }

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

  // ---- the section rail (home): dots that fill as the sections go by --------------------------------------------
  const sections = rail ? [...document.querySelectorAll("main > section")] : [];
  const dots = rail ? rail.querySelectorAll("li").length : 0;

  // ---- the loop --------------------------------------------------------------------------------------------------
  function frame(now) {
    raf = 0;
    if (probing) {
      probeN++; probeT0 = probeT0 || now;
      if (now - probeT0 >= 500) {
        probing = false;
        if ((probeN * 1000) / (now - probeT0) < 45) { root.classList.add("fx-lite"); scenes.forEach((s) => s.stale()); }
      } else schedule();
    }
    const vh = window.innerHeight || 1, y = window.pageYOffset || 0;
    const work = [...live, ...settle];
    settle.clear();
    const measured = work.map((s) => s.measure(vh));                 // all reads first
    if (bar) docH = root.scrollHeight;
    let rs = -1;
    if (dots && sections.length) {
      rs = 0;
      sections.forEach((s, k) => { const r = s.getBoundingClientRect(); if (r.top <= vh * 0.5) rs = k + clamp((vh * 0.5 - r.top) / Math.max(1, r.height)); });
    }
    work.forEach((s, i) => s.apply(measured[i]));                    // then all writes
    if (header && (y > 40) !== condensed) { condensed = y > 40; header.classList.toggle("is-condensed", condensed); }
    if (bar) put(bar, "--sp", clamp(y / Math.max(1, docH - vh)));
    if (rs >= 0) put(rail, "--rs", Math.min(rs, dots));
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
      if (n.dataset.fx === "pin" || n.dataset.fx === "hscroll") n.classList.add("is-focus"); else reveal(n, undefined, true);
    }
    for (let n = e.target; n && n !== root; n = n.parentElement) {
      if (n.parentElement && n.parentElement.dataset && n.parentElement.dataset.fx === "cascade") reveal(n, 0, true);
    }
  };
  // once an element has finished arriving, drop its stagger delay so hover feedback is never late
  const onEnd = (e) => { const t = e.target; if (t.classList && t.classList.contains("is-in") && e.propertyName === "opacity") t.classList.add("is-settled"); };
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", onResize, { passive: true });
  document.addEventListener("visibilitychange", onVisible);
  document.addEventListener("focusin", onFocus);
  document.addEventListener("transitionend", onEnd);
  window.addEventListener("pagehide", () => {
    io.disconnect(); cancelAnimationFrame(raf); raf = 0; live.clear(); settle.clear(); counting.length = 0;
    cleanups.forEach((fn) => fn());
    window.removeEventListener("scroll", schedule); window.removeEventListener("resize", onResize);
    document.removeEventListener("visibilitychange", onVisible); document.removeEventListener("focusin", onFocus);
    document.removeEventListener("transitionend", onEnd);
  }, { once: true });
  schedule();
})();
