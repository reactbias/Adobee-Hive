"""Adobee Hive — how the federated backend works. A 60-second explainer.

Renders an MP4 for the pitch deck: one signed card, many Hives, a search whose reach the
person chooses, and two separate levels of trust. Brand per documentation/BRAND.md —
paper and ink with one accent, clay; Instrument Serif for display, Mannin for text,
Geist Mono for tool names and signatures.

    python hive_federation.py              # 60s MP4 -> ../hive-federation.mp4
    python hive_federation.py --stills     # one PNG per scene -> ../slides/
    python hive_federation.py --preview 4  # three frames of scene 4
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


def seg(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else 1.0


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    t = clamp(t)
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def fade(c, t, ground=PAPER):
    return mix(ground, c, t)


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

    def finish(self):
        return self.img.resize((W, H), Image.LANCZOS)


SCENES = [
    ("Adobee Hive", 5.0),
    ("One card, signed", 8.0),
    ("Many Hives", 9.0),
    ("How far to look", 14.0),
    ("Two levels of trust", 12.0),
    ("Open ranking", 7.0),
    ("The front door, signed", 5.0),
]
TOTAL = sum(d for _, d in SCENES)


def chrome(c: Canvas, idx: int, t_local: float):
    """Wordmark and a quiet progress rule."""
    c.hexagon(46, 46, 13, outline=CLAY, width=2, open_corners=True)
    c.dot(46, 46, 4.5, CLAY)
    c.text(70, 46, "Adobee Hive", "textb", 16, INK3, anchor="lm")
    c.text(W - 56, 46, SCENES[idx - 1][0], "mono", 12, INK3, anchor="rm", tracking=1.4)
    elapsed = sum(d for _, d in SCENES[: idx - 1]) + t_local
    c.line(56, 852, W - 56, 852, LINE, 1)
    c.line(56, 852, 56 + (W - 112) * clamp(elapsed / TOTAL), 852, CLAY, 2.5)


def eyebrow(c, x, y, s, a=1.0):
    c.text(x, y, s.upper(), "mono", 12, fade(CLAY, a), anchor="lm", tracking=2.2)


# ---------------------------------------------------------------- 1 · title
def s_title(c, t, dur):
    p = t / dur
    a = ease(seg(p, 0.06, 0.40))
    cx, cy = 300, H / 2 - 30
    c.hexagon(
        cx,
        cy,
        86 * (0.9 + 0.1 * a),
        outline=fade(CLAY, a),
        width=4.5,
        open_corners=True,
    )
    c.hexagon(cx, cy, 40, fill=fade(CLAY, a * 0.92))
    c.text(
        430,
        cy - 34,
        "Adobee Hive",
        "display",
        78,
        fade(INK, ease(seg(p, 0.14, 0.46))),
        anchor="lm",
    )
    a2 = ease(seg(p, 0.30, 0.62))
    c.text(
        434,
        cy + 38,
        "The front door, signed.",
        "display",
        40,
        fade(CLAY, a2),
        anchor="lm",
    )
    a3 = ease(seg(p, 0.50, 0.80))
    c.line(
        434,
        cy + 78,
        434 + 300 * ease_out(seg(p, 0.52, 0.92)),
        cy + 78,
        fade(CLAY, a3),
        2.5,
    )
    c.text(
        434,
        cy + 116,
        "How the Hive works underneath",
        "text",
        21,
        fade(INK2, a3),
        anchor="lm",
    )
    c.text(
        434,
        cy + 146,
        "BaselHack 2026  ·  Team B6  ·  Adobe",
        "mono",
        13,
        fade(INK3, a3),
        anchor="lm",
        tracking=1.2,
    )


# ---------------------------------------------------------------- 2 · the card
CARD_ROWS = [
    ("name", "Hotel Rheinblick"),
    ("kind", "stay"),
    ("from_price_chf", "128"),
    ("features", "quiet · dog-friendly · near SBB"),
    ("availability", "live"),
]


def s_card(c, t, dur):
    p = t / dur
    eyebrow(c, 56, 150, "One card, signed", ease(seg(p, 0, 0.12)))
    c.text(
        56,
        206,
        "The business publishes the facts.",
        "display",
        46,
        fade(INK, ease(seg(p, 0.04, 0.24))),
        anchor="lm",
    )

    x, y = 56, 268
    ca = ease(seg(p, 0.14, 0.34))
    c.rect(x, y, 660, 300, fill=fade(SURFACE, ca), outline=fade(INK3, ca), width=1.6)
    c.text(
        x + 28,
        y + 40,
        "Hive card",
        "monob",
        15,
        fade(INK3, ca),
        anchor="lm",
        tracking=1.6,
    )
    for i, (k, v) in enumerate(CARD_ROWS):
        a = ease(seg(p, 0.22 + i * 0.06, 0.40 + i * 0.06))
        yy = y + 84 + i * 40
        c.text(x + 28, yy, k, "mono", 15, fade(INK3, a), anchor="lm")
        c.text(x + 250, yy, v, "text", 19, fade(INK, a), anchor="lm")

    sa = ease(seg(p, 0.54, 0.68))
    if sa > 0.01:
        sc = 1 + 0.45 * (1 - ease_out(seg(p, 0.54, 0.74)))
        c.seal(x + 600, y + 244, 34 * sc, sa)
        c.text(
            x + 28,
            y + 252,
            "signed by the owner",
            "mono",
            14,
            fade(CLAY, sa),
            anchor="lm",
            tracking=1.2,
        )
        c.text(
            x + 28,
            y + 276,
            "ed25519:b3f1c2a0…",
            "mono",
            13,
            fade(INK3, sa),
            anchor="lm",
        )

    ra = ease(seg(p, 0.62, 0.82))
    rx = 800
    c.text(rx, 300, "Not a website.", "display", 36, fade(INK, ra), anchor="lm")
    for i, ln in enumerate(
        [
            "An agent reads the card over MCP.",
            "It checks the signature itself.",
            "Any altered copy is turned away.",
        ]
    ):
        a = ease(seg(p, 0.68 + i * 0.06, 0.86 + i * 0.06))
        c.text(rx, 356 + i * 38, ln, "text", 21, fade(INK2, a), anchor="lm")
    fa = ease(seg(p, 0.84, 0.97))
    c.text(
        rx,
        500,
        "The owner writes it in plain words.",
        "italic",
        27,
        fade(CLAY, fa),
        anchor="lm",
    )


# ---------------------------------------------------------------- 3 · many hives
def ring_positions(n, cx, cy, r, rot=0.0):
    return [
        (
            cx + r * math.cos(rot + i * 2 * math.pi / n),
            cy + r * math.sin(rot + i * 2 * math.pi / n),
        )
        for i in range(n)
    ]


R1 = ring_positions(5, 820, 500, 190, -math.pi / 2)
R2 = ring_positions(10, 820, 500, 340, -math.pi / 2 + math.pi / 10)


def s_many(c, t, dur):
    p = t / dur
    eyebrow(c, 56, 150, "Many Hives", ease(seg(p, 0, 0.12)))
    c.text(
        56,
        206,
        "One Hive is a start.",
        "display",
        44,
        fade(INK, ease(seg(p, 0.02, 0.20))),
        anchor="lm",
    )
    c.text(
        56,
        258,
        "A town, an association, a trade body —",
        "text",
        21,
        fade(INK2, ease(seg(p, 0.18, 0.36))),
        anchor="lm",
    )
    c.text(
        56,
        290,
        "each can run one.",
        "text",
        21,
        fade(INK2, ease(seg(p, 0.22, 0.40))),
        anchor="lm",
    )
    for i, ln in enumerate(
        [
            "Hives peer with Hives.",
            "No one owns the index.",
            "Leaving means republishing one card.",
        ]
    ):
        a = ease(seg(p, 0.44 + i * 0.09, 0.64 + i * 0.09))
        c.text(56, 372 + i * 40, ln, "text", 20, fade(INK2, a), anchor="lm")
        c.line(56, 384 + i * 40, 56, 384 + i * 40, fade(CLAY, a), 2)

    home = ease(seg(p, 0.10, 0.26))
    c.hexagon(
        820,
        500,
        58,
        fill=fade(SURFACE, home),
        outline=fade(CLAY, home),
        width=3,
        open_corners=True,
    )
    c.text(820, 500, "Basel", "textb", 18, fade(INK, home), anchor="mm")

    for i, (hx, hy) in enumerate(R1):
        a = ease(seg(p, 0.30 + i * 0.05, 0.50 + i * 0.05))
        if a <= 0.01:
            continue
        ang = math.atan2(hy - 500, hx - 820)
        c.line(
            820 + 58 * math.cos(ang),
            500 + 58 * math.sin(ang),
            hx - 44 * math.cos(ang),
            hy - 44 * math.sin(ang),
            fade(INK3, a * 0.8),
            1.6,
        )
        c.hexagon(
            hx,
            hy,
            44,
            fill=fade(SURFACE, a),
            outline=fade(INK3, a),
            width=2,
            open_corners=True,
        )
    for i, (hx, hy) in enumerate(R2):
        a = ease(seg(p, 0.58 + i * 0.025, 0.76 + i * 0.025))
        if a <= 0.01:
            continue
        near = min(R1, key=lambda q: (q[0] - hx) ** 2 + (q[1] - hy) ** 2)
        ang2 = math.atan2(hy - near[1], hx - near[0])
        c.line(
            near[0] + 44 * math.cos(ang2),
            near[1] + 44 * math.sin(ang2),
            hx - 26 * math.cos(ang2),
            hy - 26 * math.sin(ang2),
            fade(LINE, a),
            1.3,
        )
        c.hexagon(
            hx,
            hy,
            26,
            fill=fade(SURFACE, a),
            outline=fade(LINE, a),
            width=1.6,
            open_corners=True,
        )


# ---------------------------------------------------------------- 4 · radius
STEPS = [
    (0, "this Hive only", 1, "34"),
    (1, "direct peers", 6, "412"),
    (2, "peers of peers", 16, "1 840"),
]


def s_radius(c, t, dur):
    p = t / dur
    eyebrow(c, 56, 150, "How far to look", ease(seg(p, 0, 0.08)))
    c.text(
        56,
        206,
        "The person sets the reach.",
        "display",
        46,
        fade(INK, ease(seg(p, 0.02, 0.16))),
        anchor="lm",
    )
    c.text(
        56,
        256,
        "Search one Hive, the neighbours, or the neighbours' neighbours.",
        "text",
        20,
        fade(INK2, ease(seg(p, 0.10, 0.26))),
        anchor="lm",
    )

    # which radius is live now
    k = 0 if p < 0.30 else 1 if p < 0.50 else 2
    grow = (
        seg(p, 0.30, 0.40)
        if k == 1
        else seg(p, 0.50, 0.60)
        if k == 2
        else seg(p, 0.14, 0.24)
    )

    cx, cy = 1050, 480
    c.hexagon(cx, cy, 54, fill=SURFACE, outline=CLAY, width=3, open_corners=True)
    c.text(cx, cy, "home", "textb", 15, INK, anchor="mm")

    for i, (hx, hy) in enumerate(R1):
        on = k >= 1
        a = ease(grow) if (k == 1 and on) else (1.0 if k >= 2 else 0.25)
        col = CLAY if on else LINE
        ang = math.atan2(hy - cy, hx - cx)
        hx2, hy2 = cx + (hx - 820) * 0.82, cy + (hy - 500) * 0.82
        c.line(
            cx + 58 * math.cos(ang),
            cy + 58 * math.sin(ang),
            hx2 - 44 * math.cos(ang),
            hy2 - 44 * math.sin(ang),
            fade(col if on else INK3, 0.9 if on else 0.35),
            1.8 if on else 1.2,
        )
        c.hexagon(
            hx2,
            hy2,
            40,
            fill=fade(SURFACE, 1),
            outline=fade(col, a if on else 0.4),
            width=2.4 if on else 1.5,
            open_corners=True,
        )
    for i, (hx, hy) in enumerate(R2):
        on = k >= 2
        hx2, hy2 = cx + (hx - 820) * 0.82, cy + (hy - 500) * 0.82
        near = min(R1, key=lambda q: (q[0] - hx) ** 2 + (q[1] - hy) ** 2)
        nx, ny = cx + (near[0] - 820) * 0.82, cy + (near[1] - 500) * 0.82
        a = ease(grow) if on else 0.3
        ang2 = math.atan2(hy2 - ny, hx2 - nx)
        c.line(
            nx + 44 * math.cos(ang2),
            ny + 44 * math.sin(ang2),
            hx2 - 26 * math.cos(ang2),
            hy2 - 26 * math.sin(ang2),
            fade(CLAY if on else LINE, a * 0.8),
            1.5 if on else 1,
        )
        c.hexagon(
            hx2,
            hy2,
            24,
            fill=SURFACE,
            outline=fade(CLAY if on else LINE, a),
            width=2 if on else 1.4,
            open_corners=True,
        )

    # the dial
    dx, dy = 56, 352
    for i, (r, label, hives, biz) in enumerate(STEPS):
        live = i == k
        a = ease(seg(p, 0.12 + i * 0.20, 0.22 + i * 0.20))
        yy = dy + i * 92
        if live:
            c.rect(dx - 14, yy - 30, 560, 76, fill=fade((250, 240, 232), 0.9))
        c.text(
            dx,
            yy,
            f"radius {r}",
            "monob",
            24,
            fade(CLAY if live else INK3, max(a, 0.35)),
            anchor="lm",
        )
        c.text(
            dx + 160,
            yy,
            label,
            "text",
            20,
            fade(INK if live else INK3, max(a, 0.3)),
            anchor="lm",
        )
        c.text(
            dx + 420,
            yy - 11,
            f"{hives} Hive" + ("" if hives == 1 else "s"),
            "mono",
            15,
            fade(INK2 if live else INK3, max(a, 0.3)),
            anchor="lm",
        )
        c.text(
            dx + 420,
            yy + 15,
            f"{biz} businesses",
            "mono",
            15,
            fade(INK2 if live else INK3, max(a, 0.3)),
            anchor="lm",
        )

    na = ease(seg(p, 0.70, 0.86))
    c.line(56, 650, 616, 650, fade(LINE, na), 1)
    for i, ln in enumerate(
        [
            "Each hop carries a deadline and a list of Hives already asked,",
            "so a search never loops and never runs away.",
            "Signatures are checked where the search ends, never taken on trust.",
        ]
    ):
        a = ease(seg(p, 0.72 + i * 0.06, 0.88 + i * 0.06))
        c.text(
            56,
            686 + i * 32,
            ln,
            "text",
            18,
            fade(INK2 if i < 2 else CLAY, a),
            anchor="lm",
        )


# ---------------------------------------------------------------- 5 · trust
def s_trust(c, t, dur):
    p = t / dur
    eyebrow(c, 56, 150, "Two levels of trust", ease(seg(p, 0, 0.10)))
    c.text(
        56,
        206,
        "A Hive is rated. So is a business.",
        "display",
        46,
        fade(INK, ease(seg(p, 0.02, 0.18))),
        anchor="lm",
    )

    la = ease(seg(p, 0.14, 0.32))
    c.rect(56, 268, 700, 290, fill=fade(SURFACE, la), outline=fade(INK3, la), width=1.6)
    c.hexagon(126, 330, 28, outline=fade(CLAY, la), width=2.4, open_corners=True)
    c.text(176, 330, "The Hive", "textb", 25, fade(INK, la), anchor="lm")
    c.text(
        176,
        360,
        "how well it vets, how honestly it ranks",
        "text",
        17,
        fade(INK3, la),
        anchor="lm",
    )
    for i, ln in enumerate(
        [
            "verification it declares, against what peers observe",
            "ranking policy — paid placement is a downgrade",
            "availability, and how often its cards fail a check",
        ]
    ):
        a = ease(seg(p, 0.24 + i * 0.06, 0.42 + i * 0.06))
        c.dot(92, 414 + i * 38, 3.5, fade(CLAY, a))
        c.text(110, 414 + i * 38, ln, "text", 18, fade(INK2, a), anchor="lm")
    a4 = ease(seg(p, 0.42, 0.56))
    c.text(
        92,
        528,
        "Each Hive judges its peers itself. There is no global score.",
        "italic",
        19,
        fade(CLAY, a4),
        anchor="lm",
    )

    ra = ease(seg(p, 0.30, 0.46))
    c.rect(
        800, 268, 744, 290, fill=fade(SURFACE, ra), outline=fade(INK3, ra), width=1.6
    )
    c.seal(870, 330, 28, ra)
    c.text(920, 330, "The business", "textb", 25, fade(INK, ra), anchor="lm")
    c.text(
        920, 360, "what it actually delivered", "text", 17, fade(INK3, ra), anchor="lm"
    )
    for i, ln in enumerate(
        [
            "reviews only from a signed booking receipt",
            "attestations from third parties, each signed",
            "no stay, no review — and nothing to buy",
        ]
    ):
        a = ease(seg(p, 0.40 + i * 0.06, 0.58 + i * 0.06))
        c.dot(836, 414 + i * 38, 3.5, fade(CLAY, a))
        c.text(854, 414 + i * 38, ln, "text", 18, fade(INK2, a), anchor="lm")
    a5 = ease(seg(p, 0.56, 0.70))
    c.text(
        836,
        528,
        "This travels with the business, from Hive to Hive.",
        "italic",
        19,
        fade(CLAY, a5),
        anchor="lm",
    )

    fa = ease(seg(p, 0.70, 0.84))
    c.line(56, 606, W - 56, 606, fade(LINE, fa), 1)
    c.text(56, 652, "rank", "mono", 20, fade(INK3, fa), anchor="lm")
    parts = [
        ("what was asked for", 150),
        ("× trust in the Hives it came through", 440),
        ("× distance", 880),
    ]
    for s, x in parts:
        c.text(x, 652, s, "text", 20, fade(INK, fa), anchor="lm")
    ga = ease(seg(p, 0.80, 0.94))
    c.text(
        56,
        700,
        "All three are shown separately, so a result can still say why it won.",
        "text",
        19,
        fade(INK2, ga),
        anchor="lm",
    )
    c.text(
        56,
        740,
        "A Hive that carries forged cards loses its peers' trust —",
        "text",
        19,
        fade(INK2, ga),
        anchor="lm",
    )
    c.text(
        56,
        772,
        "and every business on it ranks lower everywhere.",
        "textb",
        19,
        fade(CLAY, ga),
        anchor="lm",
    )


# ---------------------------------------------------------------- 6 · ranking
ROWS = [
    (
        "Hotel Rheinblick",
        "Basel",
        "0",
        "quiet side, dogs welcome, 240 m from SBB",
        True,
    ),
    ("Gasthof Kleinbasel", "Riehen", "1", "dogs welcome, 1.2 km from SBB", False),
    ("Pension Rhypark", "Lörrach", "2", "quiet, no dogs — excluded, says so", False),
]


def s_rank(c, t, dur):
    p = t / dur
    eyebrow(c, 56, 150, "Open ranking", ease(seg(p, 0, 0.12)))
    c.text(
        56,
        206,
        "Every answer says why.",
        "display",
        46,
        fade(INK, ease(seg(p, 0.02, 0.20))),
        anchor="lm",
    )
    c.text(
        56,
        256,
        "And where it came from, and how far away that was.",
        "text",
        20,
        fade(INK2, ease(seg(p, 0.10, 0.28))),
        anchor="lm",
    )

    hy = 330
    ha = ease(seg(p, 0.14, 0.30))
    for s, x in [("business", 56), ("Hive", 620), ("hops", 830), ("why", 950)]:
        c.text(x, hy, s.upper(), "mono", 12, fade(INK3, ha), anchor="lm", tracking=1.8)
    c.line(56, hy + 18, W - 56, hy + 18, fade(INK, ha), 1.6)

    for i, (name, hive, hops, why, win) in enumerate(ROWS):
        a = ease(seg(p, 0.26 + i * 0.11, 0.46 + i * 0.11))
        if a <= 0.01:
            continue
        yy = hy + 70 + i * 74
        if win:
            c.rect(44, yy - 30, W - 88, 60, fill=fade((250, 240, 232), a))
        c.text(56, yy, name, "textb" if win else "text", 23, fade(INK, a), anchor="lm")
        c.text(620, yy, hive, "mono", 16, fade(INK2, a), anchor="lm")
        c.text(830, yy, hops, "mono", 16, fade(CLAY if win else INK2, a), anchor="lm")
        c.text(950, yy, why, "text", 18, fade(INK2, a), anchor="lm")
        if win:
            c.seal(W - 92, yy, 20, a)

    fa = ease(seg(p, 0.66, 0.84))
    c.line(56, 646, W - 56, 646, fade(LINE, fa), 1)
    c.text(
        56,
        690,
        "Placement cannot be bought — there is no slot to sell.",
        "text",
        21,
        fade(INK, fa),
        anchor="lm",
    )
    c.text(
        56,
        726,
        "The one left out is told why it was left out.",
        "italic",
        21,
        fade(CLAY, fa),
        anchor="lm",
    )


# ---------------------------------------------------------------- 7 · close
def s_close(c, t, dur):
    p = t / dur
    a = ease(seg(p, 0.04, 0.30))
    c.hexagon(W / 2, 330, 72, outline=fade(CLAY, a), width=4, open_corners=True)
    c.hexagon(W / 2, 330, 33, fill=fade(CLAY, a))
    c.text(
        W / 2,
        470,
        "The front door, signed.",
        "display",
        56,
        fade(INK, ease(seg(p, 0.18, 0.46))),
        anchor="mm",
    )
    a2 = ease(seg(p, 0.36, 0.62))
    c.text(
        W / 2,
        540,
        "On GitHub you find projects to work on.",
        "text",
        22,
        fade(INK2, a2),
        anchor="mm",
    )
    c.text(
        W / 2,
        574,
        "On Adobee Hive, agents find businesses and people to work with.",
        "text",
        22,
        fade(INK2, a2),
        anchor="mm",
    )
    a3 = ease(seg(p, 0.56, 0.80))
    c.line(W / 2 - 150, 626, W / 2 + 150, 626, fade(CLAY, a3), 2.5)
    c.text(
        W / 2,
        668,
        "Team B6  ·  BaselHack 2026",
        "mono",
        15,
        fade(INK3, a3),
        anchor="mm",
        tracking=1.6,
    )


RENDER = [s_title, s_card, s_many, s_radius, s_trust, s_rank, s_close]


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


def main() -> None:
    """Render the video, or stills for slides."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=int)
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--fps", type=int, default=FPS)
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))

    if a.preview:
        i = a.preview - 1
        acc = sum(d for _, d in SCENES[:i])
        for fr in (0.3, 0.65, 0.95):
            frame(acc + SCENES[i][1] * fr).save(
                os.path.join(here, f"prev-{a.preview}-{int(fr*100)}.png")
            )
        print("previews written")
        return
    if a.stills:
        for i, (nm, dur) in enumerate(SCENES):
            acc = sum(d for _, d in SCENES[:i])
            slug = nm.lower().replace(" ", "-").replace(",", "")
            out_dir = os.path.join(here, "..", "slides")
            os.makedirs(out_dir, exist_ok=True)
            frame(acc + dur * 0.93).save(
                os.path.join(out_dir, f"hive-{i+1}-{slug}.png")
            )
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
