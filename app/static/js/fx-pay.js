/* Payment result: shows the success sequence once per order per browser session. The sequence itself is plain CSS
   and starts as soon as the page paints; this file only switches it off when this order has already played it
   here (a back/forward or a reload). With no script, or with storage blocked, the sequence just plays again. */
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
