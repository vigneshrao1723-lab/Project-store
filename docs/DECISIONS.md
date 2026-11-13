# Decisions made without asking

The owner is not available overnight, so each decision is logged here with the time, the options and the reason.
Newest last.

| Time (IST) | Decision | Options considered | Why |
|---|---|---|---|
| 23:38 | The list of switched-off effects lives in `app/fx.json` (`{"off": []}`), read by the context processor and written into `<html data-fx-off="...">`; `fx-scroll.js` merges it with its own `OFF` constant (kept, empty). | (a) only the JS constant; (b) a data attribute typed into base.html; (c) a JSON file. | One array in one place, present at first paint so CSS-only effects (and view transitions) switch off with no script. The JS constant stays so the earlier tests and the "one list" comment remain true. |
| 23:38 | Knob defaults for `--cart-anim-ms` (1000) and `--pay-anim-ms` (1400) are unitless millisecond numbers, not lengths. | (a) lengths with typed division; (b) unitless numbers. | Dividing two lengths in `calc()` is not supported by older browsers; a unitless number works everywhere and `fx-cart.js` can read it. |
| 23:38 | `--loader-ms` changes when the intro loader starts to leave (default 1000ms); the loader scene's inner timings are unchanged. | Scale every loader keyframe, or only the hold time. | The loader's own tests pin its keyframes; the hold time is what "loader too long" means. |
| 23:47 | The frame-rate probe that can set `fx-lite` starts 300 ms after the page's load event, not at script start. | Probe from the first frame; probe after load; drop the probe. | A screenshot or a slow first paint at load made the probe see a jank burst and wrongly turn the pinned showcase off on a fast machine. Waiting for load keeps the probe honest and removes nothing. |
| 23:49 | The home showcase headline for scene three states the measured test counts from `app/facts.json` rather than a typed number. | Typed numbers; facts-driven. | One source of truth. `scripts/update_facts.py` re-syncs it before release. |
| 23:50 | Product page restructured into a title row, a sticky rail (cover + buy box) and a details column; the rail stops being sticky when the viewport is under 760 px tall or under 901 px wide, and the rail cover is 16:10 instead of 4:3. | Keep the old 2-column layout with a sticky cover only; scroll the rail inside itself. | A rail that scrolls inside itself showed a scrollbar (seen in a screenshot and removed). A shorter cover lets cover and buy box fit a 800 px window so the buy box is always in view; short windows fall back to normal flow. |
| 23:50 | A pending order now shows the stepper at step 2 (payment). | Leave it hidden; show step 2. | The brief asked for the stepper on every transactional page; a pending order is at the payment step. |
