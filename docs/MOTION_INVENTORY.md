# Motion inventory

Every motion effect on the `motion-3` branch, as of commit `892c96b` plus everything added since. This work is
**additive only**: `tests/test_fx_inventory.py` reads this table and fails if any listed hook (a literal string)
disappears from its file. To add an effect, add a row; to retire one, say so in the commit and remove its row on
purpose.

Columns: **Effect**, **Page** where the visitor sees it, **Hook** (the literal text that must be in the file), **File**, and **Switch**: the name that turns the effect off (see docs/MOTION_TUNING.md; `-` marks plumbing that is not itself an effect).

| Effect | Page | Hook | File | Switch |
|---|---|---|---|---|
| Intro loader markup | first page of a session | `data-loader` | app/templates/base.html | loader |
| Intro loader gate | every page | `intro-run` | app/static/js/motion-boot.js | loader |
| Intro loader scene | every page | `intro-run .loader` | app/static/css/main.css | loader |
| Category card interactions | home, catalogue, product | `data-motion="tile"` | app/templates/_macros.html | cards |
| Card interaction script | home, catalogue, product | `is-active` | app/static/js/motion.js | cards |
| Press feedback on buttons | everywhere | `data-press` | app/templates/product.html | press |
| Press feedback style | everywhere | `.btn[data-press].is-pressed` | app/static/css/main.css | press |
| Skeleton reveal states | legacy sections | `[data-reveal].is-pending` | app/static/css/main.css | rise |
| Add to cart: label out, cart rolls, item drops, tick draws | product | `atc-go` | app/templates/product.html | cart-button |
| Add to cart keyframes | product | `@keyframes atc-roll` | app/static/css/motion3.css | cart-button |
| Add to cart script | product | `dataset.state` | app/static/js/fx-cart.js | cart-button |
| Header cart count pulse | product, cart | `@keyframes fx-bump` | app/static/css/motion3.css | count-bump |
| Payment success mark | order detail | `result_mark('success'` | app/templates/order_detail.html | pay-mark |
| Payment failure mark | pay | `result_mark('failure'` | app/templates/pay.html | pay-mark |
| Payment mark drawing | order detail, pay | `@keyframes rs-draw` | app/static/css/motion3.css | pay-mark |
| Payment progress sweep | order detail, pay | `@keyframes rs-sweep` | app/static/css/motion3.css | pay-mark |
| Payment content fade-up | order detail, pay | `@keyframes rs-after` | app/static/css/motion3.css | pay-mark |
| Payment replay guard | order detail | `ps-paid-` | app/static/js/fx-pay.js | - |
| Rise: section heads | home, product | `{{ fx('rise') }}` | app/templates/home.html | rise |
| Rise: cover plate | product | `data-motion-kind="{{ p.category.cover_kind }}" {{ fx('rise') }}` | app/templates/product.html | rise |
| Cascade: story cards | home | `story-grid fx-zoomc" {{ fx('cascade') }}` | app/templates/home.html | cascade |
| Cascade: browse by field | home | `class="index fx-alt" {{ fx('cascade') }}` | app/templates/home.html | cascade |
| Cascade: shelf tiles | home | `data-motion-group="tiles" {{ fx('cascade') }}` | app/templates/home.html | cascade |
| Cascade: how buying works | home | `class="plain steps fx-flipc" {{ fx('cascade') }}` | app/templates/home.html | cascade |
| Cascade: catalogue grid | catalogue | `data-motion-group="tiles" {{ fx('cascade') }}` | app/templates/catalogue.html | cascade |
| Cascade: product details | product | `<dl class="def" {{ fx('cascade') }}>` | app/templates/product.html | cascade |
| Cascade: what is in the kit | product | `<ul {{ fx('cascade') }}>` | app/templates/product.html | cascade |
| Cascade: prose | product | `class="prose" {{ fx('cascade') }}` | app/templates/product.html | cascade |
| Cascade: related projects | product | `{{ fx('cascade') }}>{% for r in related %}` | app/templates/product.html | cascade |
| Count: four story figures | home | `fx_count(n_projects)` | app/templates/home.html | count |
| Count macro (target, sizer, live text) | home | `data-fx="count" data-to=` | app/templates/_macros.html | - |
| Home showcase, pinned and scroll-linked | home | `class="showcase pin-lg" {{ fx('pin') }}` | app/templates/home.html | pin |
| Showcase pinned stage | home | `position: sticky` | app/static/css/motion3.css | pin |
| Showcase covers slide in from both sides | home | `sc-cover fx-move` | app/templates/home.html | pin |
| Showcase headline crossfades through three lines | home | `sc-l3` | app/templates/home.html | pin |
| Showcase "Scroll" cue | home | `sc-cue` | app/templates/home.html | pin |
| Showcase scroll hint | home | `sc-hint` | app/templates/home.html | pin |
| Product scene, pinned on large screens | product | `scene pin-lg` | app/templates/product.html | pin |
| Product scene parallax | product | `sc-art" {{ fx('parallax') }}` | app/templates/product.html | parallax |
| Pin and parallax progress | home, product | `--fx-top` | app/static/js/fx-scroll.js | - |
| Scroll-progress hairline | browse pages | `fx-progress` | app/templates/base.html | hairline |
| Condensed header past 40 px | all but error pages | `is-condensed` | app/static/js/fx-scroll.js | header |
| Footer rise | all but error pages | `site-footer"{% if fx_page` | app/templates/base.html | footer |
| Focus brings elements in at once | all but error pages | `is-instant` | app/static/js/fx-scroll.js | rise |
| Adaptive quality (fx-lite) | all | `fx-lite` | app/static/js/fx-scroll.js | - |
| Cleanup on pagehide | all | `pagehide` | app/static/js/fx-scroll.js | - |
| Cart page heading | cart | `{{ fx('rise') }}` | app/templates/cart.html | rise |
| Checkout heading and summary | checkout | `aria-label="Order summary" {{ fx('cascade') }}` | app/templates/checkout.html | cascade |
| Pay page items | pay | `pay-items" {{ fx('cascade') }}` | app/templates/pay.html | cascade |
| Sign in heading | sign in | `<h1 {{ fx('rise') }}>Sign in` | app/templates/login.html | rise |
| Register heading | register | `<h1 {{ fx('rise') }}>Create an account` | app/templates/register.html | rise |
| Order rows | orders | `<tbody {{ fx('cascade') }}>` | app/templates/orders.html | cascade |
| Order detail rows | order detail | `<tbody {{ fx('cascade') }}>` | app/templates/order_detail.html | cascade |
| Shared tokens | all | `--fx-stagger` | app/static/css/motion3.css | - |
| Page class machinery | all | `data-page=` | app/templates/base.html | - |
| Headline line by line | home | `{{ fx('lines') }}` | app/templates/home.html | lines |
| Copy word by word | home, product | `{{ fx('words') }}` | app/templates/home.html | words |
| Product tagline word by word | product | `{{ fx_words(p.tagline) }}` | app/templates/product.html | words |
| Alternating card entrances (from left and right) | home, catalogue | `fx-alt` | app/static/css/motion3.css | cascade |
| Zooming card entrances | home, product | `fx-zoomc` | app/static/css/motion3.css | cascade |
| Flipping card entrances | home | `fx-flipc` | app/static/css/motion3.css | cascade |
| Single-block entrances from a side, zoom, flip | any | `[data-fx="from-left"]:not(.is-in)` | app/static/css/motion3.css | from-left |
| Clip-path wipe with scale-down for covers | home, catalogue, product | `{{ fx('clip') }}` | app/templates/_macros.html | clip |
| Product cover clip | product | `class="plate-cover" {{ fx('clip') }}` | app/templates/product.html | clip |
| Drawn "How buying works" timeline | home | `{{ fx('draw') }}` | app/templates/home.html | draw |
| Timeline line drawing | home | `stroke-dashoffset: calc(100 * (1 - var(--d)))` | app/static/css/motion3.css | draw |
| Sideways shelf driven by vertical scroll | home | `{{ fx('hscroll') }}` | app/templates/home.html | hscroll |
| Tech-stack marquee | home | `{{ fx('marquee') }}` | app/templates/home.html | marquee |
| Tile tilt and pointer spotlight | home, catalogue, product | `{{ fx('tilt') }}` | app/templates/_macros.html | tilt |
| Magnetic primary button | home | `{{ fx('magnetic') }}` | app/templates/home.html | magnetic |
| Section rail | home | `<nav class="rail"` | app/templates/home.html | rail |
| Section rail fill | home | `--rs` | app/static/js/fx-scroll.js | rail |
| Hero parallax, three layers | home | `px px-3` | app/templates/home.html | parallax |
| View transitions between pages | all | `@view-transition { navigation: auto; }` | app/static/css/motion3.css | view-transitions |
| Cover shared between card and product page | catalogue, product | `view-transition-name: cover` | app/static/css/motion3.css | view-transitions |
| Adaptive quality list of switches | all | `const OFF = [];` | app/static/js/fx-scroll.js | - |
| Settled arrivals lose their delay | all | `is-settled` | app/static/js/fx-scroll.js | - |
| Checkout progress stepper | cart, checkout, pay, order | `{% macro stepper(current) %}` | app/templates/_macros.html | stepper |
| Stepper line draws into the current step | cart, checkout, pay, order | `@keyframes fx-stp` | app/static/css/motion3-ui.css | stepper |
| Field underline draws from the left | checkout, sign in, register, admin forms | `.inp:focus-within .ul` | app/static/css/motion3-ui.css | inputs |
| Field error shake | sign in, register, checkout | `@keyframes fx-shake` | app/static/css/motion3-ui.css | shake |
| Field success tick draws | sign in, register, checkout | `.inp .ok path` | app/static/css/motion3-ui.css | inputs |
| Field markup (underline and tick) | every form | `<span class="inp">` | app/templates/_macros.html | - |
| Submit button spinner while posting | every form | `@keyframes fx-spin` | app/static/css/motion3-ui.css | forms |
| Double-submit guard and spinner script | every form | `posting.has(form)` | app/static/js/fx-ui.js | forms |
| Flash toasts slide in with a draining timer | every page | `@keyframes fx-drain` | app/static/css/motion3-ui.css | toasts |
| Toasts leave after six seconds (errors stay) | every page | `is-leaving` | app/static/js/fx-ui.js | toasts |
| Cart row slides away | cart | `@keyframes fx-ghost` | app/static/css/motion3-ui.css | cart-rows |
| Cart row ghost script | cart | `is-ghost` | app/static/js/fx-ui.js | cart-rows |
| Cart figures tick | cart | `@keyframes fx-tick` | app/static/css/motion3-ui.css | cart-ticks |
| Empty cart bobs | cart | `@keyframes fx-bob` | app/static/css/motion3-ui.css | bob |
| Empty cart line-art | cart | `class="empty-cart"` | app/templates/cart.html | bob |
| Pay amount zooms in | pay | `{{ fx('zoom') }}` | app/templates/pay.html | zoom |
| Order status timeline | order detail | `{% macro order_timeline(order) %}` | app/templates/_macros.html | status-timeline |
| Download preparing state | order detail | `is-preparing` | app/static/js/fx-ui.js | downloads |
| Drifting line-art behind the form | sign in, register | `class="drift"` | app/templates/login.html | drift |
| Drift keyframes | sign in, register | `@keyframes fx-drift-a` | app/static/css/motion3-ui.css | drift |
| Animated focus ring | everywhere | `@keyframes fx-ring` | app/static/css/motion3-ui.css | focus-ring |
| Press feedback | everywhere | `.btn:active` | app/static/css/motion3-ui.css | press |
| Link underline wipe | everywhere | `.nav a::after` | app/static/css/motion3-ui.css | wipe |
| Card hover lift | home, product, cart, order | `.fx-card:hover` | app/static/css/motion3-ui.css | lift |
| Admin: figures count up | admin dashboard | `fx_count(paid_count)` | app/templates/admin/dashboard.html | admin-motion |
| Admin: heading flips in | admin dashboard | `{{ fx('flip') }}` | app/templates/admin/dashboard.html | admin-motion |
| Admin: rows fade in | admin orders, products | `<tbody {{ fx('cascade') }}>` | app/templates/admin/orders.html | admin-motion |
| Admin: row hover | admin | `.admin .table tbody tr:hover` | app/static/css/motion3-ui.css | admin-motion |
| Interface script loaded on every page that moves | all but error pages | `js/fx-ui.js` | app/templates/base.html | - |
| Pointer spotlight disc | home, catalogue, product | `[data-fx="tilt"]::after` | app/static/css/motion3.css | spotlight |
| Showcase counter 01 / 02 / 03 | home | `class="sc-count"` | app/templates/home.html | pin |
| Showcase scene one, "Scroll to fill the shelf" | home | `Scroll to fill the shelf` | app/templates/home.html | pin |
| Showcase scene two, fields | home | `, one platform` | app/templates/home.html | pin |
| Showcase scene three, "Built to be checked" | home | `Built to be checked` | app/templates/home.html | pin |
| Hero headline blur-to-sharp arrival | home | `@keyframes fx-ghost` | app/static/css/motion3-ui.css | ghost |
| Product page sticky cover and buy box | product | `class="product-rail"` | app/templates/product.html | lift |
| Ring pulse behind the payment tick | order detail, pay | `@keyframes rs-pulse` | app/static/css/motion3.css | pay-mark |
| Stepper on a pending order | order detail | `elif order.status == 'pending' %}{{ stepper(2) }}` | app/templates/order_detail.html | stepper |
| Page fade where view transitions are unsupported | all | `@keyframes fx-page-in` | app/static/css/motion3-ui.css | page-fade |
| Empty orders line-art idle loop | orders | `empty-art empty-orders` | app/templates/orders.html | bob |
| Empty search line-art idle loop | catalogue | `empty-art empty-search` | app/templates/catalogue.html | bob |
