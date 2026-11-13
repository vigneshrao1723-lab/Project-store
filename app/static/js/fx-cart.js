/* Add to cart on the product page, plus a pulse on the header count when it goes up.
   It listens to what the page already does and changes nothing about it: the form's submit event starts the
   animation, and the DOM updates app.js already makes (the note under the button, the header count) say how the
   request ended. If this file never loads, the button works exactly as before. */
(() => {
  "use strict";
  const calm = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const GO = 360;            // ms: label out, cart to the middle
  const HOLD = 1600;         // ms from the click until the button starts to return
  const SETTLE = 400;        // ms: the return animation
  const GIVE_UP = 8000;      // ms: no answer from the request, put the button back

  function setup(form) {
    const btn = form.querySelector(".atc");
    const go = btn && btn.querySelector(".atc-go");
    const note = form.closest(".buy")?.querySelector("[data-note]");
    if (!go || !note) return;
    let timers = [], pending = false, t0 = 0, fromAdded = false;

    const later = (fn, ms) => timers.push(setTimeout(fn, Math.max(0, ms)));
    const state = (name) => {
      if (name) { btn.dataset.state = name; btn.classList.add("is-animating"); }
      else { delete btn.dataset.state; btn.classList.remove("is-animating"); }
    };
    const reset = () => { timers.forEach(clearTimeout); timers = []; pending = false; fromAdded = false; state(null); };

    function measure() {
      const b = btn.getBoundingClientRect(), g = go.getBoundingClientRect();
      const x = (b.left + b.width / 2) - (g.left + g.width / 2);
      btn.style.setProperty("--atc-x", x + "px");
      btn.style.setProperty("--atc-out", (b.right - g.left + 8) + "px");
      btn.style.setProperty("--atc-in", (-(g.right - b.left) - 8) + "px");
    }

    form.addEventListener("submit", () => {
      const wasAdded = btn.dataset.state === "added";
      timers.forEach(clearTimeout); timers = [];
      pending = true; t0 = performance.now(); fromAdded = wasAdded;
      if (!wasAdded && !calm()) { state(null); measure(); void btn.offsetWidth; state("adding"); }
      later(reset, GIVE_UP);
    });

    new MutationObserver(() => {
      if (!pending) return;
      pending = false;
      timers.forEach(clearTimeout); timers = [];
      if (!note.querySelector("a")) {            // an error message: roll the cart back
        if (btn.dataset.state === "adding") { state("undo"); later(reset, 320); } else reset();
        return;
      }
      const wait = fromAdded || calm() ? 0 : GO - (performance.now() - t0);
      later(() => {
        if (fromAdded) { state(null); void btn.offsetWidth; }
        state("added");
        later(() => { if (calm()) reset(); else state("back"); }, HOLD - GO);
        if (!calm()) later(reset, HOLD - GO + SETTLE);
      }, wait);
    }).observe(note, { childList: true });
  }

  document.querySelectorAll("form[data-add-to-cart]").forEach(setup);

  // header cart count: pulse when the number goes up
  document.querySelectorAll("[data-cart-count]").forEach((el) => {
    let before = parseInt(el.textContent, 10) || 0;
    new MutationObserver(() => {
      const now = parseInt(el.textContent, 10) || 0;
      const up = now > before;
      before = now;
      if (!up || calm()) return;
      el.classList.remove("is-bump"); void el.offsetWidth;
      el.classList.add("is-bump", "is-animating");
      el.addEventListener("animationend", () => el.classList.remove("is-bump", "is-animating"), { once: true });
    }).observe(el, { childList: true });
  });
})();
