/* Motion 2: the moments people use the store. Add-to-cart feedback, the cart badge, scroll reveal, the condensed
   header and number ticks. Every page works and reads the same without this file: the CSS shows everything by
   default and this script only opts elements in (.is-pending, then .is-in), and a CSS animation reveals anything
   still pending after 2s even if the observer never fires. Only transform and opacity move. app.js is unchanged
   apart from three CustomEvents (cart:count, cart:added, cart:rendered) that this file listens for. */
(() => {
  "use strict";
  const calm = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  const $$ = (sel, from) => Array.from((from || document).querySelectorAll(sel));

  // Play a one-shot CSS animation class again. Reduced motion gets no movement at all.
  function play(el, cls) {
    if (calm.matches) return;
    el.classList.remove(cls);
    void el.offsetWidth;                       // restart the animation if it is already running
    el.classList.add(cls, "is-animating");
    const done = (e) => {
      if (e.target !== el) return;
      el.classList.remove(cls, "is-animating");
      el.removeEventListener("animationend", done);
    };
    el.addEventListener("animationend", done);
  }

  // ---- cart badge: bump once per increase, judged against the count remembered for this tab ----------------
  const KEY = "ps-cart-count";
  function remembered() {
    try { const v = window.sessionStorage.getItem(KEY); return v === null ? null : Number(v); } catch (_) { return null; }
  }
  function remember(n) { try { window.sessionStorage.setItem(KEY, String(n)); } catch (_) { /* no storage: no bump */ } }
  function countSeen(n) {
    const before = remembered();
    remember(n);
    if (before !== null && n > before) $$("[data-cart-count]").forEach((b) => play(b, "is-bump"));
  }
  const badge = document.querySelector("[data-cart-count]");
  if (badge) countSeen(Number(badge.textContent) || 0);
  document.addEventListener("cart:count", (e) => countSeen(Number(e.detail && e.detail.count) || 0));

  // ---- add to cart: the button turns into a check and "Added" for a moment ---------------------------------
  const timers = new WeakMap();
  document.addEventListener("cart:added", (e) => {
    const btn = e.target.querySelector && e.target.querySelector("button[type=submit]");
    if (!btn) return;
    if (btn.dataset.label === undefined) btn.dataset.label = btn.textContent;
    btn.dataset.state = "added";
    btn.textContent = "Added";
    clearTimeout(timers.get(btn));
    timers.set(btn, setTimeout(() => {
      delete btn.dataset.state;
      btn.textContent = btn.dataset.label;
    }, 1600));
  });

  // ---- numbers that change tick once: quantities, line totals and the cart total ---------------------------
  const seen = new WeakMap();
  const NUMBERS = ".stepper input, [data-line-total], [data-total], [data-count]";
  function ticks() {
    $$(NUMBERS).forEach((el) => {
      const now = "value" in el ? el.value : el.textContent;
      if (seen.has(el) && seen.get(el) !== now) play(el, "is-tick");
      seen.set(el, now);
    });
  }
  ticks();
  document.addEventListener("cart:rendered", ticks);
  document.addEventListener("click", (e) => { if (e.target.closest && e.target.closest("[data-step]")) ticks(); });

  // ---- header: a condensed state past 40px, without changing its height -------------------------------------
  const header = document.querySelector(".site-header");
  if (header) {
    let queued = false;
    const check = () => { queued = false; header.classList.toggle("is-condensed", window.scrollY > 40); };
    window.addEventListener("scroll", () => { if (!queued) { queued = true; window.requestAnimationFrame(check); } }, { passive: true });
    check();
  }

  // ---- reveal on scroll: sections, tiles and the cart and checkout summary, each once ------------------------
  if (!("IntersectionObserver" in window) || calm.matches) return;
  const targets = [];
  $$("[data-reveal], [data-motion-group='tiles'] [data-motion='tile']").forEach((el) => {
    if (el.matches("[data-reveal]") && el.querySelector("[data-motion-group='tiles']")) {
      // a section that holds a tile grid reveals its heading row, and the tiles reveal one by one
      const head = el.querySelector(".section-head");
      if (head) targets.push(head);
    } else {
      targets.push(el);
    }
  });
  if (!targets.length) return;
  const io = new IntersectionObserver((entries) => {
    let n = 0;
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      io.unobserve(el);
      el.style.setProperty("--i", Math.min(n++, 7));   // stagger by arrival order in this batch, 60ms apart, at most 8
      el.classList.remove("is-pending");
      el.classList.add("is-in");
    });
  }, { rootMargin: "0px 0px -6% 0px" });
  targets.forEach((el) => { el.classList.add("is-pending"); io.observe(el); });
})();
