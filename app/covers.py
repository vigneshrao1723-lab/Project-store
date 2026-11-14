"""Line-drawn cover art, generated per product so every project looks like its own drawing.

No colour is written here: every shape carries a class (cv-ln, cv-hl ...) and main.css paints it from the palette tokens,
so the covers follow the palette and a test can insist that hex literals live only in tokens.css."""
import hashlib
import random

from markupsafe import escape

W, H = 400, 300


def _rng(slug):
    return random.Random(int(hashlib.sha256(slug.encode()).hexdigest()[:12], 16))


def _lattice(r):
    cols, rows = 7, 5
    pts = {}
    for i in range(cols):
        for j in range(rows):
            pts[(i, j)] = (40 + i * 53 + r.randint(-14, 14), 38 + j * 56 + r.randint(-14, 14))
    out = []
    bx, by = r.randint(1, 3), r.randint(0, 2)
    out.append(f'<rect x="{40+bx*53-6}" y="{38+by*56-6}" width="{r.randint(110,150)}" height="{r.randint(90,120)}" class="cv-hl"/>')
    for (i, j), (x, y) in pts.items():
        for di, dj in ((1, 0), (0, 1), (1, 1)):
            q = pts.get((i + di, j + dj))
            if q and r.random() < 0.62:
                out.append(f'<line x1="{x}" y1="{y}" x2="{q[0]}" y2="{q[1]}" class="cv-ln" stroke-width="1.4"/>')
    for (x, y) in pts.values():
        rad = r.choice((3, 3, 3, 5, 7))
        kind = "cv-dot" if rad < 6 else "cv-ring"
        out.append(f'<circle cx="{x}" cy="{y}" r="{rad}" class="{kind}" stroke-width="1.4"/>')
    return "".join(out)


def _network(r):
    layers = [r.randint(3, 4), r.randint(4, 6), r.randint(4, 6), r.randint(2, 3)]
    xs = [60, 158, 256, 346]
    nodes = []
    for x, n in zip(xs, layers):
        gap = 232 / n
        nodes.append([(x, 34 + gap * (k + 0.5)) for k in range(n)])
    out = [f'<circle cx="{r.randint(150,260)}" cy="{r.randint(100,200)}" r="{r.randint(62,86)}" class="cv-hl"/>']
    for a, b in zip(nodes, nodes[1:]):
        for (x1, y1) in a:
            for (x2, y2) in b:
                if r.random() < 0.7:
                    out.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" class="cv-ln" stroke-width=".9" opacity=".55"/>')
    path = [r.choice(layer) for layer in nodes]
    out.append('<polyline points="' + " ".join(f"{x:.0f},{y:.0f}" for x, y in path) + f'" class="cv-acc" stroke-width="2.6" stroke-linejoin="round"/>')
    for layer in nodes:
        for (x, y) in layer:
            out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="5.5" class="cv-node" stroke-width="1.6"/>')
    return "".join(out)


def _web(r):
    out = []
    for k in range(3):
        x, y = 34 + k * 30 + r.randint(-6, 6), 36 + k * 36
        w, h = 250 + r.randint(-20, 20), 170
        kind = "cv-win cv-hl" if k == 1 else "cv-win"
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="{kind}" stroke-width="1.8"/>')
        out.append(f'<line x1="{x}" y1="{y+22}" x2="{x+w}" y2="{y+22}" class="cv-ln" stroke-width="1.4"/>')
        for d in range(3):
            out.append(f'<circle cx="{x+12+d*13}" cy="{y+11}" r="3" class="cv-dot"/>')
        for ln in range(4):
            lw = r.randint(60, w - 40)
            out.append(f'<line x1="{x+14}" y1="{y+46+ln*22}" x2="{x+14+lw}" y2="{y+46+ln*22}" class="cv-ln" stroke-width="2.2" stroke-linecap="round" opacity="{0.9 if ln==0 else 0.4}"/>')
    return "".join(out)


def _circuit(r):
    out = [f'<rect x="150" y="100" width="104" height="96" class="cv-chip" stroke-width="2"/>']
    for k in range(5):
        px = 162 + k * 20
        out.append(f'<line x1="{px}" y1="100" x2="{px}" y2="84" class="cv-ln" stroke-width="2"/>')
        out.append(f'<line x1="{px}" y1="196" x2="{px}" y2="212" class="cv-ln" stroke-width="2"/>')
    for k in range(4):
        py = 114 + k * 22
        out.append(f'<line x1="150" y1="{py}" x2="134" y2="{py}" class="cv-ln" stroke-width="2"/>')
        out.append(f'<line x1="254" y1="{py}" x2="270" y2="{py}" class="cv-ln" stroke-width="2"/>')
    out.append(f'<circle cx="164" cy="114" r="3.5" class="cv-dot"/>')
    for side in range(4):
        for t in range(r.randint(3, 4)):
            y = 38 + r.randint(0, 5) * 44 + t * 5
            x0, x1 = (134, r.randint(24, 80)) if side % 2 == 0 else (270, r.randint(320, 376))
            ym = y + r.choice((-30, 0, 30)) * (1 if side < 2 else -1)
            ym = max(24, min(276, ym))
            out.append(f'<polyline points="{x0},{114+(t*22)%88} {(x0+x1)//2},{114+(t*22)%88} {(x0+x1)//2},{ym} {x1},{ym}" class="cv-ln" stroke-width="1.5"/>')
            out.append(f'<circle cx="{x1}" cy="{ym}" r="5" class="cv-node" stroke-width="1.6"/>')
    return "".join(out)


_KINDS = {"crypto": _lattice, "ai": _network, "web": _web, "hardware": _circuit}


def cover_svg(slug, kind, title=""):
    body = _KINDS.get(kind, _web)(_rng(slug))
    safe_title = f"{escape(title)}"          # < > & ' " become entities, so a title cannot break out of the SVG
    label = f'<title>{safe_title}</title>' if safe_title else ""
    return (
        f'<svg class="cover" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{safe_title or "Project cover drawing"}" preserveAspectRatio="xMidYMid slice">{label}'
        f'<rect width="{W}" height="{H}" class="cv-bg"/>'
        f'<path d="M0 .5H{W}M0 {H/2}H{W}M0 {H-.5}H{W}" class="cv-grid"/>{body}</svg>'
    )
