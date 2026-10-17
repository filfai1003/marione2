"""Turn the Meshy images into the site's assets: transparent icons, card backs and 92 card faces."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy import ndimage

RAW = "raw"; OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
os.makedirs(f"{OUT}/icons", exist_ok=True); os.makedirs(f"{OUT}/cards/fr", exist_ok=True); os.makedirs(f"{OUT}/cards/it", exist_ok=True)
INK = (36, 31, 20, 255); CREAM = (255, 250, 238, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
W, H, R = 240, 360, 18

def load(name):
    return Image.open(f"{RAW}/{name}.png").convert("RGBA")

def cutout(im, thresh=232):
    """White background connected to the border becomes transparent (soft edge)."""
    a = np.asarray(im).astype(np.int16)
    white = (a[..., 0] > thresh) & (a[..., 1] > thresh) & (a[..., 2] > thresh)
    lab, _ = ndimage.label(white)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = np.isin(lab, list(border))
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    alpha_img = Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(1.2))
    out = im.copy(); out.putalpha(alpha_img)
    bbox = Image.fromarray(alpha).getbbox()
    return out.crop(bbox) if bbox else out

def fit(im, size, pad=0.06):
    s = int(size * (1 - 2 * pad))
    im = im.copy(); im.thumbnail((s, s), Image.LANCZOS)
    c = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    return c

def rounded_mask(w, h, r):
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    return m

def crop_card(im):
    """Card backs come drawn on a white page: keep just the card."""
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    nonwhite = ~((a > 238).all(axis=2))
    ys, xs = np.where(nonwhite)
    im = im.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    return im

def cover(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))

def save(im, path, q=86):
    im.save(path, "WEBP", quality=q, method=6)

# ---------- icons, slot symbols ----------
for f in sorted(os.listdir(RAW)):
    n = f[:-4]
    if n.startswith("icon_") or n.startswith("slot_"):
        save(fit(cutout(load(n)), 256), f"{OUT}/icons/{n[5:] if n.startswith('icon_') else n}.webp")

SUIT = {}
for s in "shdc":
    SUIT["fr" + s] = cutout(load(f"suit_fr_{s}"))
for s in "dcbs":
    SUIT["it" + s] = cutout(load(f"suit_it_{s}"))
for k, im in SUIT.items():
    save(fit(im, 128, 0.02), f"{OUT}/icons/suit_{k}.webp")

def pip(key, size, flip=False):
    im = SUIT[key].copy(); im.thumbnail((size, size), Image.LANCZOS)
    return im.rotate(180) if flip else im

# ---------- backs ----------
for n in ("back_fr_light", "back_fr_dark", "back_it"):
    im = cover(crop_card(load(n)), W, H)
    im.putalpha(rounded_mask(W, H, R))
    save(im, f"{OUT}/cards/{n[5:]}.webp")

# ---------- faces ----------
def blank():
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((0, 0, W - 1, H - 1), R, fill=CREAM, outline=INK, width=4)
    return c

RED = (200, 40, 26, 255); BLACK = (30, 26, 20, 255)
def index(c, label, suitkey, color):
    """Rank + small suit in the top-left corner and, upside down, bottom-right."""
    corner = Image.new("RGBA", (54, 92), (0, 0, 0, 0))
    d = ImageDraw.Draw(corner)
    size = 38 if len(label) == 1 else 30
    font = ImageFont.truetype(FONT, size)
    tw = d.textlength(label, font=font)
    d.text(((54 - tw) / 2, 2), label, font=font, fill=color)
    p = pip(suitkey, 32)
    corner.alpha_composite(p, ((54 - p.width) // 2, 50))
    c.alpha_composite(corner, (6, 8))
    c.alpha_composite(corner.rotate(180), (W - 60, H - 100))

LAYOUT = {
    1: [(.5, .5)], 2: [(.5, .08), (.5, .92)], 3: [(.5, .08), (.5, .5), (.5, .92)],
    4: [(.2, .08), (.8, .08), (.2, .92), (.8, .92)],
    5: [(.2, .08), (.8, .08), (.5, .5), (.2, .92), (.8, .92)],
    6: [(.2, .08), (.8, .08), (.2, .5), (.8, .5), (.2, .92), (.8, .92)],
    7: [(.2, .08), (.8, .08), (.5, .29), (.2, .5), (.8, .5), (.2, .92), (.8, .92)],
    8: [(.2, .08), (.8, .08), (.5, .29), (.2, .5), (.8, .5), (.5, .71), (.2, .92), (.8, .92)],
    9: [(.2, .08), (.8, .08), (.2, .36), (.8, .36), (.5, .5), (.2, .64), (.8, .64), (.2, .92), (.8, .92)],
    10: [(.2, .08), (.8, .08), (.5, .22), (.2, .36), (.8, .36), (.2, .64), (.8, .64), (.5, .78), (.2, .92), (.8, .92)],
}
BOX = (58, 52, 182, 308)  # pip area between the corner indices

def pips(c, n, suitkey, size, flip_bottom=True):
    x0, y0, x1, y1 = BOX
    for fx, fy in LAYOUT[n]:
        p = pip(suitkey, size, flip=flip_bottom and fy > .55)
        x = x0 + fx * (x1 - x0) - p.width / 2; y = y0 + fy * (y1 - y0) - p.height / 2
        c.alpha_composite(p, (round(x), round(y)))

def art(c, name):
    im = cover(load(name), W - 64, H - 64)
    mask = rounded_mask(im.width, im.height, 12)
    frame = Image.new("RGBA", (im.width + 8, im.height + 8), INK)
    frame.putalpha(rounded_mask(frame.width, frame.height, 15))
    c.alpha_composite(frame, (28, 28)); im.putalpha(mask); c.alpha_composite(im, (32, 32))

FR_LABEL = {"T": "10", "J": "J", "Q": "Q", "K": "K", "A": "A"}
for s in "shdc":
    color = RED if s in "hd" else BLACK
    for r in "23456789TJQKA":
        c = blank(); key = "fr" + s; label = FR_LABEL.get(r, r)
        if r in "JQK":
            art(c, f"fr_{r}{s}")
        elif r == "A":
            p = pip(key, 140); c.alpha_composite(p, ((W - p.width) // 2, (H - p.height) // 2))
        else:
            pips(c, int(label), key, 46)
        index(c, label, key, color)
        save(c, f"{OUT}/cards/fr/{r}{s}.webp")

IT_NUM = {"F": "8", "C": "9", "R": "10"}
for s in "dcbs":
    for r in "1234567FCR":
        c = blank(); key = "it" + s; label = IT_NUM.get(r, r)
        if r in "FCR":
            art(c, f"it_{r}{s}")
        elif r == "1":
            p = pip(key, 150); c.alpha_composite(p, ((W - p.width) // 2, (H - p.height) // 2))
        else:
            pips(c, int(r), key, 58, flip_bottom=False)
        index(c, label, key, INK)
        save(c, f"{OUT}/cards/it/{r}{s}.webp")
print("done")
