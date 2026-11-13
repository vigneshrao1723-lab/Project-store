"""The browse-page variants: headline lines, word-by-word copy, alternating card entrances, clip reveals, the drawn
timeline, the sideways shelf, the marquee, tilt and magnetic feedback, the section rail, hero parallax, and view
transitions. Markup through the macros; rules in the stylesheet; behaviour in test_fx_scroll.py."""
import re
from pathlib import Path

from tests.test_fx_system import without_hover_media

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "app" / "static" / "css" / "motion3.css").read_text(encoding="utf-8").replace("\r\n", "\n")
BARE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
VARIANTS = BARE[BARE.index('html.fx-on [data-fx="cascade"] > .is-settled'):]


def block(css, prelude):
    """The inside of every @media block that starts with `prelude`, joined."""
    out, i = "", 0
    while True:
        i = css.find(prelude, i)
        if i < 0:
            assert out, prelude
            return out
        j = css.index("{", i)
        depth = 0
        for k in range(j, len(css)):
            depth += css[k] == "{"
            depth -= css[k] == "}"
            if depth == 0:
                break
        out += css[j + 1:k]
        i = k


# ---- markup ---------------------------------------------------------------------------------------------------------------

def test_the_macros_split_a_headline_into_masked_lines_and_numbered_words(client):
    home = client.get("/").get_data(as_text=True)
    h1 = re.search(r'<h1 class="h1" data-fx="lines">(.*?)</h1>', home, re.S).group(1)
    lines = re.findall(r'<span class="ln"><span>(.*?)</span></span> ', h1)
    assert len(lines) >= 4 and " ".join(lines) == "Real engineering projects, ready to run and ready to explain."
    lede = re.search(r'<p class="lede" data-fx="words">(.*?)</p>', home, re.S).group(1)
    words = re.findall(r'<span class="w">(.*?)</span>', lede)
    assert 10 <= len(words) <= 30 and " ".join(words).startswith("Every kit comes with the working source")


def test_only_the_first_thirty_words_are_wrapped_and_the_rest_stay_plain_text(app):
    from flask import render_template_string
    with app.test_request_context():
        out = render_template_string('{% from "_macros.html" import fx_words %}{{ fx_words(t) }}', t=" ".join(f"w{i}" for i in range(45)))
        assert out.count('class="w"') == 30 and out.strip().endswith("w44") and "<script" not in out
        assert render_template_string('{% from "_macros.html" import fx_words %}{{ fx_words(t) }}', t="<b>x</b> y").count("&lt;b&gt;") == 1


def test_a_headline_line_is_escaped(app):
    from flask import render_template_string
    with app.test_request_context():
        out = render_template_string('{% from "_macros.html" import fx_lines %}{{ fx_lines("a <i>b</i>", "c") }}')
    assert "&lt;i&gt;" in out and "<i>" not in out


def test_the_home_page_carries_every_browse_variant(client):
    home = client.get("/").get_data(as_text=True)
    assert 'class="story-grid fx-zoomc" data-fx="cascade"' in home and 'class="index fx-alt" data-fx="cascade"' in home
    assert 'class="plain steps fx-flipc" data-fx="cascade"' in home and '<div class="grid fx-alt" data-motion-group="tiles" data-fx="cascade">' in home
    tiles = len(re.findall(r'<a class="tile', home))
    assert tiles >= 4 and home.count('data-fx="tilt"') == tiles and home.count('data-fx="clip"') == tiles
    assert 'data-fx="magnetic"' in home and home.count('data-fx="parallax"') == 3


def test_the_timeline_is_four_real_steps_with_a_drawn_line(client, app):
    home = client.get("/").get_data(as_text=True)
    tl = home[home.index('class="tl-wrap"'):home.index("</svg>", home.index('class="tl-wrap"'))]
    assert 'data-fx="draw"' in tl
    assert re.findall(r"<h3>(.*?)</h3>", tl) == ["Choose", "Reserve stock", "Pay", "Download"]
    assert f"holds your copy for {app.config['RESERVATION_MINUTES']} minutes" in tl
    assert 'pathLength="100"' in tl and 'aria-hidden="true"' in tl


def test_the_marquee_lists_the_stack_twice_for_a_seamless_loop_and_hides_the_copy_from_readers(client):
    home = client.get("/").get_data(as_text=True)
    band = home[home.index('class="stack-band"'):home.index("</section>", home.index('class="stack-band"'))]
    rows = re.findall(r'<ul class="plain mq-row"( aria-hidden="true")?>(.*?)</ul>', band, re.S)
    assert len(rows) == 2 and rows[0][0] == "" and rows[1][0] != ""
    names = re.findall(r"<li>(.*?)</li>", rows[0][1])
    assert names == ["Flask", "MySQL", "Docker", "GitHub Actions", "pytest", "SQLAlchemy", "Razorpay"]
    assert re.findall(r"<li>(.*?)</li>", rows[1][1]) == names


def test_the_rail_has_one_dot_for_every_section_of_the_home_page(client):
    home = client.get("/").get_data(as_text=True)
    main = home[home.index("<main"):home.index("</main>")]
    sections = re.findall(r"<section\b", main)
    rail = re.search(r'<nav class="rail" aria-hidden="true"><ol>(.*?)</ol></nav>', home, re.S).group(1)
    assert rail.count("<li></li>") == len(sections) == 8
    assert len(re.findall(r"\.rail li:nth-child\(\d\)", BARE)) >= 7


def test_the_sideways_shelf_lists_real_projects_as_plain_links(client):
    home = client.get("/").get_data(as_text=True)
    shelf = home[home.index('class="shelf"'):home.index("</section>", home.index('class="shelf"'))]
    assert 'data-fx="hscroll"' in shelf and 'class="hs-stage fx-stage"' in shelf and 'class="plain hs-track"' in shelf
    assert shelf.count('class="hs-card"') >= 2 and shelf.count("<a ") == shelf.count('class="hs-card"')
    assert "tabindex" not in shelf


def test_the_showcase_has_three_headline_lines_and_a_scroll_cue_and_is_pinned(client):
    home = client.get("/").get_data(as_text=True)
    show = home[home.index('class="showcase pin-lg"'):home.index("</section>", home.index('class="showcase pin-lg"'))]
    assert show.count('class="sc-line') == 3 and 'class="sc-cue"' in show and "pin-soft" not in show


def test_covers_wipe_in_and_the_product_tagline_reads_word_by_word(client, rag):
    page = client.get(f"/p/{rag.slug}").get_data(as_text=True)
    assert '<div class="plate-cover" data-fx="clip">' in page
    assert re.search(r'<p class="lede" data-fx="words">(<span class="w">.*?</span> )+', page)
    assert "grid fx-zoomc" in (ROOT / "app" / "templates" / "product.html").read_text(encoding="utf-8")


# ---- stylesheet ------------------------------------------------------------------------------------------------------------

def test_every_new_hiding_rule_starts_with_html_fx_on_and_clip_path_is_the_only_new_property():
    for selector, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", re.sub(r"@keyframes [\w-]+ \{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", VARIANTS)):
        if re.search(r"opacity:\s*0\b", body) and "::after" not in selector:
            assert all(p.strip().startswith("html.fx-on") for p in selector.split(",")), selector
    assert re.search(r'\[data-fx="clip"\]:not\(\.is-in\) \{ clip-path: inset\(0 0 100% 0\); \}', VARIANTS)
    assert re.search(r'\[data-fx="clip"\]:not\(\.is-in\) > \.cover \{ transform: scale\(1\.08\); \}', VARIANTS)


def test_tilt_and_magnetic_exist_only_for_fine_pointers_and_stay_within_6_degrees_and_6px():
    inside = block(VARIANTS, "@media (hover: hover) and (pointer: fine)")
    assert '[data-fx="tilt"].is-tilting' in inside and '[data-fx="magnetic"]' in inside
    outside = without_hover_media(VARIANTS[:VARIANTS.rindex("@media (prefers-reduced-motion: reduce)")])
    assert 'data-fx="tilt"' not in outside and 'data-fx="magnetic"' not in outside
    js = (ROOT / "app" / "static" / "js" / "fx-scroll.js").read_text(encoding="utf-8")
    assert 'knob("--tilt-max", 6)' in js and 'knob("--magnet-max", 6)' in js         # the 6 degrees and 6 px defaults are the knobs' defaults


def test_the_spotlight_is_a_flat_disc_not_a_gradient():
    assert "gradient" not in VARIANTS and "box-shadow" not in VARIANTS and "filter:" not in VARIANTS and "blur" not in VARIANTS
    assert re.search(r'\[data-fx="tilt"\]::after \{[^}]*border-radius: 50%[^}]*background: var\(--mark\)', VARIANTS)


def test_the_marquee_is_css_only_pauses_on_hover_and_stops_for_reduced_motion():
    assert "html.fx-on:not(.fx-off-marquee) .mq-row { animation: fx-marquee" in VARIANTS
    assert "html.fx-on .marquee:hover .mq-row { animation-play-state: paused; }" in block(VARIANTS, "@media (hover: hover) and (pointer: fine)")
    assert re.search(r"@media \(prefers-reduced-motion: reduce\) \{ \.mq-row \{ animation: none;", VARIANTS)
    assert "setInterval" not in (ROOT / "app" / "static" / "js" / "fx-scroll.js").read_text(encoding="utf-8")


def test_the_rail_is_for_large_screens_and_browse_pages_only():
    assert re.search(r'@media \(min-width: 1100px\) \{\s*html\.fx-on body\[data-page="browse"\] \.rail \{ display: block; position: fixed', VARIANTS)
    assert re.search(r"\.rail \{ display: none; \}", VARIANTS)


def test_the_hero_layers_move_at_three_different_speeds_and_fx_lite_stops_them():
    speeds = re.findall(r"\.px-(\d) \{ --pm: (-?[\d.]+);", VARIANTS)
    assert len({s for _, s in speeds}) == 3
    assert 'html.fx-lite [data-fx="parallax"] { transform: none; }' in BARE


def test_view_transitions_are_a_progressive_enhancement_with_one_named_cover():
    inside = block(VARIANTS, "@media (prefers-reduced-motion: no-preference) {\n  @view-transition")
    assert "@view-transition { navigation: auto; }" in inside and "animation-duration: 180ms" in inside
    assert ".product .plate-cover { view-transition-name: cover; }" in inside
    assert ".tile:is(:hover, :focus-within, :active) .tile-cover { view-transition-name: cover; }" in inside
    assert inside.count("view-transition-name") == 2


def test_the_shelf_is_a_swipe_row_by_default_and_pinned_only_with_the_script_on_large_screens_without_lite():
    default = re.search(r"\.hs-stage \{[^}]*overflow-x: auto; scroll-snap-type: x mandatory;", VARIANTS)
    assert default
    pinned = block(VARIANTS, "@media (min-width: 900px)\n{") if False else VARIANTS[VARIANTS.index("@media (min-width: 900px) {\n  html.fx-on:not(.fx-lite) [data-fx=\"hscroll\"]"):]
    assert "position: sticky" in pinned and "html.fx-on:not(.fx-lite)" in pinned
    assert "sticky" not in VARIANTS[:VARIANTS.index("@media (min-width: 900px) {\n  html.fx-on:not(.fx-lite) [data-fx=\"hscroll\"]")]


def test_the_drawn_line_defaults_to_finished_without_the_script():
    assert re.search(r"\.tl-wrap \{[^}]*--d: 1;", VARIANTS)
    assert "stroke-dashoffset: calc(100 * (1 - var(--d)))" in VARIANTS


def test_reduced_motion_restores_every_variant():
    tail = VARIANTS[VARIANTS.rindex("@media (prefers-reduced-motion: reduce)"):]
    for needle in ('[data-fx="clip"]', ".fx-alt", '[data-fx="lines"]', '[data-fx="words"]', '[data-fx="hscroll"]', ".tl-draw { stroke-dashoffset: 0; }", "is-tilting"):
        assert needle in tail, needle


# ---- the three-scene showcase -----------------------------------------------------------------------------------------------

def test_the_showcase_is_three_scenes_with_a_counter_and_the_stated_headlines(client, app):
    home = client.get("/").get_data(as_text=True)
    show = home[home.index('class="showcase pin-lg"'):home.index("</section>", home.index('class="showcase pin-lg"'))]
    heads = re.findall(r"<h2 class=\"h2\"[^>]*>(.*?)</h2>", show)
    assert heads == ["Scroll to fill the shelf", "Four fields, one platform", "Built to be checked"]
    assert re.search(r'<p class="sc-count" aria-hidden="true">.*<b class="sc-n1">01</b><b class="sc-n2">02</b><b class="sc-n3">03</b>.* / 03</span></p>', show, re.S)
    assert show.count("sc-cover fx-move") == 4 and 'class="sc-cue"' in show


def test_the_second_headline_counts_the_real_fields_and_the_third_quotes_the_facts_file(client, rag, soc):
    from app.extensions import db
    from app.context import FACTS
    rag.is_active = False
    db.session.commit()
    home = client.get("/").get_data(as_text=True)
    assert "Three fields, one platform" in home
    assert f"{FACTS['tests']} automated tests, {FACTS['security_tests']} of them security checks" in home


def test_the_scenes_change_at_set_points_and_the_counter_follows_the_same_windows():
    seen = {m: (a, b) for m, a, b in re.findall(r"\.sc-l(\d), \.sc-n\d \{ --a: (-?[\d.]+); --b: (-?[\d.]+); \}", BARE)}
    assert seen == {"1": ("-1", ".36"), "2": (".3", ".7"), "3": (".64", "9")}
    assert ".sc-line, .sc-num b { --in:" in BARE and "opacity: min(var(--in), var(--out))" in BARE


def test_the_showcase_is_pinned_on_large_screens_and_scroll_linked_unpinned_on_phones():
    big = block(VARIANTS + BARE, "@media (min-width: 900px)")
    assert 'html.fx-on:not(.fx-lite) [data-fx="pin"].pin-lg .fx-stage { contain: layout paint; position: sticky' in big
    phone = block(BARE, "@media (max-width: 899px)")
    assert ".sc-count { position: static;" in phone and "html.fx-on .sc-cue" in phone
    assert "--pin-h: 300vh" in BARE
