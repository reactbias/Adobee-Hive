"""Adobee Hive — the pitch film. Three slides, about a minute.

Slide 1  the punchline: a bee leaves the Hive, more arrive, and they merge into one agent.
Slide 2  the vision: entities with their own folders, listed on hives as JSON, searched by agents.
Slide 3  the hotel journey: the ask, the hives, the match, two agents, and the human's yes.

Brand per documentation/BRAND.md — paper and ink with one accent, clay; Instrument Serif for
display, Mannin for text, Geist Mono for JSON and signatures. The model on screen is the one that
is built: ratings in tenths of a star, `rating: null` for unrated, a hub scored on
`published - realised`, and a whole `provenance.path` on every federated result.

    python hive_federation.py                 # the film -> ../hive-federation.mp4
    python hive_federation.py --stills        # one PNG per slide, all three slide-2 variants
    python hive_federation.py --variant b     # render the film with vision variant b
    python hive_federation.py --preview 2     # three frames of scene 2
"""

from __future__ import annotations

import argparse
import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H, SS, FPS = 1600, 900, 2, 30

# documentation/BRAND.md
PAPER = (246, 243, 237)
SURFACE = (255, 254, 251)
INK = (23, 20, 15)
INK2 = (75, 68, 58)
INK3 = (133, 124, 111)
LINE = (228, 222, 211)
CLAY = (162, 79, 44)
CLAYGLOW = (217, 139, 95)
CLAYDARK = (90, 46, 26)
BAD = (163, 50, 31)
WASH = (250, 240, 232)  # the chosen row, clay at a whisper

HERE = os.path.dirname(os.path.abspath(__file__))
# The brand faces ship once, with their licences, in the frontend. Read them from there and
# convert to a gitignored cache rather than keeping a second copy of a licensed binary.
WOFF2 = os.path.normpath(
    os.path.join(HERE, "..", "..", "code", "frontend", "public", "fonts")
)
FDIR = os.path.join(HERE, ".fontcache")


def _ensure_fonts() -> None:
    """Convert the bundled woff2 faces to ttf once, into the cache."""
    os.makedirs(FDIR, exist_ok=True)
    missing = [
        f for f in set(FILES.values()) if not os.path.exists(os.path.join(FDIR, f))
    ]
    if not missing:
        return
    from fontTools.ttLib import TTFont  # needs fonttools and brotli; see README.md

    for name in missing:
        src = os.path.join(WOFF2, name.replace(".ttf", ".woff2"))
        font = TTFont(src)
        font.flavor = None
        font.save(os.path.join(FDIR, name))


FILES = {
    "display": "InstrumentSerif-Regular.ttf",
    "italic": "InstrumentSerif-Italic.ttf",
    "text": "ManninDerivativeAdobee-Variable.ttf",
    "textb": "ManninDerivativeAdobee-Variable.ttf",
    "mono": "GeistMono-Variable.ttf",
    "monob": "GeistMono-Variable.ttf",
}
WEIGHT = {"text": 400, "textb": 650, "mono": 400, "monob": 600}
_fc: dict = {}


def F(kind: str, size: int):
    """Brand font at a supersampled size, with the right variable weight."""
    key = (kind, size)
    if key not in _fc:
        _ensure_fonts()
        f = ImageFont.truetype(os.path.join(FDIR, FILES[kind]), size * SS)
        if kind in WEIGHT:
            try:
                f.set_variation_by_axes([WEIGHT[kind]])
            except Exception:
                pass
        _fc[key] = f
    return _fc[key]


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t):
    return 1 - (1 - clamp(t)) ** 3


def ease_in(t):
    return clamp(t) ** 2


def seg(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else 1.0


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    t = clamp(t)
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def fade(c, t, ground=PAPER):
    return mix(ground, c, t)


def bez(p0, p1, p2, p3, u):
    """A point on a cubic bezier. The bees fly on these, so a flight reads as a flight."""
    v = 1 - u
    return (
        v**3 * p0[0] + 3 * v * v * u * p1[0] + 3 * v * u * u * p2[0] + u**3 * p3[0],
        v**3 * p0[1] + 3 * v * v * u * p1[1] + 3 * v * u * u * p2[1] + u**3 * p3[1],
    )


def bez_heading(p0, p1, p2, p3, u):
    """The direction of travel at u, so the bee points where it is going."""
    a = bez(p0, p1, p2, p3, max(0.0, u - 0.004))
    b = bez(p0, p1, p2, p3, min(1.0, u + 0.004))
    return math.atan2(b[1] - a[1], b[0] - a[0])


class Canvas:
    """A supersampled frame; all coordinates are in final-image pixels."""

    def __init__(self, bg=PAPER):
        self.img = Image.new("RGB", (W * SS, H * SS), bg)
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x, y, w, h, fill=None, outline=None, width=1):
        self.d.rectangle(
            [x * SS, y * SS, (x + w) * SS, (y + h) * SS],
            fill=fill,
            outline=outline,
            width=max(1, int(width * SS)),
        )

    def line(self, x1, y1, x2, y2, fill=INK, width=1):
        self.d.line(
            [x1 * SS, y1 * SS, x2 * SS, y2 * SS],
            fill=fill,
            width=max(1, int(width * SS)),
        )

    def dashed(self, x1, y1, x2, y2, fill=LINE, width=1.2, dash=8, gap=7):
        """A dashed rule, for a route that is proposed rather than travelled."""
        total = math.hypot(x2 - x1, y2 - y1)
        if total < 1:
            return
        step = (dash + gap) / total
        u = 0.0
        while u < 1.0:
            v = min(1.0, u + dash / total)
            self.line(
                lerp(x1, x2, u),
                lerp(y1, y2, u),
                lerp(x1, x2, v),
                lerp(y1, y2, v),
                fill,
                width,
            )
            u += step

    def arrow(self, x1, y1, x2, y2, fill=INK3, width=1.6, head=9):
        """A line that says which way the thing moves."""
        self.line(x1, y1, x2, y2, fill, width)
        ang = math.atan2(y2 - y1, x2 - x1)
        for s in (2.5, -2.5):
            self.line(
                x2, y2, x2 + head * math.cos(ang + s), y2 + head * math.sin(ang + s), fill, width
            )

    def text(self, x, y, s, kind="text", size=16, fill=INK, anchor="la", tracking=0.0):
        if tracking:
            f = F(kind, size)
            w = (
                sum(self.d.textlength(ch, font=f) + tracking * SS for ch in s)
                - tracking * SS
            )
            cx = x * SS - (w / 2 if anchor[0] == "m" else w if anchor[0] == "r" else 0)
            for ch in s:
                self.d.text((cx, y * SS), ch, font=f, fill=fill, anchor="l" + anchor[1])
                cx += self.d.textlength(ch, font=f) + tracking * SS
        else:
            self.d.text(
                (x * SS, y * SS), s, font=F(kind, size), fill=fill, anchor=anchor
            )

    def tw(self, s, kind="text", size=16):
        return self.d.textlength(s, font=F(kind, size)) / SS

    def hexagon(self, cx, cy, r, fill=None, outline=None, width=2, open_corners=False):
        """The brand hexagon: flat-top, optionally left open at the corners like the sketch."""
        pts = [
            (
                cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
                cy + r * math.sin(math.pi / 6 + i * math.pi / 3),
            )
            for i in range(6)
        ]
        if fill:
            self.d.polygon([(p[0] * SS, p[1] * SS) for p in pts], fill=fill)
        if outline:
            for i in range(6):
                a, b = pts[i], pts[(i + 1) % 6]
                if open_corners:
                    ax, ay = lerp(a[0], b[0], 0.13), lerp(a[1], b[1], 0.13)
                    bx, by = lerp(a[0], b[0], 0.87), lerp(a[1], b[1], 0.87)
                else:
                    ax, ay, bx, by = a[0], a[1], b[0], b[1]
                self.line(ax, ay, bx, by, outline, width)

    def dot(self, cx, cy, r, fill=INK):
        self.d.ellipse(
            [(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=fill
        )

    def oval(self, cx, cy, rx, ry, rot=0.0, fill=None, outline=None, width=1.0, n=26):
        """An ellipse at an angle. Pillow draws no rotated ellipse, so this is a polygon."""
        ca, sa = math.cos(rot), math.sin(rot)
        pts = []
        for i in range(n):
            th = 2 * math.pi * i / n
            px, py = rx * math.cos(th), ry * math.sin(th)
            pts.append(((cx + px * ca - py * sa) * SS, (cy + px * sa + py * ca) * SS))
        if fill:
            self.d.polygon(pts, fill=fill)
        if outline:
            self.d.line(
                pts + [pts[0]], fill=outline, width=max(1, int(width * SS)), joint="curve"
            )

    def seal(self, cx, cy, r, a=1.0, col=CLAY):
        """The signature seal: hexagon plus a tick."""
        self.hexagon(cx, cy, r, fill=fade(SURFACE, a), outline=fade(col, a), width=2.2)
        self.line(cx - r * 0.34, cy, cx - r * 0.08, cy + r * 0.28, fade(col, a), 2.6)
        self.line(
            cx - r * 0.08,
            cy + r * 0.28,
            cx + r * 0.36,
            cy - r * 0.26,
            fade(col, a),
            2.6,
        )

    # ------------------------------------------------------------------ the bee
    def bee(self, x, y, ang=0.0, s=18.0, a=1.0, flap=0.0, mirror=None):
        """The B6 bee, drawn along its heading: striped body, two loop wings, one antenna.

        `s` is the body length in final pixels and `flap` runs 0 to 1, opening the wings.
        `mirror` flips the bee about its own axis; left by default, so a bee flying leftwards
        keeps its back up instead of turning over. Drawn from the whiteboard mascot.
        """
        if a <= 0.02 or s < 1:
            return
        ca, sa = math.cos(ang), math.sin(ang)
        m = -1 if (ca < 0 if mirror is None else mirror) else 1

        def P(px, py):
            px, py = px * s, py * m * s
            return x + px * ca - py * sa, y + px * sa + py * ca

        # Wings first: the body sits on top of them.
        wing_ry = (0.10 + 0.14 * flap) * s
        for side in (-1, 1):
            wx, wy = P(-0.02, 0.30 * side)
            self.oval(
                wx,
                wy,
                0.50 * s,
                wing_ry,
                ang + side * m * (0.80 + 0.30 * flap),
                fill=fade(SURFACE, a * 0.8),
                outline=fade(INK3, a * 0.65),
                width=max(0.9, s * 0.045),
            )
        # Stinger, then the striped body from tail to head.
        tx, ty = P(-0.72, 0)
        bx, by = P(-0.52, 0)
        self.line(tx, ty, bx, by, fade(CLAYDARK, a), max(1.0, s * 0.06))
        for px, r, col in (
            (-0.50, 0.13, CLAYDARK),
            (-0.36, 0.19, CLAY),
            (-0.20, 0.235, CLAYDARK),
            (-0.02, 0.25, CLAY),
            (0.16, 0.225, CLAYDARK),
        ):
            cx, cy = P(px, 0)
            self.dot(cx, cy, r * s, fade(col, a))
        hx, hy = P(0.36, 0)
        self.dot(hx, hy, 0.185 * s, fade(INK, a))
        # One curly antenna, the mascot's tell.
        a1, a2, a3 = P(0.46, -0.10), P(0.60, -0.32), P(0.76, -0.28)
        self.line(a1[0], a1[1], a2[0], a2[1], fade(INK, a * 0.9), max(0.9, s * 0.045))
        self.line(a2[0], a2[1], a3[0], a3[1], fade(INK, a * 0.9), max(0.9, s * 0.045))

    def trail(self, p0, p1, p2, p3, u, a=1.0, span=0.22, n=9):
        """The last stretch of a bee's route, so the frame shows where it came from."""
        for i in range(n):
            uu = u - span * (i + 1) / n
            if uu <= 0:
                break
            px, py = bez(p0, p1, p2, p3, uu)
            self.dot(px, py, 1.5, fade(CLAYGLOW, a * 0.5 * (1 - i / n)))

    # ------------------------------------------------------------------ blocks
    def folder_icon(self, x, y, s=9, col=INK3):
        """A folder glyph, 1.4:1, drawn on the hexagon's line weight."""
        self.rect(x, y - s * 0.52, s * 0.45, s * 0.22, fill=col)
        self.rect(x, y - s * 0.34, s * 1.35, s * 0.86, fill=col)

    def tree(self, x, y, rows, a=1.0, size=15, lead=29, note_x=250):
        """A folder structure: depth, name, and a quiet note on the right.

        The shape of the owner's vault, never its contents — that is what a Card carries.
        """
        for i, (depth, name, note) in enumerate(rows):
            yy = y + i * lead
            ix = x + depth * 22
            self.folder_icon(ix, yy, size * 0.62, fade(INK3 if depth else INK2, a))
            self.text(
                ix + size * 0.62 * 1.35 + 9,
                yy,
                name,
                "mono",
                size,
                fade(INK if depth else INK2, a),
                anchor="lm",
            )
            if note:
                self.text(
                    x + note_x, yy, note, "mono", size - 2, fade(INK3, a), anchor="lm"
                )

    def json_line(self, x, y, s, a=1.0, size=13):
        """One line of JSON: the key quiet, the value in ink, so the eye lands on the value."""
        if '": ' in s:
            k, _, v = s.partition('": ')
            k += '": '
            self.text(x, y, k, "mono", size, fade(INK3, a), anchor="lm")
            self.text(
                x + self.tw(k, "mono", size),
                y,
                v,
                "monob",
                size,
                fade(INK, a),
                anchor="lm",
            )
        else:
            self.text(x, y, s, "mono", size, fade(INK3, a), anchor="lm")

    def json_card(self, x, y, w, lines, a=1.0, size=13, lead=22, label="JSON", pad=22):
        """The panel a hive actually serves: condensed JSON, nothing rendered."""
        h = pad * 2 + 26 + lead * len(lines)
        self.rect(x, y, w, h, fill=fade(SURFACE, a), outline=fade(INK3, a), width=1.5)
        self.text(
            x + pad,
            y + pad + 4,
            label,
            "monob",
            size - 1,
            fade(INK3, a),
            anchor="lm",
            tracking=1.6,
        )
        for i, ln in enumerate(lines):
            self.json_line(x + pad, y + pad + 30 + i * lead, ln, a, size)
        return h

    def chip(self, x, y, s, a=1.0, col=CLAY, size=12, pad=9):
        """A small mono label with a dot: a status is a dot and a word, never a pill."""
        self.dot(x + 3, y, 3.2, fade(col, a))
        self.text(x + 14, y, s, "mono", size, fade(col, a), anchor="lm")
        return 14 + self.tw(s, "mono", size) + pad

    def finish(self):
        return self.img.resize((W, H), Image.LANCZOS)


# --------------------------------------------------------------------- the film
SCENES = [
    ("Adobee Hive", 9.0),
    ("The vision", 12.5),
    ("The ask", 5.0),
    ("The hives", 10.0),
    ("The match", 8.0),
    ("Two agents", 8.5),
    ("Your yes", 5.5),
    ("Adobee Hive", 4.5),
]
TOTAL = sum(d for _, d in SCENES)

#: Which slide-2 version the film uses. --variant switches it; --stills writes all three.
VARIANT = "a"


def chrome(c: Canvas, idx: int, t_local: float):
    """Wordmark and a quiet progress rule."""
    c.hexagon(46, 46, 13, outline=CLAY, width=2, open_corners=True)
    c.dot(46, 46, 4.5, CLAY)  # the bee does not survive 26 px; the mark does
    c.text(70, 46, "Adobee Hive", "textb", 16, INK3, anchor="lm")
    c.text(W - 56, 46, SCENES[idx - 1][0], "mono", 12, INK3, anchor="rm", tracking=1.4)
    elapsed = sum(d for _, d in SCENES[: idx - 1]) + t_local
    c.line(56, 852, W - 56, 852, LINE, 1)
    c.line(56, 852, 56 + (W - 112) * clamp(elapsed / TOTAL), 852, CLAY, 2.5)


def eyebrow(c, x, y, s, a=1.0):
    c.text(x, y, s.upper(), "mono", 12, fade(CLAY, a), anchor="lm", tracking=2.2)


# ------------------------------------------------- 1 · punchline, and the bees
HOME = (322, 300)
MERGE = (1162, 300)

#: Each arriving agent's route: start, two controls, and the point they all become one.
FLIGHTS = [
    (HOME, (470, 436), (852, 430), MERGE, 0.20, 0.60),
    ((-150, 120), (220, 36), (700, 62), MERGE, 0.26, 0.605),
    ((706, -170), (862, -24), (1010, 92), MERGE, 0.30, 0.615),
    ((1782, 86), (1580, 36), (1392, 142), MERGE, 0.33, 0.625),
    ((1782, 452), (1556, 496), (1336, 406), MERGE, 0.36, 0.635),
    ((500, 540), (790, 520), (1004, 448), MERGE, 0.39, 0.645),
]

PUNCHLINE = "Agents don't browse. They ask the Hive."
SLOGAN = "One Hive. Many agents. No website in between."


def s_title(c, t, dur):
    """The mark, the bee that leaves it, five that arrive, and the agent they become."""
    p = t / dur

    # The logo: a bee in an open hexagon, drawn straight from the sketch.
    ha = ease(seg(p, 0.02, 0.18))
    c.hexagon(
        HOME[0], HOME[1], 104 * (0.94 + 0.06 * ha), outline=fade(CLAY, ha), width=4.5,
        open_corners=True,
    )
    if p < 0.21:
        # Still at home, wings going, about to leave.
        c.bee(HOME[0], HOME[1], -0.28, 40 * ha, ha, abs(math.sin(t * 17)))
    # Once it has gone, the cell is not empty: the entities the Hive lists stay behind.
    ca = ease(seg(p, 0.24, 0.42))
    for ex, ey in ((-34, -20), (0, 24), (34, -20)):
        c.hexagon(HOME[0] + ex, HOME[1] + ey, 21, outline=fade(INK3, ca * 0.8), width=1.6, open_corners=True)
    c.text(
        HOME[0], HOME[1] + 142, "THE HIVE", "mono", 13,
        fade(INK3, ease(seg(p, 0.10, 0.24))), anchor="mm", tracking=2.4,
    )

    # Six agents converge. The first one came out of the Hive; the others from elsewhere.
    for p0, p1, p2, p3, t0, t1 in FLIGHTS:
        u = seg(p, t0, t1)
        if u <= 0 or u >= 1:
            continue
        uu = ease_out(u) if p0 == HOME else ease(u)
        x, y = bez(p0, p1, p2, p3, uu)
        a = ease(seg(u, 0.0, 0.10)) * (1 - ease_in(seg(u, 0.86, 1.0)))
        c.trail(p0, p1, p2, p3, uu, a)
        c.bee(
            x, y, bez_heading(p0, p1, p2, p3, uu), 20 * (1 - 0.45 * seg(u, 0.8, 1.0)),
            a, abs(math.sin(t * 19 + p0[0])),
        )

    # The merge: one pulse, then the mark again — many bees, one agent.
    pulse = seg(p, 0.60, 0.78)
    if 0 < pulse < 1:
        c.hexagon(
            MERGE[0], MERGE[1], 60 + 90 * ease_out(pulse),
            outline=fade(CLAYGLOW, (1 - pulse) * 0.7), width=2, open_corners=True,
        )
    ma = ease(seg(p, 0.60, 0.74))
    if ma > 0.01:
        pop = 1 + 0.22 * (1 - ease_out(seg(p, 0.60, 0.80)))
        c.hexagon(
            MERGE[0], MERGE[1], 104 * pop, outline=fade(CLAY, ma), width=4.5,
            open_corners=True,
        )
        c.bee(MERGE[0], MERGE[1], -0.18, 46 * ma * pop, ma, abs(math.sin(t * 13)))
        c.text(
            MERGE[0], MERGE[1] + 142, "ONE AGENT", "mono", 13, fade(CLAY, ma),
            anchor="mm", tracking=2.4,
        )

    # The words, once the picture has been made.
    ta = ease(seg(p, 0.70, 0.86))
    c.text(56, 604, "Adobee Hive", "display", 76, fade(INK, ta), anchor="lm")
    pa = ease(seg(p, 0.76, 0.92))
    c.text(56, 684, PUNCHLINE, "display", 44, fade(CLAY, pa), anchor="lm")
    la = ease(seg(p, 0.82, 0.96))
    c.line(56, 718, 56 + 320 * ease_out(seg(p, 0.82, 1.0)), 718, fade(CLAY, la), 2.5)
    c.text(56, 756, SLOGAN, "text", 23, fade(INK2, la), anchor="lm")
    c.text(
        56, 800, "Team B6  ·  BaselHack 2026  ·  Adobe, The Post-Website Business",
        "mono", 13, fade(INK3, la), anchor="lm", tracking=1.2,
    )


# ------------------------------------------------------------- 2 · the vision
VISION_HEAD = "An internet agents can read."
VISION_SUB = "People and businesses are entities. Hives list them. Agents do the walking."

ENTITY_TREE = [
    (0, "hotel-krafft/", ""),
    (1, "rooms/", "26 files"),
    (1, "rates/", "8 files"),
    (1, "house/", "5 files"),
    (1, "guests/", "private"),
]
CARD_JSON = [
    "{",
    '  "name": "Hotel Krafft Basel",',
    '  "rating": 43,',
    '  "rating_count": 18,',
    '  "offers": ["room-booking"],',
    '  "needs": ["frontdesk-spring"],',
    '  "sig": "ed25519:f10a9c3b…"',
    "}",
]
#: What each hive says about the hives it connects to: published - realised, tenths of a star.
PEERS = [
    ("hub.basel.swiss", "0", "calibrated"),
    ("hotels.nordwest.ch", "-3", "under-promises"),
    ("hub.loerrach.de", "+11", "over-promises"),
]


def _vision_head(c, p):
    """The two lines every version of this slide carries."""
    eyebrow(c, 56, 150, "The vision", ease(seg(p, 0, 0.08)))
    c.text(56, 206, VISION_HEAD, "display", 46, fade(INK, ease(seg(p, 0.02, 0.16))), anchor="lm")
    c.text(56, 256, VISION_SUB, "text", 20, fade(INK2, ease(seg(p, 0.08, 0.22))), anchor="lm")


def _two_ratings(c, p, y, a0=0.72):
    """The two kinds of rating, said plainly. This is the part juries ask about."""
    a = ease(seg(p, a0, a0 + 0.14))
    c.line(56, y - 34, W - 56, y - 34, fade(LINE, a), 1)
    c.text(
        56, y, "A hive rates its entities only from a signed receipt or a scored meeting.",
        "text", 19, fade(INK2, a), anchor="lm",
    )
    b = ease(seg(p, a0 + 0.06, a0 + 0.20))
    c.text(
        56, y + 32, "And it rates the hives it connects to: published minus realised, in tenths of a star.",
        "text", 19, fade(INK2, b), anchor="lm",
    )
    c.text(
        56, y + 64, "Lower is better. A hive is judged on whether it told the truth about its members.",
        "textb", 19, fade(CLAY, b), anchor="lm",
    )


def v_flow(c, p):
    """Version A — four steps in reading order: entity, hive, search, match."""
    _vision_head(c, p)
    xs = [56, 448, 840, 1232]
    cw = 312
    steps = [
        ("1 · entity", "A person or a business. Their context stays in their own folders."),
        ("2 · hive", "The hive lists it as JSON. Not a website: JSON is what an agent reads."),
        ("3 · search", "A business builds an agent from its own entity and sends it across several hives."),
        ("4 · match", "The matched entity becomes an agent too. The two agents talk."),
    ]
    for i, (label, caption) in enumerate(steps):
        a = ease(seg(p, 0.18 + i * 0.11, 0.36 + i * 0.11))
        if a <= 0.01:
            continue
        x = xs[i]
        c.text(x, 320, label.upper(), "monob", 12, fade(CLAY, a), anchor="lm", tracking=2.0)
        c.line(x, 336, x + cw, 336, fade(LINE, a), 1)
        if i:
            c.arrow(xs[i] - 58, 470, xs[i] - 22, 470, fade(INK3, a), 1.6, 8)

        if i == 0:
            c.rect(x, 360, cw, 212, fill=fade(SURFACE, a), outline=fade(INK3, a), width=1.5)
            c.tree(x + 22, 396, ENTITY_TREE, a, 14, 27, note_x=188)
            c.text(x + 22, 548, "shape, never contents", "mono", 12, fade(INK3, a), anchor="lm")
        elif i == 1:
            c.json_card(x, 360, cw, CARD_JSON, a, 12, 20, label="CARD", pad=18)
        elif i == 2:
            rx = x + 48
            c.dashed(rx - 30, 364, rx - 30, 540, fade(CLAYGLOW, a), 1.4, 6, 6)
            for j, (hub, err, _) in enumerate(PEERS):
                hy = 392 + j * 66
                c.hexagon(rx, hy, 24, fill=fade(SURFACE, a), outline=fade(CLAY if j < 2 else INK3, a), width=2.2, open_corners=True)
                c.text(rx + 36, hy - 9, hub, "mono", 12, fade(INK, a), anchor="lm")
                c.text(rx + 36, hy + 11, f"peer error {err}", "mono", 11, fade(INK3, a), anchor="lm")
            bu = (p * 1.7) % 1.0
            c.bee(rx - 30, lerp(364, 540, bu), math.pi / 2, 18, a, abs(math.sin(p * 52)))
            c.text(x, 568, "several hives, one search", "mono", 12, fade(INK3, a), anchor="lm")
        else:
            for j, (cxx, name) in enumerate(((x + 62, "needs"), (x + 232, "offers"))):
                c.hexagon(cxx, 430, 40, fill=fade(SURFACE, a), outline=fade(CLAY, a), width=2.4, open_corners=True)
                c.bee(cxx, 430, -0.2 if j == 0 else math.pi, 24, a, 0.5)
                c.text(cxx, 486, name, "mono", 12, fade(INK3, a), anchor="mm")
            c.line(x + 106, 430, x + 188, 430, fade(CLAY, a), 2)
            c.dot(x + 147, 430, 3.4, fade(CLAY, a))
            c.text(x, 548, "no website in between", "mono", 12, fade(CLAY, a), anchor="lm")

        for j, ln in enumerate(_wrap(c, caption, cw, "text", 17)):
            c.text(x, 606 + j * 25, ln, "text", 17, fade(INK2, a), anchor="lm")

    _two_ratings(c, p, 724, 0.70)


HUBS_B = [
    ("hub.basel.swiss", 756, 420, 52, "0"),
    ("hotels.nordwest.ch", 1022, 332, 46, "-3"),
    ("basel-hotelverband.ch", 1120, 548, 44, "+2"),
    ("hub.loerrach.de", 1388, 416, 40, "+11"),
]
EDGES_B = [(0, 1, "-3"), (0, 2, "+2"), (1, 3, "+11"), (2, 3, "+6")]


def v_network(c, p):
    """Version B — the federation as a graph: entities below, hives above, errors on the edges."""
    _vision_head(c, p)

    a0 = ease(seg(p, 0.14, 0.30))
    c.rect(56, 318, 300, 232, fill=fade(SURFACE, a0), outline=fade(INK3, a0), width=1.5)
    c.text(78, 352, "ENTITY", "monob", 12, fade(CLAY, a0), anchor="lm", tracking=2.0)
    c.tree(78, 392, ENTITY_TREE, a0, 14, 27, note_x=182)
    c.text(78, 526, "a person, or a business", "mono", 12, fade(INK3, a0), anchor="lm")
    for i, ln in enumerate(
        [
            "The entity keeps its own folders.",
            "The hive carries a signed JSON card, not a page.",
            "An agent is built from an entity, and goes looking.",
        ]
    ):
        a = ease(seg(p, 0.46 + i * 0.07, 0.62 + i * 0.07))
        c.dot(62, 596 + i * 34, 3.4, fade(CLAY, a))
        c.text(80, 596 + i * 34, ln, "text", 18, fade(INK2, a), anchor="lm")

    ea = ease(seg(p, 0.26, 0.40))
    for i, j, err in EDGES_B:
        ax, ay, ar = HUBS_B[i][1], HUBS_B[i][2], HUBS_B[i][3]
        bx, by, br = HUBS_B[j][1], HUBS_B[j][2], HUBS_B[j][3]
        ang = math.atan2(by - ay, bx - ax)
        x1, y1 = ax + ar * math.cos(ang), ay + ar * math.sin(ang)
        x2, y2 = bx - br * math.cos(ang), by - br * math.sin(ang)
        c.line(x1, y1, x2, y2, fade(INK3, ea * 0.8), 1.5)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        c.rect(mx - 22, my - 12, 44, 24, fill=fade(PAPER, ea))
        # Over half a star of exaggeration is the only one worth colouring as a warning.
        c.text(mx, my, err, "monob", 13, fade(BAD if int(err) > 5 else CLAY, ea), anchor="mm")

    for i, (name, hx, hy, r, _) in enumerate(HUBS_B):
        a = ease(seg(p, 0.20 + i * 0.05, 0.36 + i * 0.05))
        c.hexagon(hx, hy, r, fill=fade(SURFACE, a), outline=fade(CLAY if i < 3 else INK3, a), width=2.4, open_corners=True)
        c.text(hx, hy - 6, "hive", "mono", 12, fade(INK3, a), anchor="mm")
        c.text(hx, hy + 12, "JSON", "monob", 12, fade(INK, a), anchor="mm")
        c.text(hx, hy + r + 20, name, "mono", 12, fade(INK2, a), anchor="mm")

    # One agent, threading three of them, and the match at the end.
    ra = ease(seg(p, 0.42, 0.54))
    route = ((380, 420), (520, 340), (620, 360), (HUBS_B[0][1] - 58, HUBS_B[0][2] - 8))
    u = clamp((p - 0.42) / 0.30)
    if ra > 0.01:
        for k in range(1, 26):
            px, py = bez(*route, k / 26)
            c.dot(px, py, 1.4, fade(CLAYGLOW, ra * 0.55))
        bx, by = bez(*route, ease(u))
        c.bee(bx, by, bez_heading(*route, ease(u)), 20, ra, abs(math.sin(p * 44)))

    ma = ease(seg(p, 0.60, 0.74))
    c.text(HUBS_B[2][1] + 80, HUBS_B[2][2] + 4, "match", "monob", 13, fade(CLAY, ma), anchor="lm")
    c.arrow(HUBS_B[2][1] + 48, HUBS_B[2][2], HUBS_B[2][1] + 74, HUBS_B[2][2], fade(CLAY, ma), 1.6, 7)
    for j, cxx in enumerate((1322, 1444)):
        c.hexagon(cxx, 626, 36, fill=fade(SURFACE, ma), outline=fade(CLAY, ma), width=2.4, open_corners=True)
        c.bee(cxx, 626, -0.2 if j == 0 else math.pi, 22, ma, 0.5)
    c.line(1360, 626, 1406, 626, fade(CLAY, ma), 2)
    c.text(1383, 678, "two agents, talking", "mono", 12, fade(INK3, ma), anchor="mm")

    _two_ratings(c, p, 740, 0.74)


ENTITY_TREE_FULL = [
    (0, "hotel-krafft/", "visibility"),
    (1, "rooms/", "public-summary"),
    (1, "rates/", "public-summary"),
    (1, "house/", "public"),
    (1, "guests/", "private"),
    (1, "deals/", "omitted — shared"),
]
CARD_JSON_FULL = [
    "{",
    '  "id": "hive:hub.basel.swiss/hotel-krafft@…",',
    '  "kind": "business",',
    '  "name": "Hotel Krafft Basel",',
    '  "rating": 43,            // 4.3 / 5',
    '  "rating_count": 18,      // signed receipts',
    '  "offers": [{ "id": "room-booking", … }],',
    '  "needs":  [{ "id": "frontdesk-spring", … }],',
    '  "sig": "ed25519:f10a9c3b…"',
    "}",
]


def v_data(c, p):
    """Version C — the artefacts themselves: the folder shape, the card, and the two scores."""
    _vision_head(c, p)

    a0 = ease(seg(p, 0.14, 0.30))
    c.rect(56, 306, 520, 272, fill=fade(SURFACE, a0), outline=fade(INK3, a0), width=1.5)
    c.text(84, 340, "THE ENTITY'S OWN FOLDERS", "monob", 12, fade(CLAY, a0), anchor="lm", tracking=1.8)
    c.tree(84, 384, ENTITY_TREE_FULL, a0, 15, 30, note_x=250)
    c.text(56, 612, "The card carries the shape. The contents never leave.", "text", 17, fade(INK3, a0), anchor="lm")

    a1 = ease(seg(p, 0.26, 0.44))
    c.json_card(628, 306, 916, CARD_JSON_FULL, a1, 14, 23, label="WHAT THE HIVE SERVES", pad=22)
    c.text(628, 612, "No page is rendered. This is the whole listing.", "text", 17, fade(INK3, a1), anchor="lm")

    ra = ease(seg(p, 0.50, 0.64))
    c.line(56, 648, W - 56, 648, fade(LINE, ra), 1)
    cols = [("WHAT IS RATED", 56), ("BY WHAT", 560), ("WHAT YOU SEE", 1020)]
    for s, x in cols:
        c.text(x, 684, s, "mono", 12, fade(INK3, ra), anchor="lm", tracking=1.8)
    rows = [
        ("an entity on a hive", "a signed receipt, or a scored meeting", "rating 43  ·  4.3 / 5  ·  18 receipts"),
        ("a hive, by another hive", "published minus realised", "error -3  ·  under-promises  ·  lower is better"),
    ]
    for i, (what, by, shown) in enumerate(rows):
        a = ease(seg(p, 0.58 + i * 0.09, 0.74 + i * 0.09))
        yy = 726 + i * 42
        c.text(56, yy, what, "textb", 19, fade(INK, a), anchor="lm")
        c.text(560, yy, by, "text", 19, fade(INK2, a), anchor="lm")
        c.text(1020, yy, shown, "mono", 15, fade(CLAY if i else INK2, a), anchor="lm")
    fa = ease(seg(p, 0.80, 0.94))
    c.text(
        56, 812, "A hive is judged on whether it told the truth about its members, never on how good they were.",
        "italic", 22, fade(CLAY, fa), anchor="lm",
    )


VISIONS = {"a": v_flow, "b": v_network, "c": v_data}
VISION_NAMES = {"a": "flow", "b": "network", "c": "data"}


def s_vision(c, t, dur):
    """Slide 2, in whichever version the film is cut with."""
    VISIONS[VARIANT](c, t / dur)


def _wrap(c, s, width, kind="text", size=17):
    """Greedy wrap to a pixel width; the deck has no text box to do it for us."""
    out, line = [], ""
    for word in s.split():
        trial = f"{line} {word}".strip()
        if c.tw(trial, kind, size) > width and line:
            out.append(line)
            line = word
        else:
            line = trial
    if line:
        out.append(line)
    return out


# -------------------------------------------------------------- 3a · the ask
ASK_TREE = [
    (0, "mara/", ""),
    (1, "travel/", "quiet, dog"),
    (1, "calendar/", "20–22 Nov"),
    (1, "budget/", "CHF 200/night"),
]


def s_ask(c, t, dur):
    """The human says one sentence. Her agent is built from her own entity."""
    p = t / dur
    eyebrow(c, 56, 150, "The ask", ease(seg(p, 0, 0.12)))
    c.text(56, 206, "A room near Basel SBB.", "display", 46, fade(INK, ease(seg(p, 0.02, 0.18))), anchor="lm")

    a1 = ease(seg(p, 0.14, 0.32))
    c.rect(56, 282, 880, 112, fill=fade(SURFACE, a1), outline=fade(INK3, a1), width=1.5)
    c.text(84, 318, "MARA", "monob", 12, fade(INK3, a1), anchor="lm", tracking=2.0)
    c.text(84, 356, "“Quiet room near Basel SBB, Fri to Sun, under CHF 200. The dog comes along.”", "text", 21, fade(INK, a1), anchor="lm")

    a2 = ease(seg(p, 0.34, 0.52))
    c.rect(56, 418, 880, 96, fill=fade(WASH, a2))
    c.text(84, 450, "MARA'S AGENT", "monob", 12, fade(CLAY, a2), anchor="lm", tracking=2.0)
    c.text(84, 486, "Asking the hives.", "text", 21, fade(INK, a2), anchor="lm")

    # Her agent is not a product. It is built out of her entity, and it leaves.
    a3 = ease(seg(p, 0.46, 0.64))
    c.rect(1000, 282, 544, 232, fill=fade(SURFACE, a3), outline=fade(INK3, a3), width=1.5)
    c.text(1028, 318, "HER ENTITY", "monob", 12, fade(CLAY, a3), anchor="lm", tracking=2.0)
    c.tree(1028, 358, ASK_TREE, a3, 15, 30, note_x=238)
    c.text(1028, 486, "The agent is built from these folders.", "text", 16, fade(INK3, a3), anchor="lm")

    # Built, and gone: the bee leaves her folders and sets off for the hives.
    fl = seg(p, 0.60, 1.0)
    if fl > 0:
        route = ((1030, 452), (860, 600), (620, 600), (312, 492))
        u = ease(fl)
        bx, by = bez(*route, u)
        c.trail(*route, u, 1.0, 0.34)
        c.bee(bx, by, bez_heading(*route, u), 24, ease(seg(fl, 0, 0.1)), abs(math.sin(t * 20)))

    fa = ease(seg(p, 0.72, 0.90))
    c.text(56, 604, "She never opens a website. Neither does her agent.", "text", 21, fade(INK2, fa), anchor="lm")
    c.text(56, 644, "It knows what she wants because it was built from her own context.", "italic", 23, fade(CLAY, fa), anchor="lm")


# ------------------------------------------------------------- 3b · the hives
HIVES = [
    ("hub.basel.swiss", 920, 392, 60, "0", "calibrated", 34),
    ("hotels.nordwest.ch", 1188, 322, 50, "-3", "under-promises", 212),
    ("basel-hotelverband.ch", 1208, 562, 48, "+2", "calibrated", 96),
    ("hub.loerrach.de", 1396, 436, 38, "+11", "over-promises", 140),
]
HIVE_EDGES = [(0, 1), (0, 2), (1, 3), (2, 3)]
ROUTE = ((680, 452), (790, 300), (860, 322), (920, 392))


def s_hives(c, t, dur):
    """The agent forages: several hotel hives, each scored on how honestly it rates."""
    p = t / dur
    eyebrow(c, 56, 150, "The hives", ease(seg(p, 0, 0.10)))
    c.text(56, 206, "Her agent visits the hives.", "display", 46, fade(INK, ease(seg(p, 0.02, 0.16))), anchor="lm")
    c.text(56, 256, "Hotel hives, interconnected. It goes to the well-calibrated ones first.", "text", 20, fade(INK2, ease(seg(p, 0.08, 0.24))), anchor="lm")

    ea = ease(seg(p, 0.22, 0.36))
    for i, j in HIVE_EDGES:
        ax, ay, ar = HIVES[i][1], HIVES[i][2], HIVES[i][3]
        bx, by, br = HIVES[j][1], HIVES[j][2], HIVES[j][3]
        ang = math.atan2(by - ay, bx - ax)
        c.line(ax + ar * math.cos(ang), ay + ar * math.sin(ang), bx - br * math.cos(ang), by - br * math.sin(ang), fade(INK3, ea * 0.7), 1.5)

    for i, (name, hx, hy, r, err, verdict, members) in enumerate(HIVES):
        a = ease(seg(p, 0.14 + i * 0.06, 0.32 + i * 0.06))
        good = not err.startswith("+1")
        c.hexagon(hx, hy, r, fill=fade(SURFACE, a), outline=fade(CLAY if good else INK3, a), width=2.6 if good else 1.8, open_corners=True)
        c.text(hx, hy - 8, f"{members}", "textb", 20, fade(INK, a), anchor="mm")
        c.text(hx, hy + 14, "entities", "mono", 11, fade(INK3, a), anchor="mm")
        c.text(hx, hy + r + 22, name, "mono", 13, fade(INK2, a), anchor="mm")
        c.text(hx, hy + r + 42, f"peer error {err}  ·  {verdict}", "mono", 12, fade(CLAY if good else BAD, a), anchor="mm")

    # The flight, hive to hive, in the order the calibration suggests.
    fl = seg(p, 0.30, 0.78)
    if fl > 0:
        legs = [
            (ROUTE, 0.0, 0.34),
            (((920, 392), (1020, 292), (1110, 280), (1188, 322)), 0.34, 0.64),
            (((1188, 322), (1270, 420), (1150, 470), (1208, 562)), 0.64, 1.0),
        ]
        for route, s0, s1 in legs:
            u = seg(fl, s0, s1)
            if u <= 0:
                continue
            for k in range(1, 22):
                px, py = bez(*route, min(u, 1.0) * k / 22)
                c.dot(px, py, 1.4, fade(CLAYGLOW, 0.5))
            if u < 1.0:
                bx, by = bez(*route, ease(u))
                c.bee(bx, by, bez_heading(*route, ease(u)), 24, 1.0, abs(math.sin(t * 20)))

    # What comes back carries its whole route, origin first.
    pa = ease(seg(p, 0.56, 0.72))
    c.rect(56, 330, 580, 170, fill=fade(SURFACE, pa), outline=fade(INK3, pa), width=1.5)
    c.text(84, 364, "WHAT COMES BACK", "monob", 12, fade(CLAY, pa), anchor="lm", tracking=1.8)
    for i, ln in enumerate(
        [
            '"provenance": {',
            '  "path": ["hotels.nordwest.ch",',
            '           "hub.basel.swiss"],',
            '  "origin": "hotels.nordwest.ch", "hops": 1 }',
        ]
    ):
        a = ease(seg(p, 0.60 + i * 0.04, 0.74 + i * 0.04))
        c.json_line(84, 404 + i * 26, ln, a, 14)
    c.text(56, 532, "Origin first. A relaying hive cannot claim the card as its own.", "text", 17, fade(INK3, ease(seg(p, 0.72, 0.84))), anchor="lm")

    fa = ease(seg(p, 0.78, 0.92))
    c.text(56, 596, "A hive rates its entities. It also rates the hives it connects to:", "text", 20, fade(INK2, fa), anchor="lm")
    c.text(56, 632, "published minus realised, in tenths of a star. Lower is better; negative means it undersold.", "text", 20, fade(INK2, fa), anchor="lm")
    c.text(56, 676, "So loerrach.de at +11 is asked last, and its members rank lower everywhere.", "textb", 20, fade(CLAY, fa), anchor="lm")


# ------------------------------------------------------------- 3c · the match
MATCH_JSON = [
    "{",
    '  "id": "hive:hub.basel.swiss/hotel-krafft@…",',
    '  "name": "Hotel Krafft Basel",',
    '  "description": "26 rooms on the Rhine, since 1872.",',
    '  "rating": 43,  "rating_count": 18,',
    '  "offers": [{ "id": "room-booking",',
    '      "price": { "from": 165, "currency": "CHF" },',
    '      "terms": "Free cancellation 48h." }],',
    '  "contact": { "mcp": "https://hotelkrafft.example/mcp" },',
    '  "sig": "ed25519:f10a9c3b…"',
    "}",
]
KRAFFT_TREE = [
    (0, "hotel-krafft/", ""),
    (1, "rooms/", "26 files"),
    (1, "rates/", "8 files"),
    (1, "house/", "5 files"),
]


def s_match(c, t, dur):
    """The listing is condensed JSON. On a match, an agent is built out of the entity."""
    p = t / dur
    eyebrow(c, 56, 150, "The match", ease(seg(p, 0, 0.10)))
    c.text(56, 206, "One entity matches.", "display", 46, fade(INK, ease(seg(p, 0.02, 0.16))), anchor="lm")
    c.text(56, 256, "A hotel on a hive is not a page. It is this.", "text", 20, fade(INK2, ease(seg(p, 0.08, 0.24))), anchor="lm")

    ja = ease(seg(p, 0.14, 0.34))
    c.json_card(56, 306, 820, MATCH_JSON, ja, 14, 23, label="THE LISTING", pad=24)
    sa = ease(seg(p, 0.38, 0.52))
    c.seal(820, 640, 26, sa)
    c.text(84, 648, "signature checked by her agent, against the owner's key", "mono", 13, fade(CLAY, sa), anchor="lm")

    # The entity becomes an agent: the folders behind it, the hexagon in front.
    ba = ease(seg(p, 0.46, 0.64))
    c.arrow(906, 440, 976, 440, fade(INK3, ba), 1.8, 9)
    c.text(941, 410, "built from", "mono", 12, fade(INK3, ba), anchor="mm")
    c.rect(1010, 306, 534, 190, fill=fade(SURFACE, ba), outline=fade(INK3, ba), width=1.5)
    c.text(1038, 340, "THE HOTEL'S OWN FOLDERS", "monob", 12, fade(CLAY, ba), anchor="lm", tracking=1.8)
    c.tree(1038, 382, KRAFFT_TREE, ba, 14, 28, note_x=232)

    aa = ease(seg(p, 0.60, 0.78))
    if aa > 0.01:
        pop = 1 + 0.2 * (1 - ease_out(seg(p, 0.60, 0.84)))
        c.hexagon(1276, 620, 70 * pop, outline=fade(CLAY, aa), width=3.4, open_corners=True)
        c.bee(1276, 620, -0.2, 34 * aa, aa, abs(math.sin(t * 15)))
        c.text(1276, 716, "THE HOTEL'S AGENT", "mono", 13, fade(CLAY, aa), anchor="mm", tracking=2.2)

    fa = ease(seg(p, 0.78, 0.94))
    c.text(56, 762, "An agent is built out of the matched entity — now with everything the owner keeps,", "text", 20, fade(INK2, fa), anchor="lm")
    c.text(56, 796, "not only the lines the listing carries.", "textb", 20, fade(CLAY, fa), anchor="lm")


# ------------------------------------------------------------ 3d · two agents
TALK = [
    (0, "Mara's agent", "Fri 20 to Sun 22 November, two nights. Quiet side, one dog."),
    (1, "Krafft's agent", "Courtyard single, CHF 165 a night. Dogs welcome, no charge."),
    (0, "Mara's agent", "She lands late. Check-in after 19:00?"),
    (1, "Krafft's agent", "Desk until 23:00. Free cancellation 48 h. CHF 330 for the two nights."),
    (0, "Mara's agent", "Agreed, and held. Nothing is booked until she says yes."),
]


def s_talk(c, t, dur):
    """Two agents settle it between them. No website, no form, no call."""
    p = t / dur
    eyebrow(c, 56, 150, "Two agents", ease(seg(p, 0, 0.10)))
    c.text(56, 206, "Two agents. One conversation.", "display", 46, fade(INK, ease(seg(p, 0.02, 0.16))), anchor="lm")

    ha = ease(seg(p, 0.06, 0.20))
    for side, label, x in ((0, "MARA'S AGENT", 150), (1, "KRAFFT'S AGENT", 1450)):
        c.hexagon(x, 300, 44, fill=fade(SURFACE, ha), outline=fade(CLAY, ha), width=2.6, open_corners=True)
        c.bee(x, 300, -0.2 if side == 0 else math.pi, 26, ha, 0.5)
        c.text(x, 364, label, "mono", 12, fade(INK3, ha), anchor="mm", tracking=1.8)

    for i, (side, who, line) in enumerate(TALK):
        a = ease(seg(p, 0.18 + i * 0.12, 0.34 + i * 0.12))
        if a <= 0.01:
            continue
        yy = 288 + i * 84
        x = 240 if side == 0 else 1360
        anchor = "lm" if side == 0 else "rm"
        if side == 0:
            c.rect(x - 14, yy - 30, 760, 64, fill=fade(WASH, a * 0.9))
        else:
            c.rect(x - 746, yy - 30, 760, 64, fill=fade(SURFACE, a), outline=fade(LINE, a), width=1.2)
        c.text(x, yy - 10, who, "monob", 12, fade(CLAY if side == 0 else INK3, a), anchor=anchor, tracking=1.6)
        c.text(x, yy + 16, line, "text", 19, fade(INK, a), anchor=anchor)

    fa = ease(seg(p, 0.80, 0.94))
    c.line(56, 760, W - 56, 760, fade(LINE, fa), 1)
    c.text(56, 798, "Every term comes from the card the owner signed. Nothing was scraped and nothing was guessed.", "text", 20, fade(INK2, fa), anchor="lm")


# --------------------------------------------------------------- 3e · the yes
def s_yes(c, t, dur):
    """Agents negotiate. People decide. Only a signed receipt can leave a review."""
    p = t / dur
    eyebrow(c, 56, 150, "Your yes", ease(seg(p, 0, 0.12)))
    c.text(56, 206, "She says yes. Then it books.", "display", 46, fade(INK, ease(seg(p, 0.02, 0.18))), anchor="lm")

    a1 = ease(seg(p, 0.12, 0.30))
    c.rect(56, 288, 760, 228, fill=fade(SURFACE, a1), outline=fade(INK3, a1), width=1.6)
    c.text(88, 324, "YOUR AGENT ASKS", "monob", 12, fade(CLAY, a1), anchor="lm", tracking=2.0)
    c.text(88, 372, "Book the courtyard single at Hotel Krafft,", "text", 22, fade(INK, a1), anchor="lm")
    c.text(88, 404, "20 to 22 November, CHF 330 for two nights?", "text", 22, fade(INK, a1), anchor="lm")
    a2 = ease(seg(p, 0.34, 0.48))
    c.rect(88, 436, 168, 48, fill=fade(INK, a2))
    c.text(172, 460, "Approve", "textb", 19, fade(SURFACE, a2) if a2 > 0.5 else fade(PAPER, a2), anchor="mm")
    c.text(284, 460, "Decline", "text", 19, fade(INK3, a2), anchor="lm")

    a3 = ease(seg(p, 0.50, 0.66))
    c.text(88, 554, "She approves.", "italic", 26, fade(CLAY, a3), anchor="lm")

    # The receipt lands like a stamp.
    a4 = ease(seg(p, 0.58, 0.74))
    if a4 > 0.01:
        drop = 1 + 0.5 * (1 - ease_out(seg(p, 0.58, 0.80)))
        c.rect(880, 288 + 30 * (drop - 1), 664, 228, fill=fade(SURFACE, a4), outline=fade(CLAY, a4), width=1.8)
        c.text(912, 324, "SIGNED RECEIPT", "monob", 12, fade(CLAY, a4), anchor="lm", tracking=2.0)
        for i, ln in enumerate(
            [
                '"card_version": 47,',
                '"nights": 2,  "total_chf": 330,',
                '"receipt": "sha256:ee01…",',
                '"agent": "mara\'s agent"',
            ]
        ):
            a = ease(seg(p, 0.62 + i * 0.04, 0.76 + i * 0.04))
            c.json_line(912, 368 + i * 28, ln, a, 15)
        c.seal(1468, 470, 28, ease(seg(p, 0.72, 0.84)))

    fa = ease(seg(p, 0.78, 0.92))
    c.line(56, 620, W - 56, 620, fade(LINE, fa), 1)
    c.text(56, 662, "The receipt names the card version it was booked against.", "text", 20, fade(INK2, fa), anchor="lm")
    c.text(56, 698, "Only that receipt can leave a review. No stay, no review.", "text", 20, fade(INK2, fa), anchor="lm")
    c.text(56, 744, "Agents negotiate. People decide.", "italic", 26, fade(CLAY, ease(seg(p, 0.86, 0.98))), anchor="lm")


# ------------------------------------------------------------------- 4 · close
def s_close(c, t, dur):
    """Back to the mark, and the one line that says what this is for."""
    p = t / dur
    a = ease(seg(p, 0.04, 0.28))
    c.hexagon(W / 2, 318, 78, outline=fade(CLAY, a), width=4, open_corners=True)
    c.bee(W / 2, 318, -0.2, 36 * a, a, abs(math.sin(t * 12)))
    c.text(W / 2, 452, PUNCHLINE, "display", 54, fade(INK, ease(seg(p, 0.16, 0.44))), anchor="mm")
    a2 = ease(seg(p, 0.34, 0.60))
    c.text(W / 2, 528, "On GitHub you find projects to work on.", "text", 22, fade(INK2, a2), anchor="mm")
    c.text(W / 2, 562, "On Adobee Hive, agents find businesses and people to work with.", "text", 22, fade(INK2, a2), anchor="mm")
    a3 = ease(seg(p, 0.54, 0.78))
    c.line(W / 2 - 150, 614, W / 2 + 150, 614, fade(CLAY, a3), 2.5)
    c.text(W / 2, 656, "Adobee Hive  ·  Team B6  ·  BaselHack 2026", "mono", 15, fade(INK3, a3), anchor="mm", tracking=1.6)


RENDER = [s_title, s_vision, s_ask, s_hives, s_match, s_talk, s_yes, s_close]

#: One still per scene, named for the slide it belongs to in the deck.
STILLS = [
    "slide-1-punchline",
    "slide-2-vision",
    "slide-3a-the-ask",
    "slide-3b-the-hives",
    "slide-3c-the-match",
    "slide-3d-two-agents",
    "slide-3e-your-yes",
    "slide-4-close",
]


def frame(gt: float) -> Image.Image:
    """Render the frame at global time gt seconds."""
    acc = 0.0
    for i, (_, dur) in enumerate(SCENES):
        if gt < acc + dur or i == len(SCENES) - 1:
            c = Canvas()
            tl = clamp(gt - acc, 0, dur)
            RENDER[i](c, tl, dur)
            if 0 < i < len(SCENES) - 1:
                chrome(c, i + 1, tl)
            return c.finish()
        acc += dur
    raise AssertionError


def _still(i: int, at: float = 0.93) -> Image.Image:
    """The frame near the end of scene i, when everything on it has arrived."""
    return frame(sum(d for _, d in SCENES[:i]) + SCENES[i][1] * at)


def main() -> None:
    """Render the video, or stills for slides."""
    global VARIANT
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=int)
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--variant", choices=sorted(VISIONS), default=VARIANT)
    ap.add_argument("--fps", type=int, default=FPS)
    a = ap.parse_args()
    VARIANT = a.variant
    here = os.path.dirname(os.path.abspath(__file__))

    if a.preview:
        i = a.preview - 1
        acc = sum(d for _, d in SCENES[:i])
        for fr in (0.3, 0.65, 0.95):
            frame(acc + SCENES[i][1] * fr).save(
                os.path.join(here, f"prev-{a.preview}-{int(fr * 100)}.png")
            )
        print("previews written")
        return
    if a.stills:
        out_dir = os.path.join(here, "..", "slides")
        os.makedirs(out_dir, exist_ok=True)
        for i, name in enumerate(STILLS):
            if name == "slide-2-vision":
                for key, label in VISION_NAMES.items():
                    VARIANT = key
                    _still(i).save(os.path.join(out_dir, f"{name}-{key}-{label}.png"))
                VARIANT = a.variant
            else:
                _still(i).save(os.path.join(out_dir, f"{name}.png"))
        print("stills written")
        return

    import imageio.v2 as iio
    import numpy as np

    out = os.path.abspath(os.path.join(here, "..", "hive-federation.mp4"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n = int(TOTAL * a.fps)
    w = iio.get_writer(
        out,
        fps=a.fps,
        codec="libx264",
        quality=9,
        macro_block_size=8,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
    for k in range(n):
        w.append_data(np.asarray(frame(k / a.fps)))
        if k % 90 == 0:
            print(f"  {k:4d}/{n}", flush=True)
    w.close()
    print("wrote", out)


if __name__ == "__main__":
    main()
