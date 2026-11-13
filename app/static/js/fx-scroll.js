/* Scroll-linked motion for the home page and the catalogue. One requestAnimationFrame loop does all of it: it
   measures what is near the screen, writes a progress number onto each piece (--e for one card or tile, --p for the
   pinned showcase) and the stylesheet turns that into transform and opacity. Pieces far from the screen are not
   touched, scroll and resize listeners are passive, and the loop stops while the tab is hidden. With reduced
   motion, or if this file never runs, every number defaults to "finished" in the stylesheet, so nothing is hidden. */
(() => {
  "use strict";
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const clamp = (x) => Math.min(1, Math.max(0, x));
  const live = new Set();          // pieces near the screen
  const pieces = [];
  const counting = [];             // counters that are counting up right now
  let raf = 0, dirty = true;

  function put(el, name, value) {          // write only when it changed enough to matter
    const v = value.toFixed(3);
    if (el.__v && el.__v[name] === v) return;
    (el.__v = el.__v || {})[name] = v;
    el.style.setProperty(name, v);
  }

  // cards that come in one after another: 0 when the group's top is at 85% of the screen, 1 at 35%
  function cascade(group) {
    const items = [...group.querySelectorAll("[data-fx-item]")];
    const counters = items.map((it) => it.querySelector("[data-fx-count]"));
    counters.forEach((c) => { if (c) c.__n = +c.dataset.fxCount; });
    return {
      el: group, items,
      measure: (vh) => group.getBoundingClientRect().top / vh,
      apply(top) {
        const p = clamp((0.85 - top) / 0.5);
        items.forEach((it, i) => {
          const e = clamp((p * (items.length + 1) - i) / 1.4);
          put(it, "--e", e);
          const c = counters[i];
          if (c && e > 0.5 && !c.__done) startCount(c);
        });
      },
    };
  }

  // tiles: each comes in as its own top crosses the lower part of the screen, and a tile further along its row
  // follows a little after the one before it
  function tiles(grid) {
    const items = [...grid.querySelectorAll(".tile")];
    return {
      el: grid, items,
      measure: (vh) => {
        const rects = items.map((t) => t.getBoundingClientRect());
        const rowTop = rects.length ? rects[0].top : 0;
        const cols = Math.max(1, rects.filter((r) => Math.abs(r.top - rowTop) < 4).length);
        return { rects, cols, vh };
      },
      apply({ rects, cols, vh }) {
        items.forEach((t, i) => put(t, "--e", clamp((0.97 * vh - rects[i].top) / (0.2 * vh) - (i % cols) * 0.15)));
      },
    };
  }

  // the pinned showcase: 0 when the stage sticks, 1 when it lets go. The stage sticks just under the site header
  // when the header itself is sticky, and at the top of the screen when it is not.
  function showcase(sec) {
    const stage = sec.querySelector(".showcase-stage");
    const header = document.querySelector(".site-header");
    const items = [...sec.querySelectorAll(".sc-cover, .sc-head")];
    let top = 0, stale = true;                    // the header's height only changes when the window does
    window.addEventListener("resize", () => { stale = true; }, { passive: true });
    return {
      el: sec, items,
      measure: () => {
        if (stale) { top = header && getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0; stale = false; }
        return { top, p: (top - sec.getBoundingClientRect().top) / Math.max(1, sec.offsetHeight - stage.offsetHeight) };
      },
      apply({ top, p }) {
        if (sec.__top !== top) { sec.__top = top; sec.style.setProperty("--fx-top", top + "px"); }
        put(sec, "--p", clamp(p));
      },
    };
  }

  // counters: text changes only inside the fixed-width box the stylesheet gave them
  function startCount(c) {
    c.__done = true;
    const out = c.querySelector(".cnt-live");
    if (!out || !(c.__n > 0)) return;
    counting.push({ out, n: c.__n, t0: performance.now() });
    out.textContent = "0";
    schedule();
  }
  function tickCounters(now) {
    for (let i = counting.length - 1; i >= 0; i--) {
      const c = counting[i], t = clamp((now - c.t0) / 900);
      c.out.textContent = String(Math.round(c.n * (1 - Math.pow(1 - t, 3))));
      if (t >= 1) counting.splice(i, 1);
    }
  }

  function frame(now) {
    raf = 0;
    const vh = window.innerHeight || 1;
    const todo = [...live];
    const measured = todo.map((p) => p.measure(vh));        // all reads first
    todo.forEach((p, i) => p.apply(measured[i]));            // then all writes
    tickCounters(now);
    dirty = false;
    if (counting.length) schedule();
  }
  function schedule() {
    if (!raf && !document.hidden) raf = requestAnimationFrame(frame);
  }

  document.querySelectorAll('[data-fx="cascade"]').forEach((g) => pieces.push(cascade(g)));
  document.querySelectorAll('[data-fx="tiles"]').forEach((g) => pieces.push(tiles(g)));
  document.querySelectorAll('[data-fx="showcase"]').forEach((s) => {
    pieces.push(showcase(s));
    s.addEventListener("focusin", () => s.classList.add("is-focus"));
  });
  if (!pieces.length) return;
  // counters wait at zero until their card has come in (without a script they simply show the final number)
  document.querySelectorAll("[data-fx-count] .cnt-live").forEach((l) => { l.textContent = "0"; });

  // will-change is on only for pieces that are near the screen, and comes off when they leave it
  const near = (p, on) => { if (on) live.add(p); else live.delete(p); p.items.forEach((i) => i.classList[on ? "add" : "remove"]("is-animating")); };
  if ("IntersectionObserver" in window) {
    const byEl = new Map(pieces.map((p) => [p.el, p]));
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => near(byEl.get(e.target), e.isIntersecting));
      schedule();
    }, { rootMargin: "30% 0px 30% 0px" });
    pieces.forEach((p) => io.observe(p.el));
  } else {
    pieces.forEach((p) => near(p, true));
  }

  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else schedule(); });
  schedule();
})();
