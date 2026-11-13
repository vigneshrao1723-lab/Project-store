# Decisions made without asking

The owner is not available overnight, so each decision is logged here with the time, the options and the reason.
Newest last.

| Time (IST) | Decision | Options considered | Why |
|---|---|---|---|
| 23:38 | The list of switched-off effects lives in `app/fx.json` (`{"off": []}`), read by the context processor and written into `<html data-fx-off="...">`; `fx-scroll.js` merges it with its own `OFF` constant (kept, empty). | (a) only the JS constant; (b) a data attribute typed into base.html; (c) a JSON file. | One array in one place, present at first paint so CSS-only effects (and view transitions) switch off with no script. The JS constant stays so the earlier tests and the "one list" comment remain true. |
| 23:38 | Knob defaults for `--cart-anim-ms` (1000) and `--pay-anim-ms` (1400) are unitless millisecond numbers, not lengths. | (a) lengths with typed division; (b) unitless numbers. | Dividing two lengths in `calc()` is not supported by older browsers; a unitless number works everywhere and `fx-cart.js` can read it. |
| 23:38 | `--loader-ms` changes when the intro loader starts to leave (default 1000ms); the loader scene's inner timings are unchanged. | Scale every loader keyframe, or only the hold time. | The loader's own tests pin its keyframes; the hold time is what "loader too long" means. |
