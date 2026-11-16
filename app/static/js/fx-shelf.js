/* The home shelf as an endless loop (v1.4). It drifts from load; a mouse over it, focus on a card and the Pause button
   stop it; with reduced motion it starts paused. fx-scroll.js calls window.fxShelf.tick. See docs/ARCHITECTURE.md. */
(() => {
  "use strict";
  const root = document.documentElement, sec = document.querySelector('[data-fx="hscroll"]');
  const stage = sec && sec.querySelector(".hs-stage"), track = sec && sec.querySelector(".hs-track");
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!stage || !track || !(root.classList.contains("fx-on") || mq.matches) || root.classList.contains("fx-off-shelf-loop")) return;
  if (!root.classList.contains("fx-on")) root.classList.add("fx-shelf-rm");
  const cards = [...track.children];
  if (cards.length < 2) return;
  const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
  const knob = (n, d) => { const v = parseFloat(getComputedStyle(root).getPropertyValue(n)); return v >= 0 ? v : d; };
  const speed = knob("--shelf-speed", 26), gain = knob("--shelf-wheel-gain", 1), VMAX = 1800;
  const gutter = parseFloat(getComputedStyle(track).paddingLeft) || 24;
  const offs = [], on = (el, type, fn, o) => { el.addEventListener(type, fn, o); offs.push(() => el.removeEventListener(type, fn, o)); };
  const wake = () => window.dispatchEvent(new Event("fxshelf-wake"));
  const copy = () => cards.map((c) => {
    const k = c.cloneNode(true);
    k.setAttribute("aria-hidden", "true"); k.setAttribute("inert", ""); k.classList.add("hs-clone");
    k.querySelectorAll("a, button, [tabindex]").forEach((a) => a.setAttribute("tabindex", "-1"));
    return k;
  });
  copy().reverse().forEach((k) => track.insertBefore(k, track.firstChild));
  let after = copy();
  after.forEach((k) => track.appendChild(k));
  sec.classList.add("is-loop");
  const s = { x: 0, v: 0, dir: 1, paused: mq.matches, calm: mq.matches, hover: false, focus: false, lock: false, start: null, moving: false, lastY: null, t: 0, P: 0, lo: 0, stale: true };
  const pos = (el) => el.offsetLeft - track.firstChild.offsetLeft;
  const measure = () => {
    s.stale = false;
    s.P = pos(after[0]) - pos(cards[0]);
    if (!(s.P > 0)) return;
    while (after.length < (Math.ceil(stage.clientWidth / s.P) + 1) * cards.length) { const m = copy(); m.forEach((k) => track.appendChild(k)); after = after.concat(m); }
    s.lo = pos(cards[0]) - gutter - s.P / 2;
    track.__span = s.P;
    if (!s.t) s.x = pos(cards[0]) - gutter;
  };
  const push = (px) => { if (!px) return; s.v = clamp(s.v + px * gain * 4, -VMAX, VMAX); if (Math.abs(px) > 1) s.dir = px > 0 ? 1 : -1; wake(); };
  window.fxShelf = {
    state: s, push,
    tick(now, y) {
      if (s.stale) measure();
      const dt = s.t ? clamp((now - s.t) / 1000, 0, 0.05) : 0;
      s.t = now;
      const r = sec.getBoundingClientRect();
      if (r.bottom <= 0 || r.top >= window.innerHeight) { s.lastY = null; return false; }
      if (s.lastY !== null && y !== s.lastY && !s.moving && !s.lock && !s.calm) push(y - s.lastY);   // scrolling pushes it (not with reduced motion)
      s.lastY = y;
      const target = s.paused || s.hover || s.focus ? 0 : s.dir * speed;
      if (!s.moving && !s.lock) {
        s.v += (target - s.v) * (1 - Math.exp(-dt / 0.6));
        s.x += s.v * dt;
        if (s.P > 0) s.x = s.lo + ((((s.x - s.lo) % s.P) + s.P) % s.P);
      }
      track.style.setProperty("--sx", s.x.toFixed(2));
      return s.moving || target !== 0 || Math.abs(s.v - target) > 0.5;
    },
  };
  const btn = sec.querySelector("[data-shelf-toggle]");
  const setPaused = (v) => {
    s.paused = v;
    if (btn) { btn.dataset.state = v ? "paused" : "playing"; btn.querySelector("[data-label]").textContent = v ? "Play" : "Pause"; }
    wake();
  };
  if (btn) {
    btn.hidden = false;
    setPaused(s.paused);
    on(btn, "click", () => setPaused(!s.paused));
  }
  if (mq.addEventListener) on(mq, "change", (e) => { s.calm = e.matches; if (e.matches) setPaused(true); else wake(); });
  const hover = (v) => (e) => { if (e.pointerType === "mouse") { s.hover = v; wake(); } };
  on(stage, "pointerenter", hover(true));
  on(stage, "pointerleave", hover(false));
  on(stage, "wheel", (e) => {
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) { e.preventDefault(); push(e.deltaX * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1)); }
  }, { passive: false });
  on(stage, "pointerdown", (e) => { if (!e.button) s.start = { id: e.pointerId, cx: e.clientX, x: s.x, last: e.clientX, t: performance.now(), vel: 0 }; });
  on(stage, "pointermove", (e) => {
    const st = s.start;
    if (!st || st.id !== e.pointerId) return;
    if (!s.moving && Math.abs(e.clientX - st.cx) > 6) {
      s.moving = true; sec.classList.add("is-dragging");
      try { stage.setPointerCapture(e.pointerId); } catch (err) { /* keeps working inside the shelf */ }
    }
    if (!s.moving) return;
    const t = performance.now(), step = (t - st.t) / 1000;
    if (step > 0) st.vel = 0.7 * st.vel + 0.3 * ((st.last - e.clientX) / step);
    st.last = e.clientX; st.t = t;
    s.x = st.x - (e.clientX - st.cx); s.v = 0;
    wake();
  });
  const release = (e) => {
    if (!s.start || s.start.id !== e.pointerId) return;
    if (s.moving) {
      s.v = clamp(s.start.vel, -VMAX, VMAX);
      if (Math.abs(s.v) > 20) s.dir = s.v > 0 ? 1 : -1;
      s.suppress = true;                                                     // the click ending a drag opens nothing
      sec.classList.remove("is-dragging");
    }
    s.start = null; s.moving = false; wake();
  };
  on(stage, "pointerup", release);
  on(stage, "pointercancel", release);
  on(stage, "click", (e) => { if (s.suppress) { s.suppress = false; e.preventDefault(); e.stopPropagation(); } }, true);
  on(track, "focusin", (e) => {                                             // cards only, not the Pause button
    s.focus = true;
    const card = e.target.closest(".hs-card");
    if (cards.indexOf(card) >= 0) {
      if (s.stale) measure();
      const left = pos(card) - s.x;
      if (left < gutter || left + card.offsetWidth > stage.clientWidth - gutter) s.x = pos(card) - gutter;
      s.v = 0; s.lock = true;
    }
    wake();
  });
  on(track, "focusout", (e) => { if (!track.contains(e.relatedTarget)) { s.focus = s.lock = false; wake(); } });
  on(window, "resize", () => { s.stale = true; wake(); }, { passive: true });
  on(window, "pagehide", () => { offs.forEach((f) => f()); delete window.fxShelf; }, { once: true });
  window.dispatchEvent(new Event("fxshelf-ready"));
})();
