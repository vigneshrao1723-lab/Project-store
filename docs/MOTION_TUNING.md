# Tuning the motion

Everything you are likely to want to change is in **`app/static/css/fx-tuning.css`** (numbers) and **`app/fx.json`**
(on/off switches). Edit, save, reload. Nothing else needs touching, no build step, no tests to update.

## Knobs (numbers)

Each is a CSS custom property in `fx-tuning.css`, named after the effect it belongs to.

| Knob | Default | What it changes | Good range |
|---|---|---|---|
| `--fx-speed` | `1` | **All motion.** A multiplier on every duration: `0.5` is twice as slow, `2` twice as fast. | 0.6 to 1.6 |
| `--fx-dist` | `14px` | **rise, cascade, zoom, flip, lines, words.** How far things travel as they come in. | 8px to 24px |
| `--fx-stagger` | `60ms` | **cascade, lines.** The delay between neighbouring items. | 30ms to 120ms |
| `--fx-ease` | `cubic-bezier(.2,.7,.2,1)` | **Every entrance and scene.** The easing curve. Try `ease-out` for a plainer feel. | `ease-out` to `cubic-bezier(.1,.9,.2,1)` |
| `--tilt-max` | `6` | **tilt.** The most a tile leans toward the pointer, in degrees (a plain number). | 2 to 10 |
| `--magnet-max` | `6` | **magnetic.** The most a button leans toward the pointer, in px (a plain number). | 2 to 10 |
| `--parallax-strength` | `1` | **parallax.** Multiplies the drift of the home hero layers and the product cover. `0` stops them. | 0 to 2 |
| `--cover-slide-distance` | `60vw` | **pin (home showcase, product scene).** How far off to the side the covers start. | 30vw to 100vw |
| `--loader-ms` | `1000ms` | **loader.** How long the intro loader stays before it fades out (the scene inside is unchanged; a 2s failsafe still hides it). | 600ms to 1600ms |
| `--cart-anim-ms` | `1000` | **cart-button.** Length of the Add to cart sequence in ms (a plain number; the script reads it too). | 600 to 1600 |
| `--pay-anim-ms` | `1400` | **pay-mark.** Length of the payment tick or cross sequence in ms (a plain number). | 900 to 2200 |
| `--bg-speed` | `1` | **bg3d.** How fast the 3D background drifts (also scaled by `--fx-speed`): `0` freezes it, `2` doubles it. | 0.3 to 1.6 |
| `--bg-brightness` | `.75` | **bg3d.** How bright the glossy solid is. Lower it if text feels busy over it. | 0.4 to 0.9 |
| `--marquee-speed` | `1` | **marquee.** Ticker speed: `0.5` half speed, `2` double. | 0.4 to 2 |

Examples of one-line edits: "tilt too strong" is `--tilt-max: 3;`; "everything feels slow" is `--fx-speed: 1.3;`;
"the covers fly in from too far" is `--cover-slide-distance: 40vw;`; "the background is too bright" is `--bg-brightness: .55;`; "turn the 3D off" is `{ "off": ["bg3d"] }`.

## Switches (on/off)

One list, in one place: `app/fx.json`.

```json
{ "off": ["tilt", "marquee"] }
```

The server writes it into `<html data-fx-off="tilt marquee">`, so the switch works at first paint, with no script, and
`fx-tuning.css` (`html[data-fx-off~="tilt"] ...`) forces the effect to its finished state and stops its animation.
`fx-scroll.js` reads the same attribute so scripted effects stand down too. Default is empty (everything on).
(`OFF` at the top of `fx-scroll.js` is a second list that is merged with it; leave it empty and use `app/fx.json`.)

| Switch | Turns off |
|---|---|
| `lines` | headline line-by-line reveal |
| `words` | word-by-word copy |
| `from-left`, `from-right`, `zoom`, `flip` | single-block entrances |
| `clip` | clip-path cover wipe |
| `draw` | drawn "How buying works" line |
| `hscroll` | pinned sideways shelf (becomes a swipe row) |
| `marquee` | stack ticker |
| `tilt` | tile tilt |
| `spotlight` | the amber disc that follows the pointer on tiles |
| `magnetic` | magnetic buttons |
| `rail` | section rail |
| `parallax` | all parallax layers |
| `view-transitions` | cross-page fade and the shared cover |
| `toasts` | toast styling (messages stay inline) |
| `stepper` | checkout stepper line drawing |
| `status-timeline` | order status line drawing |
| `admin-motion` | every effect on admin pages |
| `rise`, `cascade`, `count`, `pin` | the basic scroll words (pin leaves the showcase and product scene unpinned and finished) |
| `loader` | intro loader |
| `cards` | tile, plate and hero interactions (the category motifs) |
| `press`, `lift`, `wipe`, `focus-ring` | button press, card hover lift, link underline wipe, animated focus ring |
| `cart-button`, `count-bump` | Add to cart sequence, header count pulse |
| `cart-rows`, `cart-ticks`, `bob` | cart row slide-out, ticking totals, empty-state idle animation |
| `pay-mark` | payment tick/cross sequence and its fade-up |
| `hairline`, `header`, `footer` | scroll-progress line, condensed header, footer rise |
| `inputs`, `shake`, `forms` | field underline and tick, error shake, posting spinner |
| `downloads`, `drift` | download "preparing" state, drifting art behind sign in and register |
| `bg3d` | the 3D WebGL background (canvas and scrim); the still CSS gradient underneath stays |
| `ghost` | the hero headline's blur-to-sharp arrival |
| `page-fade` | the short page fade-in used where view transitions are unsupported |

Every effect in `docs/MOTION_INVENTORY.md` has a switch in its last column; a test checks that each one has a rule in
`fx-tuning.css` and that `app/fx.json` only names real switches.

## Adaptive quality

`html.fx-lite` is set automatically on weak devices (4 or fewer cores, 4 GB or less memory, or under 45 fps in the first half
second) and turns off only the heaviest items: pinned sticky stages become scroll-linked, the sideways shelf becomes a
swipe row, big parallax stops. Add `?fx=lite` or `?fx=full` to an address to force it either way when testing.
