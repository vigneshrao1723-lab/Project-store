# Motion inventory

Every motion effect on the `motion-3` branch, as of commit `892c96b` plus everything added since. This work is
**additive only**: `tests/test_fx_inventory.py` reads this table and fails if any listed hook (a literal string)
disappears from its file. To add an effect, add a row; to retire one, say so in the commit and remove its row on
purpose.

Columns: **Effect**, **Page** where the visitor sees it, **Hook** (the literal text that must be in the file), **File**.

| Effect | Page | Hook | File |
|---|---|---|---|
| Intro loader markup | first page of a session | `data-loader` | app/templates/base.html |
| Intro loader gate | every page | `intro-run` | app/static/js/motion-boot.js |
| Intro loader scene | every page | `intro-run .loader` | app/static/css/main.css |
| Category card interactions | home, catalogue, product | `data-motion="tile"` | app/templates/_macros.html |
| Card interaction script | home, catalogue, product | `is-active` | app/static/js/motion.js |
| Press feedback on buttons | everywhere | `data-press` | app/templates/product.html |
| Press feedback style | everywhere | `.btn[data-press].is-pressed` | app/static/css/main.css |
| Skeleton reveal states | legacy sections | `[data-reveal].is-pending` | app/static/css/main.css |
| Add to cart: label out, cart rolls, item drops, tick draws | product | `atc-go` | app/templates/product.html |
| Add to cart keyframes | product | `@keyframes atc-roll` | app/static/css/motion3.css |
| Add to cart script | product | `dataset.state` | app/static/js/fx-cart.js |
| Header cart count pulse | product, cart | `@keyframes fx-bump` | app/static/css/motion3.css |
| Payment success mark | order detail | `result_mark('success'` | app/templates/order_detail.html |
| Payment failure mark | pay | `result_mark('failure'` | app/templates/pay.html |
| Payment mark drawing | order detail, pay | `@keyframes rs-draw` | app/static/css/motion3.css |
| Payment progress sweep | order detail, pay | `@keyframes rs-sweep` | app/static/css/motion3.css |
| Payment content fade-up | order detail, pay | `@keyframes rs-after` | app/static/css/motion3.css |
| Payment replay guard | order detail | `ps-paid-` | app/static/js/fx-pay.js |
| Rise: section heads | home, product | `{{ fx('rise') }}` | app/templates/home.html |
| Rise: cover plate | product | `data-motion-kind="{{ p.category.cover_kind }}" {{ fx('rise') }}` | app/templates/product.html |
| Cascade: story cards | home | `story-grid" {{ fx('cascade') }}` | app/templates/home.html |
| Cascade: browse by field | home | `class="index" {{ fx('cascade') }}` | app/templates/home.html |
| Cascade: shelf tiles | home | `data-motion-group="tiles" {{ fx('cascade') }}` | app/templates/home.html |
| Cascade: how buying works | home | `class="plain steps" {{ fx('cascade') }}` | app/templates/home.html |
| Cascade: catalogue grid | catalogue | `data-motion-group="tiles" {{ fx('cascade') }}` | app/templates/catalogue.html |
| Cascade: product details | product | `<dl class="def" {{ fx('cascade') }}>` | app/templates/product.html |
| Cascade: what is in the kit | product | `<ul {{ fx('cascade') }}>` | app/templates/product.html |
| Cascade: prose | product | `class="prose" {{ fx('cascade') }}` | app/templates/product.html |
| Cascade: related projects | product | `{{ fx('cascade') }}>{% for r in related %}` | app/templates/product.html |
| Count: four story figures | home | `fx_count(n_projects)` | app/templates/home.html |
| Count macro (target, sizer, live text) | home | `data-fx="count" data-to=` | app/templates/_macros.html |
| Home showcase, pinned and scroll-linked | home | `class="showcase" {{ fx('pin') }}` | app/templates/home.html |
| Showcase pinned stage | home | `position: sticky` | app/static/css/motion3.css |
| Showcase covers slide in from both sides | home | `sc-cover fx-move` | app/templates/home.html |
| Showcase headline crossfades through three lines | home | `sc-l3` | app/templates/home.html |
| Showcase "Scroll" cue | home | `sc-cue` | app/templates/home.html |
| Showcase scroll hint | home | `sc-hint` | app/templates/home.html |
| Product scene, pinned on large screens | product | `scene pin-lg` | app/templates/product.html |
| Product scene parallax | product | `sc-art" {{ fx('parallax') }}` | app/templates/product.html |
| Pin and parallax progress | home, product | `--fx-top` | app/static/js/fx-scroll.js |
| Scroll-progress hairline | browse pages | `fx-progress` | app/templates/base.html |
| Condensed header past 40 px | all but error pages | `is-condensed` | app/static/js/fx-scroll.js |
| Footer rise | all but error pages | `site-footer"{% if fx_page` | app/templates/base.html |
| Focus brings elements in at once | all but error pages | `is-instant` | app/static/js/fx-scroll.js |
| Adaptive quality (fx-lite) | all | `fx-lite` | app/static/js/fx-scroll.js |
| Cleanup on pagehide | all | `pagehide` | app/static/js/fx-scroll.js |
| Cart page heading | cart | `{{ fx('rise') }}` | app/templates/cart.html |
| Checkout heading and summary | checkout | `aria-label="Order summary" {{ fx('cascade') }}` | app/templates/checkout.html |
| Pay page items | pay | `pay-items" {{ fx('cascade') }}` | app/templates/pay.html |
| Sign in heading | sign in | `<h1 {{ fx('rise') }}>Sign in` | app/templates/login.html |
| Register heading | register | `<h1 {{ fx('rise') }}>Create an account` | app/templates/register.html |
| Order rows | orders | `<tbody {{ fx('cascade') }}>` | app/templates/orders.html |
| Order detail rows | order detail | `<tbody {{ fx('cascade') }}>` | app/templates/order_detail.html |
| Shared tokens | all | `--fx-stagger` | app/static/css/motion3.css |
| Page class machinery | all | `data-page=` | app/templates/base.html |
