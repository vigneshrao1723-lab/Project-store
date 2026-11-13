/* Interface motion for controls and for the pages people pay and sign in on. It never hides anything: it adds states
   (a spinner on a posting button, a toast that leaves, a cart row that slides away, a figure that ticks, a download that
   says it is preparing). No observer of the viewport and no animation-frame loop here; the scroll system lives in
   fx-scroll.js. Under reduced motion only the form guard runs, and its spinner is a still ring. */
(() => {
  "use strict";
  const calm = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const root = document.documentElement;
  const off = (name) => root.classList.contains("fx-off-" + name);      // the one list of switches is OFF in fx-scroll.js
  const timers = [], observers = [];
  const later = (fn, ms) => { const t = setTimeout(fn, ms); timers.push(t); return t; };

  // ---- forms: a button shows it is posting, and a second submit of the same form is ignored meanwhile --------------
  const posting = new Set();
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (off("forms")) return;
    if (e.defaultPrevented || !form || form.tagName !== "FORM") return;       // the add-to-cart form handles itself (and disables its button)
    if (posting.has(form)) { e.preventDefault(); return; }
    posting.add(form);
    const btn = e.submitter || form.querySelector('button[type="submit"], button:not([type])');
    if (btn && btn.classList.contains("btn")) { btn.classList.add("is-loading"); btn.setAttribute("aria-busy", "true"); }
    later(() => release(form, btn), 15000);                                   // a request that never answers must not lock the form
  });
  function release(form, btn) { posting.delete(form); if (btn) { btn.classList.remove("is-loading"); btn.removeAttribute("aria-busy"); } }
  window.addEventListener("pageshow", (e) => {                                // back to a page from the cache: forms are usable again
    if (!e.persisted) return;
    posting.clear();
    document.querySelectorAll(".btn.is-loading").forEach((b) => { b.classList.remove("is-loading"); b.removeAttribute("aria-busy"); });
  });

  if (!calm) {
    if (!off("toasts")) root.classList.add("fx-ui");

    // ---- flash messages are toasts: success and info ones leave after six seconds, errors stay until the page changes --
    if (!off("toasts")) document.querySelectorAll(".flashes .flash").forEach((el) => {
      if (el.classList.contains("flash-error")) return;
      later(() => { el.classList.add("is-leaving"); later(() => { el.hidden = true; }, 380); }, 6000);
    });

    // ---- downloads: a press says the link is being prepared ---------------------------------------------------------
    document.addEventListener("click", (e) => {
      const a = !off("downloads") && e.target.closest && e.target.closest(".delivery a");
      if (!a) return;
      a.classList.add("is-preparing"); a.setAttribute("aria-busy", "true");
      later(() => { a.classList.remove("is-preparing"); a.removeAttribute("aria-busy"); }, 1400);
    });

    // ---- cart: removed rows slide away, changed figures tick ---------------------------------------------------------
    const cart = document.querySelector("[data-cart]");
    const lines = cart && cart.querySelector(".lines");
    if (lines && !off("cart")) {
      const tick = (el) => { el.classList.remove("is-tick"); void el.offsetWidth; el.classList.add("is-tick"); };
      const gone = new MutationObserver((muts) => muts.forEach((m) => m.removedNodes.forEach((n) => {
        if (n.nodeType !== 1 || !n.matches(".line:not(.is-ghost)")) return;
        n.classList.add("is-ghost");                                          // put the removed row back as a harmless ghost that slides out
        n.removeAttribute("data-line"); n.setAttribute("aria-hidden", "true");
        n.querySelectorAll("button, input, a").forEach((c) => c.setAttribute("tabindex", "-1"));
        lines.insertBefore(n, m.nextSibling && m.nextSibling.parentNode === lines ? m.nextSibling : null);
        n.addEventListener("animationend", () => n.remove(), { once: true });
      })));
      gone.observe(lines, { childList: true });
      const figures = new MutationObserver((muts) => {
        const hit = new Set();
        muts.forEach((m) => {
          const el = (m.target.nodeType === 1 ? m.target : m.target.parentElement);
          const fig = el && el.closest("[data-line-total], [data-total], [data-count]");
          if (!fig || fig.closest(".is-ghost")) return;
          hit.add(fig);
          const row = fig.closest("[data-line]");
          if (row && row.querySelector("input")) hit.add(row.querySelector("input"));
        });
        hit.forEach(tick);
      });
      figures.observe(cart, { childList: true, characterData: true, subtree: true });
      observers.push(gone, figures);
    }
  }

  window.addEventListener("pagehide", () => {
    timers.forEach(clearTimeout); observers.forEach((o) => o.disconnect());
  }, { once: true });
})();
