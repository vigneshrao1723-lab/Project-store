/* Runs in <head>, before first paint, to decide whether the one-time intro loader should play.
   It only adds a class to <html>; the loader is hidden by CSS unless that class is present, and a CSS animation
   hides it again after 2s even if no other script ever runs. The flag is set now, not when the loader ends, so a
   broken motion.js can show the loader at most once per session. Storage that is blocked or unavailable, and
   prefers-reduced-motion, both mean no loader. */
(function () {
  try {
    var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!calm && !window.sessionStorage.getItem("ps-intro")) {
      window.sessionStorage.setItem("ps-intro", "1");
      document.documentElement.classList.add("intro-run");
    }
  } catch (e) { /* no storage, no loader */ }
})();
