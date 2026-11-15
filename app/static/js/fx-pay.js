/* The payment mark plays once per order per browser session. See docs/ARCHITECTURE.md. */
(() => {
  "use strict";
  const mark = document.querySelector('.result-success[data-play]');
  if (!mark) return;
  try {
    const key = "ps-paid-" + mark.dataset.order;
    if (window.sessionStorage.getItem(key)) mark.classList.add("is-played");
    else window.sessionStorage.setItem(key, "1");
  } catch (e) { /* storage unavailable: play it */ }
})();
