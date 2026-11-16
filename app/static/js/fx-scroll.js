/* The scroll system: one script, one IntersectionObserver and one requestAnimationFrame loop for every page. It reads
   the data-fx words and writes classes and custom properties; the stylesheet does the moving. fx-bg.js and fx-shelf.js
   have no loop of their own and ride this one (window.fxBg.tick, window.fxShelf.tick). docs/ARCHITECTURE.md, "Script
   notes", has the full description. */
(() => {
  "use strict";
  // TO TURN AN EFFECT OFF: list its name here, e.g. ["tilt", "magnetic", "toasts"]. A data-fx word is then treated as
  // already in place; every name also becomes an fx-off-<name> class on <html>, which the stylesheets and fx-ui.js
  // check for the effects that are not data-fx words. One list for the whole site. The names are in docs/ARCHITECTURE.md:
  //   words:   rise from-left from-right zoom flip clip lines words count cascade pin hscroll parallax draw tilt magnetic marquee
  //   others:  stepper inputs shake toasts cart downloads forms drift bob timeline focus-ring press wipe lift
  //   modules: shelf-loop (fx-shelf.js) bg3d (fx-bg.js)
  const OFF = [];
  // The same list can come from the server: app/fx.json is written into <html data-fx-off="...">. Both are merged.
  ((document.documentElement.dataset && document.documentElement.dataset.fxOff) || "").split(/\s+/).forEach((n) => { if (n && OFF.indexOf(n) < 0) OFF.push(n); });
  OFF.forEach((n) => document.documentElement.classList.add("fx-off-" + n));

  const body = document.body;
  const page = body && body.dataset.page;
  if (!page || page === "none") return;
  if (page === "admin" && OFF.indexOf("admin-motion") >= 0) return;
  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let raf = 0;
  if (reduced) {                       // only the shelf gets frames (see frame)
    ["fxshelf-ready", "fxshelf-wake", "scroll", "resize"].forEach((n) => window.addEventListener(n, schedule, { passive: true }));
    document.addEventListener("visibilitychange", schedule);
    return;
  }
  if (!("IntersectionObserver" in window)) return;

  const root = document.documentElement;
  // fx-lite for weak devices (see Script notes); ?fx=lite or ?fx=full forces either way
  const forced = /[?&]fx=(lite|full)\b/.exec(window.location.search || "");
  const lite = forced ? forced[1] === "lite" : (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4;
  if (lite) root.classList.add("fx-lite");
  let probing = false, probeN = 0, probeT0 = 0;          // the frame-rate probe

  const scenic = page !== "admin";                 // admin pages get the one-shot words only
  const header = document.querySelector(".site-header");
  const bar = page === "browse" ? document.querySelector(".fx-progress") : null;   // --sp on this node, never on <html>
  const clamp = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));
  // knobs from fx-tuning.css, read once
  const knob = (name, fallback) => {
    try { const cs = typeof getComputedStyle === "function" ? getComputedStyle(root) : null; const v = cs && cs.getPropertyValue ? parseFloat(cs.getPropertyValue(name)) : NaN; return v >= 0 ? v : fallback; } catch (e) { return fallback; }
  };
  const tiltMax = knob("--tilt-max", 6), magnetMax = knob("--magnet-max", 6);
  const ONE = ["rise", "from-left", "from-right", "zoom", "flip", "clip", "words", "lines", "count"];
  const SCENES = ["pin", "hscroll", "parallax", "draw"];
  const live = new Set();            // scenes that are on screen
  const settle = new Set();          // just left: one last measurement
  const counting = [];               // counters that are counting up right now
  const cleanups = [];
  let docH = 0, condensed = false;

  function put(el, name, value) {
    const v = typeof value === "number" ? value.toFixed(3) : value;
    if (el.__v && el.__v[name] === v) return;
    (el.__v = el.__v || {})[name] = v;
    el.style.setProperty(name, v);
  }

  // ---- one-shot pieces
  function startCount(el) {
    const out = el.querySelector(".cnt-live"), n = +el.dataset.to;
    el.__done = true;
    if (!out || !(n > 0)) return;
    out.textContent = "0";
    counting.push({ out, n, t0: performance.now() });
    schedule();
  }
  function reveal(el, i, instant) {
    if (instant) el.classList.add("is-instant");         // focus never lands in something faint
    if (el.__done || el.classList.contains("is-in")) return;
    if (el.dataset.fx === "count") return startCount(el);
    if (i !== undefined) put(el, "--i", String(Math.min(i, 7)));
    el.classList.add("is-in");
  }

  // ---- scenes
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
          if (track && stuck) {                      // a sideways shelf: how far it travels (one set of cards when looping)
            const shift = Math.max(0, (track.__span || track.scrollWidth) - stage.clientWidth);
            sec.style.setProperty("--hs", shift + "px");
            sec.style.setProperty("--hs-h", (stage.offsetHeight + shift) + "px");
          }
          stale = false;
        }
        const r = sec.getBoundingClientRect();
        const p = stuck ? (top - r.top) / Math.max(1, sec.offsetHeight - stage.offsetHeight) : (0.9 * vh - r.top) / (0.6 * vh + 0.4 * r.height);
        return { p, top };
      },
      apply({ p, top: t }) {
        if (sec.__top !== t) { sec.__top = t; sec.style.setProperty("--fx-top", t + "px"); }
        put(sec, "--p", clamp(p));
        if (sec.__pre !== p < 0.2) { sec.__pre = p < 0.2; sec.classList.toggle("is-pre", sec.__pre); }
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
  function trace(el) {                
    return {
      el, moving: [],
      measure(vh) { const r = el.getBoundingClientRect(); return clamp((0.85 * vh - r.top) / (0.5 * vh + 0.6 * r.height)); },
      apply(v) { put(el, "--d", v); },
      stale() {},
    };
  }

  // ---- collect everything
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
  rises.forEach((el) => {
    const kids = el.dataset.fx === "words" ? el.querySelectorAll(".w") : el.dataset.fx === "lines" ? el.querySelectorAll(".ln") : [];
    [...kids].forEach((k, i) => put(k, "--i", String(Math.min(i, 29))));
  });

  // what is already on screen is revealed before fx-on, so it never hides
  const waiting = [], late = [];
  const arrive = (el, i) => {
    if (el.getBoundingClientRect().top >= vh0 * 0.94) waiting.push(el);
    else if (el.dataset.fx === "words" || el.dataset.fx === "lines") late.push(el);
    else reveal(el, i);
  };
  rises.forEach((el) => { if (el.dataset.fx === "count") el.querySelector(".cnt-live").textContent = "0"; arrive(el); });
  parents.forEach((parent) => [...parent.children].forEach((child, n) => arrive(child, n)));
  root.classList.add("fx-on");
  if (late.length) { void root.offsetHeight; late.forEach((el) => reveal(el)); }
  scenes.forEach((s) => { s.apply(s.measure(vh0)); s.stale(); });

  // ---- pointer feedback, fine pointers only
  const fine = window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  if (fine && scenic) {
    const on = (el, type, fn) => { el.addEventListener(type, fn); cleanups.push(() => el.removeEventListener(type, fn)); };
    active(["tilt"]).forEach((el) => {
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
    active(["magnetic"]).forEach((el) => {
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

  // ---- the one observer
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

  // ---- the loop
  function frame(now) {
    raf = 0;
    if (reduced) { if (window.fxShelf && window.fxShelf.tick(now, window.pageYOffset || 0)) schedule(); return; }
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
    const measured = work.map((s) => s.measure(vh));      // reads, then writes
    if (bar) docH = root.scrollHeight;
    work.forEach((s, i) => s.apply(measured[i]));
    if (header && (y > 40) !== condensed) { condensed = y > 40; header.classList.toggle("is-condensed", condensed); }
    if (bar) put(bar, "--sp", clamp(y / Math.max(1, docH - vh)));
    for (let i = counting.length - 1; i >= 0; i--) {
      const c = counting[i], t = clamp((now - c.t0) / 900);
      c.out.textContent = String(Math.round(c.n * (1 - Math.pow(1 - t, 3))));
      if (t >= 1) counting.splice(i, 1);
    }
    if (counting.length) schedule();
    if (window.fxShelf && window.fxShelf.tick(now, y)) schedule();
    if (window.fxBg && window.fxBg.tick(now)) schedule();
  }
  function schedule() { if (!raf && !document.hidden) raf = requestAnimationFrame(frame); }

  const onResize = () => { scenes.forEach((s) => s.stale()); schedule(); };
  const onShelf = () => { scenes.forEach((s) => s.stale()); schedule(); };
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
  const onEnd = (e) => { const t = e.target; if (t.classList && t.classList.contains("is-in") && e.propertyName === "opacity") t.classList.add("is-settled"); };
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("fxbg-ready", schedule);
  window.addEventListener("fxshelf-ready", onShelf);
  window.addEventListener("fxshelf-wake", schedule);
  window.addEventListener("resize", onResize, { passive: true });
  document.addEventListener("visibilitychange", onVisible);
  document.addEventListener("focusin", onFocus);
  document.addEventListener("transitionend", onEnd);
  window.addEventListener("pagehide", () => {
    io.disconnect(); cancelAnimationFrame(raf); raf = 0; live.clear(); settle.clear(); counting.length = 0;
    if (window.fxBg) window.fxBg.stop();
    cleanups.forEach((fn) => fn());
    window.removeEventListener("scroll", schedule); window.removeEventListener("resize", onResize); window.removeEventListener("fxbg-ready", schedule);
    window.removeEventListener("fxshelf-ready", onShelf); window.removeEventListener("fxshelf-wake", schedule);
    document.removeEventListener("visibilitychange", onVisible); document.removeEventListener("focusin", onFocus);
    document.removeEventListener("transitionend", onEnd);
  }, { once: true });
  schedule();
  if (!lite && !forced) {
    let started = false;
    const startProbe = () => { if (started) return; started = true; setTimeout(() => { probing = !document.hidden; schedule(); }, 300); };
    // with the 3D background, measure once it runs (or after 4 s), so its start-up is not mistaken for a slow device
    const afterBg = () => { if (document.querySelector("canvas[data-bg3d]") && !window.fxBg) { window.addEventListener("fxbg-ready", startProbe, { once: true }); setTimeout(startProbe, 4000); } else startProbe(); };
    if (document.readyState === "complete") afterBg(); else window.addEventListener("load", afterBg, { once: true });
  }
})();
