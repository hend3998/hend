"""Render the 20s vertical motion-graphics ad (1080x1920, 30fps) as raw frames to stdout.

Usage: python3 render.py PRODUCT_PNG FONT_TTF | ffmpeg -f rawvideo -pix_fmt rgb24 -s 1080x1920 -r 30 -i - ...
Optional: python3 render.py PRODUCT_PNG FONT_TTF --still N OUT.png  (render one frame for review)
"""
import math
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H, FPS, N = 1080, 1920, 30, 600
TABLE = 1270
PRODUCT_PNG, FONT = sys.argv[1], sys.argv[2]

C = dict(
    cream=(255, 244, 223), mint=(191, 237, 227), butter=(255, 232, 170), blush=(255, 214, 226),
    skyl=(204, 228, 255), yellow=(255, 201, 60), teal=(19, 168, 158), pink=(255, 107, 154),
    blue=(77, 150, 255), dark=(30, 30, 47), card=(200, 155, 106), card_d=(140, 98, 58),
    card_l=(222, 184, 136), orange=(255, 122, 26), rivet=(255, 210, 63), wood=(236, 205, 160),
    wood_l=(246, 224, 190), white=(255, 255, 255), green=(96, 196, 112), green_d=(46, 120, 70),
    sky=(142, 197, 255), sand=(255, 226, 154), skin=(214, 160, 118), hair=(52, 34, 24),
    red=(196, 52, 62),
)


# ---------- helpers ----------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(f, a, b):
    return clamp((f - a) / float(b - a))


def eo(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def eio(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def back(t):
    t = clamp(t)
    c1 = 1.70158
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ss(w, h, fn, S=2):
    """Draw at S x and downsample: cheap antialiasing."""
    im = Image.new("RGBA", (int(w * S), int(h * S)), (0, 0, 0, 0))
    fn(ImageDraw.Draw(im), S, im)
    return im.resize((int(w), int(h)), Image.LANCZOS)


def with_alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return im


def paste(cv, spr, cx, cy, scale=1.0, rot=0.0, alpha=1.0, anchor="c"):
    if spr is None or alpha <= 0.01 or scale <= 0.01:
        return
    im = spr
    if abs(scale - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BICUBIC)
    if abs(rot) > 0.05:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    im = with_alpha(im, alpha)
    x = int(round(cx - im.width / 2))
    y = int(round(cy - im.height / 2)) if anchor == "c" else int(round(cy - im.height))
    cv.paste(im, (x, y), im)


def star_pts(cx, cy, R, r, n=4, rot=-90):
    pts = []
    for i in range(n * 2):
        a = math.radians(rot + i * 180 / n)
        rr = R if i % 2 == 0 else r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


_texcache = {}


def tex_factor(w, h):
    key = (w, h)
    if key not in _texcache:
        x = np.arange(w)
        stripes = 1 + 0.045 * (np.sin(x / 22.0 * 2 * math.pi) > 0.6)
        noise = np.random.RandomState(3).rand(h, w) * 0.08 - 0.04
        _texcache[key] = (stripes[None, :] + noise).astype(np.float32)
    return _texcache[key]


def apply_tex(im, strength=1.0):
    a = np.asarray(im).astype(np.float32)
    t = tex_factor(im.width, im.height)
    a[..., :3] *= (1 + (t[..., None] - 1) * strength)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def outline_mask(m, px):
    return ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(px * 2 + 1)))


def add_outline(im, col, px=4):
    edge = outline_mask(im.getchannel("A"), px)
    lay = Image.new("RGBA", im.size, col + (255,))
    lay.putalpha(edge)
    out = im.copy()
    out.alpha_composite(lay)
    return out


# ---------- text ----------
_fonts = {}


def font(sz):
    if sz not in _fonts:
        _fonts[sz] = ImageFont.truetype(FONT, sz, layout_engine=ImageFont.Layout.RAQM)
    return _fonts[sz]


def text_img(txt, sz, fill, stroke=0, stroke_fill=None):
    f = font(sz)
    bb = f.getbbox(txt, direction="rtl", stroke_width=stroke)
    im = Image.new("RGBA", (bb[2] - bb[0] + 8, bb[3] - bb[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - bb[0], 4 - bb[1]), txt, font=f, fill=fill, direction="rtl",
                            stroke_width=stroke, stroke_fill=stroke_fill)
    return im


def eyes_icon(sz):
    def fn(d, S, _):
        for x0 in (0, sz * 0.52):
            d.ellipse((x0 * S, 2 * S, (x0 + sz * 0.46) * S, sz * 0.92 * S), fill=C["white"], outline=C["dark"], width=int(5 * S))
            px = x0 + sz * 0.07
            d.ellipse((px * S, sz * 0.34 * S, (px + sz * 0.22) * S, sz * 0.6 * S), fill=C["dark"])
    return ss(sz, sz, fn)


def sparkle_icon(sz):
    def fn(d, S, _):
        d.polygon(star_pts(sz * 0.58 * S, sz * 0.55 * S, sz * 0.42 * S, sz * 0.11 * S), fill=C["yellow"], outline=C["dark"], width=int(4 * S))
        d.polygon(star_pts(sz * 0.17 * S, sz * 0.2 * S, sz * 0.16 * S, sz * 0.05 * S), fill=C["yellow"], outline=C["dark"], width=int(3 * S))
    return ss(sz, sz, fn)


def pill(parts, sz=92, bg=C["white"], shadow=C["teal"], icon=None, maxw=830):
    """parts: list of (text, color) laid out right-to-left. icon sits at the left (end of RTL line)."""
    while True:
        ims = [text_img(t, sz, c) for t, c in parts]
        gap = int(sz * 0.28)
        ic = icon(int(sz * 0.95)) if icon else None
        tw = sum(i.width for i in ims) + gap * (len(ims) - 1) + ((ic.width + gap) if ic else 0)
        if tw + 110 <= maxw or sz <= 48:
            break
        sz -= 4
    ph = int(sz * 1.6)
    pw = tw + 110
    im = ss(pw, ph + 16, lambda d, S, _: (
        d.rounded_rectangle((0, 14 * S, pw * S, (ph + 14) * S - 1), radius=ph * S // 2, fill=shadow),
        d.rounded_rectangle((0, 0, pw * S, ph * S), radius=ph * S // 2, fill=bg, outline=C["dark"], width=6 * S)))
    x = pw - 55
    boxes = []
    for t in ims:
        x -= t.width
        im.paste(t, (x, (ph - t.height) // 2), t)
        boxes.append((x, t))
        x -= gap
    if ic:
        im.paste(ic, (55, (ph - ic.height) // 2), ic)
    return im, boxes, ph


# ---------- sprites ----------
def mk_particles():
    out = []
    for c in (C["yellow"], C["teal"], C["pink"], C["blue"], C["orange"]):
        out.append(ss(60, 60, lambda d, S, _, c=c: d.polygon(star_pts(30 * S, 30 * S, 28 * S, 9 * S), fill=c)))
        out.append(ss(60, 60, lambda d, S, _, c=c: d.ellipse((14 * S, 14 * S, 46 * S, 46 * S), fill=c)))
        out.append(ss(60, 60, lambda d, S, _, c=c: d.polygon([(30 * S, 8 * S), (54 * S, 50 * S), (6 * S, 50 * S)], fill=c)))
    return out


PART = mk_particles()
STAR = ss(80, 80, lambda d, S, _: d.polygon(star_pts(40 * S, 40 * S, 38 * S, 10 * S), fill=C["yellow"], outline=C["white"], width=3 * S))


def burst(cv, cx, cy, t, seed, R=300, n=14, size=1.0):
    if t <= 0 or t >= 1:
        return
    rnd = random.Random(seed)
    for _ in range(n):
        ang = rnd.uniform(0, 2 * math.pi)
        dist = R * rnd.uniform(0.45, 1.0) * eo(t)
        sp = rnd.choice(PART)
        sc = size * rnd.uniform(0.55, 1.1) * (1 - t * 0.6)
        paste(cv, sp, cx + dist * math.cos(ang), cy + dist * math.sin(ang), scale=sc,
              rot=rnd.uniform(0, 90) + t * 160, alpha=1 - max(0, (t - 0.6) / 0.4))


def twinkles(cv, f, pts, seed=0):
    for i, (x, y, s) in enumerate(pts):
        k = 0.5 + 0.5 * math.sin(f * 0.25 + i * 1.7 + seed)
        paste(cv, STAR, x, y, scale=s * (0.4 + 0.6 * k), rot=f * 3 + i * 20, alpha=0.4 + 0.6 * k)


def shadow(w, a=80):
    h = max(8, int(w * 0.12))
    im = Image.new("RGBA", (int(w * 1.3), h * 3), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((w * 0.15, h, w * 1.15, h * 2), fill=(110, 70, 30, a))
    return im.filter(ImageFilter.GaussianBlur(h * 0.4))


def make_bg(b1, b2, seed):
    im = Image.new("RGB", (W, H), C["cream"])
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.ellipse((-300, 120, 520, 940), fill=b1 + (255,))
    d.ellipse((560, -160, 1400, 620), fill=b2 + (255,))
    d.ellipse((640, 760, 1320, 1360), fill=b1 + (170,))
    lay = lay.filter(ImageFilter.GaussianBlur(70))
    im.paste(lay, (0, 0), lay)
    rnd = random.Random(seed)
    dots = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    for _ in range(34):
        x, y, r = rnd.uniform(0, W * 2), rnd.uniform(0, TABLE * 2 - 60), rnd.uniform(5, 11)
        c = rnd.choice([C["yellow"], C["teal"], C["pink"], C["blue"]])
        dd.ellipse((x - r, y - r, x + r, y + r), fill=c + (95,))
    dots = dots.resize((W, H), Image.LANCZOS)
    im.paste(dots, (0, 0), dots)
    d = ImageDraw.Draw(im)
    d.rectangle((0, TABLE, W, H), fill=C["wood"])
    d.rectangle((0, TABLE, W, TABLE + 12), fill=C["wood_l"])
    for i in range(6):
        y = TABLE + 70 + i * 105
        d.line((0, y, W, y + 10), fill=(226, 190, 142), width=3)
    return im


BG = {
    "main": make_bg(C["mint"], C["butter"], 1),
    "sky": make_bg(C["skyl"], C["butter"], 2),
    "pink": make_bg(C["blush"], C["mint"], 3),
    "mint": make_bg(C["mint"], C["skyl"], 4),
}

# product cut-out (from the reference image) upscaled once
_prod = Image.open(PRODUCT_PNG).convert("RGBA")
PROD = _prod.resize((_prod.width * 2, _prod.height * 2), Image.LANCZOS)
_rgb = PROD.convert("RGB").filter(ImageFilter.UnsharpMask(2, 60, 2))
_rgb.putalpha(PROD.getchannel("A"))
PROD = _rgb
BTN = (361 / 430.0, 245 / 383.0)  # blue-ring button centre (relative)
_pc = {}


def product(width):
    width = int(round(width / 4.0) * 4)
    if width not in _pc:
        _pc[width] = PROD.resize((width, int(PROD.height * width / PROD.width)), Image.LANCZOS)
    return _pc[width]


GLOW = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
ImageDraw.Draw(GLOW).ellipse((40, 40, 160, 160), outline=(90, 190, 255, 255), width=16)
GLOW = GLOW.filter(ImageFilter.GaussianBlur(12))


def draw_product(cv, cx, bottom, width, glow=0.0):
    p = product(width)
    paste(cv, shadow(width * 0.95, 90), cx, bottom + 6)
    x, y = int(cx - p.width / 2), int(bottom - p.height)
    cv.paste(p, (x, y), p)
    if glow > 0:
        paste(cv, GLOW, x + BTN[0] * p.width, y + BTN[1] * p.height, scale=width / 430.0 * 0.62, alpha=glow)
    return x, y, p.width, p.height


# ---------- cartoon faces ----------
def draw_eyes(cv, cx, cy, size, openness=1.0, dx=0.0, dy=0.0, wink=0.0, gap=1.15):
    """Two cartoon eyes. openness <1 = sleepy lids. wink closes the left eye (0..1)."""
    w = int(size * 3.2)
    h = int(size * 1.9)
    S = 2

    def fn(d, S, _):
        for i, ex in enumerate((w / 2 - size * gap / 2 - size / 2, w / 2 + size * gap / 2 - size / 2)):
            op = openness * ((1 - wink) if i == 0 else 1.0)
            ey = h / 2
            eh = size * 1.18 * max(0.06, op)
            if op < 0.12:
                d.arc((ex * S, (ey - size * 0.35) * S, (ex + size) * S, (ey + size * 0.35) * S), 200, 340, fill=C["dark"], width=int(size * 0.12 * S))
                continue
            box = (ex * S, (ey - eh / 2) * S, (ex + size) * S, (ey + eh / 2) * S)
            d.ellipse(box, fill=C["white"], outline=C["dark"], width=int(size * 0.09 * S))
            pr = size * 0.24
            px = ex + size / 2 + dx * size * 0.22
            py = ey + dy * size * 0.25 * min(1, op)
            py = max(ey - eh / 2 + pr, min(ey + eh / 2 - pr, py))
            d.ellipse(((px - pr) * S, (py - pr) * S, (px + pr) * S, (py + pr) * S), fill=C["dark"])
            d.ellipse(((px - pr * 0.15) * S, (py - pr * 0.75) * S, (px + pr * 0.3) * S, (py - pr * 0.3) * S), fill=C["white"])
            if op < 0.98:  # sleepy lid line
                d.line((ex * S, (ey - eh / 2) * S + 2, (ex + size) * S, (ey - eh / 2) * S + 2), fill=C["dark"], width=int(size * 0.1 * S))
    paste(cv, ss(w, h, fn), cx, cy)


def draw_mouth(cv, cx, cy, size, kind):
    def fn(d, S, _):
        w, h = size * 2, size * 1.4
        if kind == "flat":
            d.line((w * 0.25 * S, h * 0.45 * S, w * 0.75 * S, h * 0.5 * S), fill=C["dark"], width=int(size * 0.14 * S))
        elif kind == "smile":
            d.arc((w * 0.2 * S, -h * 0.2 * S, w * 0.8 * S, h * 0.7 * S), 20, 160, fill=C["dark"], width=int(size * 0.14 * S))
        else:  # open happy
            d.chord((w * 0.18 * S, -h * 0.25 * S, w * 0.82 * S, h * 0.95 * S), 0, 180, fill=C["red"], outline=C["dark"], width=int(size * 0.1 * S))
            d.chord((w * 0.36 * S, h * 0.45 * S, w * 0.64 * S, h * 0.95 * S), 180, 360, fill=(255, 140, 150))
    paste(cv, ss(size * 2, size * 1.4, fn), cx, cy)


# ---------- cardboard models ----------
def dino_mask_draw(d, k, fill=255):
    E = lambda b: d.ellipse([v * k for v in b], fill=fill)
    P = lambda pts: d.polygon([(x * k, y * k) for x, y in pts], fill=fill)
    E((300, 200, 780, 520))
    P([(720, 300), (990, 345), (730, 450)])
    E((170, 110, 400, 370))
    for a in range(195, 350, 26):
        r = math.radians(a)
        cx, cy = 285 + 118 * math.cos(r), 240 + 132 * math.sin(r)
        tx, ty = 285 + 165 * math.cos(r), 240 + 180 * math.sin(r)
        P([(cx - 26 * math.sin(r), cy + 26 * math.cos(r)), (tx, ty), (cx + 26 * math.sin(r), cy - 26 * math.cos(r))])
    P([(15, 378), (60, 322), (130, 272), (260, 252), (330, 330), (300, 440), (150, 452), (60, 418)])
    P([(150, 272), (178, 262), (100, 150)])
    P([(232, 256), (258, 256), (196, 126)])
    P([(70, 324), (96, 312), (44, 252)])
    for b in ((340, 440, 420, 640), (440, 460, 520, 640), (600, 450, 680, 640), (700, 430, 770, 630)):
        d.rounded_rectangle([v * k for v in b], radius=30 * k, fill=fill)


def dino_mask(k):
    S = 2
    m = Image.new("L", (int(1000 * k * S), int(700 * k * S)), 0)
    dino_mask_draw(ImageDraw.Draw(m), k * S)
    return m.resize((int(1000 * k), int(700 * k)), Image.LANCZOS)


def dino_plain(k):
    m = dino_mask(k)
    im = Image.new("RGBA", m.size, C["card"] + (255,))
    im.putalpha(m)
    return add_outline(apply_tex(im), C["card_d"], max(2, int(6 * k)))


def rivet_spr(r):
    return ss(r * 2, r * 2, lambda d, S, _: (
        d.ellipse((0, 0, 2 * r * S - 1, 2 * r * S - 1), fill=C["rivet"], outline=(200, 150, 20), width=2 * S),
        d.ellipse((r * 0.6 * S, r * 0.6 * S, r * 1.4 * S, r * 1.4 * S), fill=(230, 170, 30))))


def connector_spr(s):
    def fn(d, S, _):
        t = s * 0.32
        d.polygon([(0, 0), (t * S, 0), (t * S, (s - t) * S), (s * S, (s - t) * S), (s * S, s * S), (0, s * S)], fill=C["orange"], outline=(190, 80, 10), width=2 * S)
        for (x, y) in ((t / 2, s * 0.3), (s * 0.7, s - t / 2)):
            d.ellipse(((x - t * 0.22) * S, (y - t * 0.22) * S, (x + t * 0.22) * S, (y + t * 0.22) * S), fill=(150, 60, 10))
    return ss(s, s, fn)


def dino_colored(k):
    S = 2
    w, h = int(1000 * k), int(700 * k)
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    s = k * S
    dino_mask_draw(d, s, fill=C["green"] + (255,))
    d.ellipse([v * s for v in (170, 110, 400, 370)], fill=C["yellow"])
    d.ellipse([v * s for v in (205, 150, 365, 330)], fill=C["orange"])
    d.polygon([(x * s, y * s) for x, y in [(15, 378), (60, 322), (130, 272), (260, 252), (330, 330), (300, 440), (150, 452), (60, 418)]], fill=(120, 210, 130))
    for pts in ([(150, 272), (178, 262), (100, 150)], [(232, 256), (258, 256), (196, 126)], [(70, 324), (96, 312), (44, 252)]):
        d.polygon([(x * s, y * s) for x, y in pts], fill=(255, 248, 225))
    for (x, y, r) in ((470, 300, 34), (580, 270, 26), (650, 360, 30), (520, 400, 22), (400, 350, 20)):
        d.ellipse(((x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s), fill=(70, 160, 90))
    im = im.resize((w, h), Image.LANCZOS)
    im = add_outline(apply_tex(im, 0.8), C["green_d"], max(2, int(6 * k)))
    rv = rivet_spr(max(5, int(16 * k)))
    for (x, y) in ((380, 470), (480, 488), (640, 478), (735, 460)):
        im.paste(rv, (int(x * k - rv.width / 2), int(y * k - rv.height / 2)), rv)
    cn = connector_spr(max(10, int(56 * k)))
    im.paste(cn, (int(700 * k), int(330 * k)), cn)
    return im


DINO_EYE = (205, 318)  # in 1000x700 dino units


def rocket(k, colored=True):
    S = 2
    w, h = int(400 * k), int(760 * k)

    def fn(d, S, _):
        s = k * S
        P = lambda pts, c: d.polygon([(x * s, y * s) for x, y in pts], fill=c, outline=C["card_d"], width=int(5 * s))
        fin = C["yellow"] if colored else C["card"]
        P([(125, 470), (28, 630), (28, 720), (130, 660)], fin)
        P([(275, 470), (372, 630), (372, 720), (270, 660)], fin)
        d.rectangle((140 * s, 680 * s, 260 * s, 735 * s), fill=(120, 120, 135) if colored else C["card_d"], outline=C["card_d"], width=int(5 * s))
        d.rounded_rectangle((110 * s, 190 * s, 290 * s, 695 * s), radius=50 * s, fill=C["blue"] if colored else C["card"], outline=C["card_d"], width=int(5 * s))
        P([(112, 225), (200, 28), (288, 225)], C["pink"] if colored else C["card_l"])
        if colored:
            for y in (520, 585):
                d.rectangle((113 * s, y * s, 287 * s, (y + 30) * s), fill=C["white"])
        d.ellipse((145 * s, 300 * s, 255 * s, 410 * s), fill=(200, 240, 255) if colored else C["card_l"], outline=C["card_d"], width=int(6 * s))
    im = apply_tex(ss(w, h, fn), 0.8)
    cn = connector_spr(max(10, int(60 * k)))
    im.paste(cn, (int(118 * k), int(560 * k)), cn)
    cn2 = cn.transpose(Image.FLIP_LEFT_RIGHT)
    im.paste(cn2, (int(282 * k - cn2.width), int(560 * k)), cn2)
    rv = rivet_spr(max(5, int(15 * k)))
    for x in (160, 240):
        im.paste(rv, (int(x * k - rv.width / 2), int(470 * k - rv.height / 2)), rv)
    return im


def castle(k):
    w, h = int(600 * k), int(620 * k)

    def fn(d, S, _):
        s = k * S
        o = dict(outline=C["card_d"], width=int(5 * s))
        Y = 60
        R = lambda b, c: d.rectangle([b[0] * s, (b[1] + Y) * s, b[2] * s, (b[3] + Y) * s], fill=c, **o)
        P = lambda pts, c: d.polygon([(x * s, (y + Y) * s) for x, y in pts], fill=c, **o)
        R((130, 250, 470, 540), C["sand"])
        for x in range(130, 470, 62):
            R((x, 212, x + 34, 252), C["sand"])
        R((40, 170, 170, 540), C["sky"])
        R((430, 170, 560, 540), C["sky"])
        P([(25, 182), (105, 30), (185, 182)], C["pink"])
        P([(415, 182), (495, 30), (575, 182)], C["pink"])
        d.rounded_rectangle((250 * s, (400 + Y) * s, 350 * s, (545 + Y) * s), radius=50 * s, fill=(160, 90, 50), **o)
        for b in ((85, 260, 125, 320), (475, 260, 515, 320), (280, 300, 320, 352)):
            d.rounded_rectangle([b[0] * s, (b[1] + Y) * s, b[2] * s, (b[3] + Y) * s], radius=18 * s, fill=C["dark"])
        d.line((495 * s, (30 + Y) * s, 495 * s, (-50 + Y) * s), fill=C["card_d"], width=int(6 * s))
    im = apply_tex(ss(w, h, fn), 0.8)
    rv = rivet_spr(max(5, int(15 * k)))
    for (x, y) in ((150, 330), (450, 330), (150, 560), (450, 560)):
        im.paste(rv, (int(x * k - rv.width / 2), int(y * k - rv.height / 2)), rv)
    return im


def flag(cv, x, y, k, f):
    pts = []
    for i in range(9):
        u = i / 8.0
        pts.append((x + u * 90 * k, y + math.sin(f * 0.5 + u * 4) * 10 * k * u))
    for i in range(8, -1, -1):
        u = i / 8.0
        pts.append((x + u * 90 * k, y + 55 * k * (1 - u) * 0.9 + 6 * k + math.sin(f * 0.5 + u * 4) * 10 * k * u))
    ImageDraw.Draw(cv).polygon(pts, fill=C["teal"])


def marker_spr(col):
    def fn(d, S, _):
        d.rounded_rectangle((10 * S, 40 * S, 50 * S, 230 * S), radius=10 * S, fill=col, outline=C["dark"], width=3 * S)
        d.rounded_rectangle((10 * S, 0, 50 * S, 70 * S), radius=10 * S, fill=C["white"], outline=C["dark"], width=3 * S)
        d.polygon([(18 * S, 230 * S), (42 * S, 230 * S), (30 * S, 262 * S)], fill=col, outline=C["dark"], width=3 * S)
    return ss(60, 266, fn)


def card_char(w, h):
    def fn(d, S, _):
        d.rounded_rectangle((0, 14 * S, w * S, h * S), radius=26 * S, fill=C["card"], outline=C["card_d"], width=6 * S)
        for i in range(int(w / 26)):  # corrugated top edge
            x = (13 + i * 26) * S
            d.ellipse((x - 13 * S, 2 * S, x + 13 * S, 28 * S), fill=C["card_l"], outline=C["card_d"], width=3 * S)
    return apply_tex(ss(w, h, fn), 1.0)


def child_body():
    w, h = 760, 1000

    def fn(d, S, _):
        s = S
        d.rounded_rectangle((150 * s, 470 * s, 610 * s, 1100 * s), radius=150 * s, fill=C["teal"])
        d.chord((300 * s, 430 * s, 460 * s, 540 * s), 0, 180, fill=C["white"])
        d.rectangle((345 * s, 400 * s, 415 * s, 480 * s), fill=C["skin"])
        d.ellipse((190 * s, -10 * s, 570 * s, 330 * s), fill=C["hair"])
        d.ellipse((182 * s, 160 * s, 238 * s, 250 * s), fill=C["skin"])
        d.ellipse((522 * s, 160 * s, 578 * s, 250 * s), fill=C["skin"])
        d.ellipse((215 * s, 50 * s, 545 * s, 420 * s), fill=C["skin"])
        d.chord((215 * s, 20 * s, 545 * s, 230 * s), 180, 360, fill=C["hair"])
        for x in (300, 460):
            d.arc(((x - 34) * s, 180 * s, (x + 34) * s, 240 * s), 200, 340, fill=C["dark"], width=10 * s)
            d.ellipse(((x - 40) * s, 250 * s, (x + 10) * s, 285 * s), fill=(240, 130, 130, 120))
        d.chord((318 * s, 240 * s, 442 * s, 360 * s), 0, 180, fill=C["red"], outline=C["dark"], width=6 * s)
    return ss(w, h, fn)


CHILD = child_body()
HAND = ss(96, 96, lambda d, S, _: d.ellipse((0, 0, 96 * S - 1, 96 * S - 1), fill=C["skin"], outline=(170, 115, 80), width=4 * S))
SLEEVE = C["teal"]

# pre-built models
DINO_PLAIN = dino_plain(0.62)
DINO_C = {k: dino_colored(k) for k in (0.78, 0.56, 0.3)}
ROCKET_C = {k: rocket(k) for k in (0.62, 0.45)}
ROCKET_P = rocket(0.62, colored=False)
CASTLE = {k: castle(k) for k in (0.92, 0.45)}
CONN = connector_spr(70)
RIV = rivet_spr(18)
MARK = [marker_spr(c) for c in (C["pink"], C["blue"], C["green"])]
CHAR = card_char(330, 420)

# sheet with dashed dino outline for the cutting scene
SHEET_W, SHEET_H = 800, 600
_dm = Image.new("L", (SHEET_W, SHEET_H), 0)
_dm.paste(dino_mask(0.62), (90, 70))
DM_SHEET = _dm
_edge = outline_mask(_dm, 3)
_yy, _xx = np.mgrid[0:SHEET_H, 0:SHEET_W]
_dash = ((((_xx + _yy) // 14) % 2) == 0).astype(np.uint8) * 255
DASH = Image.fromarray((np.asarray(_edge).astype(np.uint16) * _dash // 255).astype(np.uint8))
CUT = _edge.filter(ImageFilter.MaxFilter(3))
_c = np.array(_dm).nonzero()
DCX, DCY = float(_c[1].mean()), float(_c[0].mean())


def sheet_img(cut_t, hole):
    im = Image.new("RGBA", (SHEET_W, SHEET_H), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, SHEET_W - 1, SHEET_H - 1), radius=18, fill=C["card"] + (255,), outline=C["card_d"] + (255,), width=6)
    im = apply_tex(im)
    dl = Image.new("RGBA", im.size, C["dark"] + (255,))
    dl.putalpha(DASH)
    im.alpha_composite(dl)
    if cut_t > 0:
        wedge = Image.new("L", im.size, 0)
        ImageDraw.Draw(wedge).pieslice((DCX - 900, DCY - 900, DCX + 900, DCY + 900), -90, -90 + 360 * cut_t, fill=255)
        cl = Image.new("RGBA", im.size, (90, 55, 25, 255))
        cl.putalpha(ImageChops.multiply(CUT, wedge))
        im.alpha_composite(cl)
    if hole:
        hl = Image.new("RGBA", im.size, (120, 80, 40, 255))
        hl.putalpha(DM_SHEET)
        im.alpha_composite(hl)
    return im


# ---------- scenes ----------
TEXT_CACHE = {}


def get_pill(key, *a, **kw):
    if key not in TEXT_CACHE:
        TEXT_CACHE[key] = pill(*a, **kw)
    return TEXT_CACHE[key]


def show_pill(cv, key, f, f_in, f_out, y, *a, **kw):
    if f < f_in or f >= f_out:
        return
    im = get_pill(key, *a, **kw)[0]
    t = prog(f, f_in, f_in + 7)
    out = prog(f, f_out - 4, f_out)
    paste(cv, im, W / 2 - 20, y, scale=back(t) * (1 - 0.15 * out), alpha=min(1, t * 2) * (1 - out))


def scene1(cv, f):
    # bored cardboard looks at the product, then gets excited
    draw_product(cv, 790, TABLE, 470, glow=0.5 + 0.3 * math.sin(f * 0.3))
    excited = prog(f, 54, 60)
    hop = math.sin(prog(f, 57, 75) * math.pi) * 70
    sway = math.sin(f * 0.12) * 3 * (1 - excited)
    cx, base = 285, TABLE - hop
    paste(cv, shadow(330 * (1 - hop / 300), 80), cx, TABLE + 6)
    paste(cv, CHAR, cx, base, rot=sway, anchor="b")
    # arms
    d = ImageDraw.Draw(cv)
    lift = eo(prog(f, 56, 64))
    for side in (-1, 1):
        sx, sy = cx + side * 165, base - 190
        ex, ey = sx + side * 70, sy + 80 - lift * 190
        d.line((sx, sy, ex, ey), fill=C["card_d"], width=12)
        d.ellipse((ex - 18, ey - 18, ex + 18, ey + 18), fill=C["card_l"], outline=C["card_d"], width=4)
    look = eio(prog(f, 44, 52))
    blink = 0.1 if 24 <= f <= 27 else 1.0
    openness = (0.5 + 0.65 * back(excited)) * blink
    draw_eyes(cv, cx + sway * 2, base - 285, 86, openness=openness, dx=0.9 * look, dy=0.5 * (1 - look) - 0.3 * excited)
    draw_mouth(cv, cx + sway * 2, base - 170, 54, "open" if excited > 0.5 else "flat")
    burst(cv, cx, base - 230, prog(f, 57, 80), 11, R=260)
    show_pill(cv, "s1", f, 9, 86, 430, [("مجرد كرتون؟", C["dark"])], icon=eyes_icon, shadow=C["yellow"])


def scene2a(cv, f):
    t = prog(f, 90, 162)
    width = 760 * (1 + 0.06 * eio(t))
    on = eo(prog(f, 100, 110))
    glow = (0.35 + 0.65 * on) * (0.8 + 0.2 * math.sin(f * 0.6))
    draw_product(cv, 540, TABLE, width, glow=glow)
    burst(cv, 540 + (BTN[0] - 0.5) * width, TABLE - width * 383 / 430 * (1 - BTN[1]), prog(f, 102, 122), 21, R=170, n=10, size=0.7)


def scene2b(cv, f):
    cut = eio(prog(f, 163, 194))
    lift = eo(prog(f, 194, 206))
    sx, sy = 540, 960
    sh = sheet_img(cut, lift > 0)
    paste(cv, shadow(SHEET_W * 0.95, 70), sx, sy + SHEET_H / 2 + 8)
    paste(cv, sh, sx, sy)
    if lift > 0:
        ox, oy = sx - SHEET_W / 2 + 90, sy - SHEET_H / 2 + 70
        piece = DINO_PLAIN
        pcx, pcy = ox + piece.width / 2, oy + piece.height / 2
        paste(cv, shadow(piece.width * 0.8, int(60 * lift)), pcx, pcy + piece.height / 2 + 30 * lift)
        paste(cv, piece, pcx, pcy - 70 * lift, scale=1 + 0.08 * lift, rot=-4 * lift)
        if f >= 198:
            draw_eyes(cv, pcx - piece.width / 2 + DINO_EYE[0] * 0.62 * 1.08 + 10, pcy - 70 - piece.height / 2 + DINO_EYE[1] * 0.62 * 1.08 - 10,
                      34, openness=back(prog(f, 198, 204)), dx=-0.5)
    burst(cv, sx, sy - 40, prog(f, 194, 212), 31, R=380, n=18)


def scene2_text(cv, f):
    if f < 96 or f >= 209:
        return
    key = "s2"
    im, boxes, ph = get_pill(key, [("قصّ…", C["dark"]), ("وشكّل…", C["dark"]), ("وابتكر!", C["teal"])], sz=88, shadow=C["pink"])
    # pill frame, then each word pops in turn
    frame = Image.new("RGBA", im.size, (0, 0, 0, 0))
    base = ss(im.width, im.height, lambda d, S, _: (
        d.rounded_rectangle((0, 14 * S, im.width * S, (ph + 14) * S - 1), radius=ph * S // 2, fill=C["pink"]),
        d.rounded_rectangle((0, 0, im.width * S, ph * S), radius=ph * S // 2, fill=C["white"], outline=C["dark"], width=6 * S)))
    frame.alpha_composite(base)
    for (x, t), fin in zip(boxes, (99, 138, 174)):
        if f >= fin:
            k = back(prog(f, fin, fin + 6))
            tt = t.resize((max(1, int(t.width * k)), max(1, int(t.height * k))), Image.BICUBIC)
            frame.paste(tt, (int(x + t.width / 2 - tt.width / 2), int((ph - tt.height) / 2)), tt)
    a = back(prog(f, 96, 102))
    out = prog(f, 204, 209)
    paste(cv, frame, W / 2, 380, scale=a * (1 - 0.15 * out), alpha=1 - out)


def scene3(cv, f):
    if f < 234:  # flat lay of pieces, connectors, rivets, markers
        items = [
            ("rect", 300, 900, 0), ("tri", 760, 870, 2), ("circ", 520, 1120, 4),
            ("conn", 260, 1150, 1), ("conn", 820, 1130, 3), ("riv", 640, 940, 2), ("riv", 690, 980, 3),
            ("riv", 420, 960, 4), ("mark0", 860, 1110, 5), ("mark1", 930, 1060, 6), ("mark2", 200, 1050, 5),
        ]
        d = ImageDraw.Draw(cv)
        for kind, x, y, dl in items:
            s = back(prog(f, 210 + dl, 216 + dl))
            if s <= 0:
                continue
            if kind == "rect":
                spr = TEXT_CACHE.setdefault("rect", add_outline(apply_tex(Image.new("RGBA", (300, 190), C["card"] + (255,))), C["card_d"], 5))
                paste(cv, spr, x, y, scale=s, rot=8)
            elif kind == "tri":
                spr = TEXT_CACHE.setdefault("tri", apply_tex(ss(240, 210, lambda dd, S, _: dd.polygon([(120 * S, 0), (240 * S, 210 * S - 1), (0, 210 * S - 1)], fill=C["card"], outline=C["card_d"], width=5 * S))))
                paste(cv, spr, x, y, scale=s, rot=-10)
            elif kind == "circ":
                spr = TEXT_CACHE.setdefault("circ", apply_tex(ss(180, 180, lambda dd, S, _: dd.ellipse((0, 0, 180 * S - 1, 180 * S - 1), fill=C["card"], outline=C["card_d"], width=5 * S))))
                paste(cv, spr, x, y, scale=s)
            elif kind == "conn":
                paste(cv, CONN, x, y, scale=s * 1.2, rot=x % 50)
            elif kind == "riv":
                paste(cv, RIV, x, y, scale=s * 1.4)
            else:
                paste(cv, MARK[int(kind[-1])], x, y, scale=s * 0.9, rot=60 + x % 30)
        return
    if f < 264:  # assembly: two panels meet, connector + rivets pop in
        t = eio(prog(f, 234, 246))
        base = TEXT_CACHE.setdefault("panA", add_outline(apply_tex(Image.new("RGBA", (420, 70), C["card"] + (255,))), C["card_d"], 5))
        wall = TEXT_CACHE.setdefault("panB", add_outline(apply_tex(Image.new("RGBA", (70, 380), C["card"] + (255,))), C["card_d"], 5))
        paste(cv, shadow(440, 70), 560, TABLE + 4)
        paste(cv, base, 560, TABLE, anchor="b")
        paste(cv, wall, 385 + (1 - t) * 260, TABLE - 70 - (1 - t) * 160, anchor="b", rot=(1 - t) * -25)
        c = back(prog(f, 246, 252))
        paste(cv, CONN, 455, TABLE - 140, scale=c * 1.5)
        for i, fx in enumerate((251, 256)):
            paste(cv, RIV, 440 + i * 50, TABLE - 105 - i * 25, scale=back(prog(f, fx, fx + 4)) * 1.3)
        burst(cv, 450, TABLE - 140, prog(f, 246, 262), 41, R=200, n=10, size=0.7)
        return
    if f < 288:  # colouring: colour reveals from bottom to top behind the marker
        t = eio(prog(f, 265, 286))
        cx, bottom = 540, TABLE
        plain, col = ROCKET_P, ROCKET_C[0.62]
        paste(cv, shadow(plain.width * 0.9, 80), cx, bottom + 4)
        x0, y0 = int(cx - plain.width / 2), int(bottom - plain.height)
        cv.paste(plain, (x0, y0), plain)
        cut = int(plain.height * (1 - t))
        part = col.crop((0, cut, col.width, col.height))
        cv.paste(part, (x0, y0 + cut), part)
        mx = cx + math.sin(f * 1.3) * plain.width * 0.25
        paste(cv, MARK[0], mx + 40, y0 + cut - 90, rot=35)
        return
    k = (f - 288) // 24
    lf = (f - 288) % 24
    labels = [("rk", "صاروخ؟", C["blue"]), ("cs", "قلعة؟", C["pink"]), ("dn", "أو ديناصور؟", C["green_d"])]
    key, label, colr = labels[k]
    show_pill(cv, key, lf, 1, 25, 420, [(label, colr)], sz=96, shadow=colr)
    t = back(prog(lf, 0, 6))
    burst(cv, 540, 900, prog(lf, 0, 20), 51 + k, R=420, n=18)
    if k == 0:
        r = ROCKET_C[0.62]
        hop = math.sin(prog(lf, 4, 18) * math.pi) * 90
        paste(cv, shadow(r.width, 80), 540, TABLE + 4)
        for i in range(4):
            pt = prog(lf, 4 + i * 2, 20)
            if 0 < pt < 1:
                rr = 26 + 30 * pt
                xx = 540 + (i - 1.5) * 50
                ImageDraw.Draw(cv).ellipse((xx - rr, TABLE - 10 - rr - pt * 40, xx + rr, TABLE - 10 + rr - pt * 40), fill=(255, 255, 255))
        paste(cv, r, 540, TABLE - hop, scale=t, rot=math.sin(lf * 0.9) * 4, anchor="b")
        if t > 0.9:
            draw_eyes(cv, 540, TABLE - hop - r.height * 0.55, 42, dx=0.2)
    elif k == 1:
        c = CASTLE[0.92]
        paste(cv, shadow(c.width, 80), 540, TABLE + 4)
        paste(cv, c, 540, TABLE, scale=t, anchor="b")
        if t > 0.9:
            x0, y0 = 540 - c.width / 2, TABLE - c.height
            flag(cv, x0 + 497 * 0.92, y0 + 12 * 0.92, 0.92, f)
            draw_eyes(cv, 540, y0 + 0.62 * c.height, 40, openness=1, dx=math.sin(lf * 0.4))
            draw_mouth(cv, 540, y0 + 0.86 * c.height, 46, "open" if (lf // 4) % 2 else "smile")
    else:
        dk = 0.78
        dn = DINO_C[dk]
        wag = math.sin(lf * 0.8) * 4
        paste(cv, shadow(dn.width * 0.8, 80), 540, TABLE + 4)
        paste(cv, dn, 540, TABLE, scale=t, rot=wag, anchor="b")
        if t > 0.9:
            x0, y0 = 540 - dn.width / 2, TABLE - dn.height
            draw_eyes(cv, x0 + DINO_EYE[0] * dk + 12, y0 + DINO_EYE[1] * dk - 16, 44, dx=-0.6)
            for i in range(3):
                nt = prog(lf, 6 + i * 3, 22)
                if 0 < nt < 1:
                    nx, ny = x0 + 40 - nt * 60 - i * 30, y0 + 120 - nt * 220 - i * 30
                    dd = ImageDraw.Draw(cv)
                    dd.ellipse((nx - 18, ny - 12, nx + 18, ny + 12), fill=C["dark"])
                    dd.line((nx + 16, ny, nx + 16, ny - 70), fill=C["dark"], width=7)
                    dd.line((nx + 16, ny - 70, nx + 40, ny - 50), fill=C["dark"], width=7)


def scene4(cv, f):
    lf = f - 360
    rnd = random.Random(7)
    for i in range(26):  # gentle confetti rain
        x = rnd.uniform(40, W - 40)
        y = (rnd.uniform(0, 1400) + lf * rnd.uniform(5, 9)) % 1500 - 100
        paste(cv, PART[i % len(PART)], x, y, scale=0.5, rot=lf * 6 + i * 30, alpha=0.8)
    bob = math.sin(lf * 0.22) * 10
    paste(cv, CHILD, 540, 700 + bob + CHILD.height / 2)
    dk = 0.56
    dn = DINO_C[dk]
    lift = math.sin(lf * 0.22 + 0.6) * 14
    dcx, dcy = 540, 1245 + bob + lift
    paste(cv, dn, dcx, dcy, scale=back(prog(lf, 0, 8)))
    d = ImageDraw.Draw(cv)
    for side in (-1, 1):
        hx, hy = dcx + side * (dn.width / 2 - 20), dcy + 70
        d.line((540 + side * 210, 1230 + bob, hx, hy), fill=SLEEVE, width=78)
        paste(cv, HAND, hx, hy)
    x0, y0 = dcx - dn.width / 2, dcy - dn.height / 2
    wink = math.sin(prog(lf, 58, 70) * math.pi)
    draw_eyes(cv, x0 + DINO_EYE[0] * dk + 10, y0 + DINO_EYE[1] * dk - 14, 36, dx=0.3, dy=-0.9, wink=wink)
    burst(cv, x0 + DINO_EYE[0] * dk - 20, y0 + DINO_EYE[1] * dk - 40, prog(lf, 62, 80), 61, R=120, n=8, size=0.6)
    show_pill(cv, "s4", f, 372, 474, 400, [("من فكرة… إلى إبداع", C["dark"])], sz=86, icon=sparkle_icon, shadow=C["teal"])


# S5 layout (shared by 5a and the static end card)
P_W, P_X = 600, 540
CAS_K, ROC_K, DIN_K = 0.45, 0.45, 0.3


def scene5_models(cv, f, settle):
    s = lambda d: back(prog(f, 482 + d, 490 + d)) if not settle else 1.0
    cs = CASTLE[CAS_K]
    paste(cv, cs, 195, 960, scale=s(0), anchor="b")
    rk = ROCKET_C[ROC_K]
    paste(cv, rk, 900, 980, scale=s(3), anchor="b")


def scene5(cv, f):
    settle = f >= 540
    t = 1.0 if settle else eo(prog(f, 480, 528))
    scene5_models(cv, f, settle)
    draw_product(cv, P_X, TABLE, P_W * (0.94 + 0.06 * t), glow=0.75)
    dn = DINO_C[DIN_K]
    s = 1.0 if settle else back(prog(f, 488, 496))
    paste(cv, shadow(dn.width * 0.8, 70), 912, TABLE + 34)
    paste(cv, dn, 912, TABLE + 30, scale=s, anchor="b")
    if not settle:
        twinkles(cv, f, [(120, 640, 0.6), (980, 600, 0.5), (90, 1180, 0.45), (1000, 1240, 0.5), (300, 700, 0.35)])
        show_pill(cv, "s5", f, 483, 538, 430, [("جاهزين تبدعون؟", C["dark"])], sz=96, shadow=C["yellow"])
        return
    # static end card (no motion after the first 4 frames)
    a = prog(f, 540, 544)
    if "brand" not in TEXT_CACHE:
        TEXT_CACHE["brand"] = text_img("ابتكار", 170, C["teal"], stroke=10, stroke_fill=C["white"])
        TEXT_CACHE["sub"] = text_img("جهاز قص الكرتون للأطفال", 62, C["dark"])
    paste(cv, TEXT_CACHE["brand"], W / 2 - 20, 330, alpha=a)
    paste(cv, TEXT_CACHE["sub"], W / 2 - 20, 475, alpha=a)
    cta = get_pill("cta", [("اطلبوه من ابتكار", C["white"])], sz=76, bg=C["pink"], shadow=C["dark"])[0]
    paste(cv, cta, W / 2 - 20, 1390, alpha=a)


# ---------- transitions ----------
def wipe(cv, f, at, seed):
    d = f - at
    if not -5 <= d < 5:
        return
    k = 1 - abs(d + 0.5) / 5.0
    cols = [C["teal"], C["yellow"], C["pink"]]
    rnd = random.Random(seed)
    cols = cols[seed % 3:] + cols[:seed % 3]
    dr = ImageDraw.Draw(cv)
    cx, cy = rnd.uniform(300, 780), rnd.uniform(700, 1200)
    for i, c in enumerate(cols):
        r = max(0.0, eio(k) * 1500 - i * 260)
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c)


def punch(cv, f, cuts):
    for c in cuts:
        if 0 <= f - c < 5:
            s = 1 + 0.07 * (1 - (f - c) / 5.0)
            big = cv.resize((int(W * s), int(H * s)), Image.BILINEAR)
            x, y = (big.width - W) // 2, (big.height - H) // 2
            return big.crop((x, y, x + W, y + H))
    return cv


def render(f):
    if f < 90:
        bgk = "main"
    elif f < 210:
        bgk = "main"
    elif f < 360:
        bgk = ["main", "main", "main", "sky", "pink", "mint"][min(5, (f - 210) // 24 if f < 288 else 3 + (f - 288) // 24)]
        if f < 288:
            bgk = "main"
    elif f < 480:
        bgk = "pink"
    else:
        bgk = "main"
    cv = BG[bgk].copy()
    if f < 90:
        scene1(cv, f)
    elif f < 162:
        scene2a(cv, f)
        scene2_text(cv, f)
    elif f < 210:
        scene2b(cv, f)
        scene2_text(cv, f)
    elif f < 360:
        scene3(cv, f)
    elif f < 480:
        scene4(cv, f)
    else:
        scene5(cv, f)
    cv = punch(cv, f, [234, 264, 288, 312, 336, 162])
    for at, sd in ((90, 0), (210, 1), (360, 2), (480, 0)):
        wipe(cv, f, at, sd)
    return cv


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "--still":
        for n in sys.argv[4].split(","):
            render(int(n)).save(sys.argv[5].replace("%d", n))
    else:
        out = sys.stdout.buffer
        for fr in range(N):
            out.write(render(fr).tobytes())
            if fr % 60 == 0:
                print("frame", fr, file=sys.stderr, flush=True)
