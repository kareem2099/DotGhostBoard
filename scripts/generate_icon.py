"""
scripts/generate_icon.py
────────────────────────
Generates DotGhostBoard icon at all standard Linux sizes.

Output:
  data/icons/icon_16.png
  data/icons/icon_32.png
  data/icons/icon_48.png
  data/icons/icon_64.png
  data/icons/icon_128.png
  data/icons/icon_256.png
  data/icons/icon.png        ← main (256px) used by the app

Run once:
  python3 scripts/generate_icon.py
"""

import os
import math
from PIL import Image, ImageDraw, ImageFilter

# ── Output directory ──────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(BASE_DIR, "data", "icons")
os.makedirs(ICONS_DIR, exist_ok=True)

# ── Colors ────────────────────────────────────────────────────
BG         = (15,  15,  15,  255)   # #0f0f0f
GHOST      = (0,   255, 65,  255)   # #00ff41  neon green
GHOST_DIM  = (0,   180, 45,  220)   # slightly darker for body shading
EYE        = (15,  15,  15,  255)   # #0f0f0f  eyes (same as bg → cut-outs)
GLOW       = (0,   255, 65,  60)    # transparent glow layer
TRANSPARENT = (0,  0,   0,   0)


def draw_ghost(size: int) -> Image.Image:
    """
    Draws the ghost icon at `size` x `size` pixels.
    Scales all coordinates proportionally.
    """
    S = size
    scale = S / 256          # all coords designed at 256px

    img = Image.new("RGBA", (S, S), TRANSPARENT)
    d   = ImageDraw.Draw(img)

    # ── Helper: scale a value ──
    def sc(v):
        return v * scale

    # ─────────────────────────────────────────
    # 1.  Outer glow (soft circle behind ghost)
    # ─────────────────────────────────────────
    glow_layer = Image.new("RGBA", (S, S), TRANSPARENT)
    gd = ImageDraw.Draw(glow_layer)
    gd.ellipse(
        [sc(28), sc(28), sc(228), sc(228)],
        fill=(0, 255, 65, 35)
    )
    glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=sc(14)))
    img = Image.alpha_composite(img, glow_blurred)
    d   = ImageDraw.Draw(img)

    # ─────────────────────────────────────────
    # 2.  Ghost body
    #     Top: semicircle (head)
    #     Bottom: wavy skirt (3 bumps)
    # ─────────────────────────────────────────
    cx      = S / 2
    head_r  = sc(88)        # head radius
    head_cy = sc(108)       # center-y of the head circle
    body_top   = head_cy - head_r       # top of head
    body_bot   = sc(210)                # bottom of ghost body

    # Build the ghost polygon as a list of (x, y) points
    pts = []

    # ── Left side going up ──
    pts.append((cx - head_r, head_cy))

    # ── Head arc (semicircle, left to right going UP) ──
    steps = 60
    for i in range(steps + 1):
        angle = math.pi + (math.pi * i / steps)   # 180° → 360°
        x = cx + head_r * math.cos(angle)
        y = head_cy + head_r * math.sin(angle)
        pts.append((x, y))

    # ── Right side going down ──
    pts.append((cx + head_r, head_cy))
    pts.append((cx + head_r, body_bot))

    # ── Wavy bottom (3 bumps, right to left) ──
    bump_h  = sc(22)   # bump height
    bw      = (head_r * 2) / 3   # width of each bump section
    x_right = cx + head_r
    x_left  = cx - head_r

    # 3 bumps: valleys at 1/3 and 2/3, center bump
    bump_xs = [
        x_right,
        x_right - bw * 0.5,
        x_right - bw,
        x_right - bw * 1.5,
        x_right - bw * 2,
        x_right - bw * 2.5,
        x_left,
    ]
    bump_ys = [
        body_bot,
        body_bot - bump_h,   # bump peak (right)
        body_bot,             # valley
        body_bot - bump_h,   # bump peak (center)
        body_bot,             # valley
        body_bot - bump_h,   # bump peak (left)
        body_bot,
    ]
    for bx, by in zip(reversed(bump_xs), reversed(bump_ys)):
        pts.append((bx, by))

    pts.append((x_left, body_bot))
    pts.append((x_left, head_cy))

    d.polygon(pts, fill=GHOST)

    # ─────────────────────────────────────────
    # 3.  Eyes  (two dark ellipses)
    # ─────────────────────────────────────────
    eye_y_top = head_cy - sc(18)
    eye_y_bot = head_cy + sc(10)
    eye_w     = sc(22)
    eye_h     = sc(28)
    eye_gap   = sc(30)   # distance from center to eye center

    # Left eye
    d.ellipse(
        [cx - eye_gap - eye_w, eye_y_top,
         cx - eye_gap + eye_w, eye_y_bot],
        fill=EYE
    )
    # Right eye
    d.ellipse(
        [cx + eye_gap - eye_w, eye_y_top,
         cx + eye_gap + eye_w, eye_y_bot],
        fill=EYE
    )

    # ─────────────────────────────────────────
    # 4.  Eye shine (tiny white highlight)
    # ─────────────────────────────────────────
    shine_r = sc(6)
    shine_off_x = sc(6)
    shine_off_y = sc(6)

    d.ellipse(
        [cx - eye_gap - shine_off_x - shine_r, eye_y_top + shine_off_y - shine_r,
         cx - eye_gap - shine_off_x + shine_r, eye_y_top + shine_off_y + shine_r],
        fill=(255, 255, 255, 180)
    )
    d.ellipse(
        [cx + eye_gap - shine_off_x - shine_r, eye_y_top + shine_off_y - shine_r,
         cx + eye_gap - shine_off_x + shine_r, eye_y_top + shine_off_y + shine_r],
        fill=(255, 255, 255, 180)
    )

    # ─────────────────────────────────────────
    # 5.  Subtle inner body gradient  (lighter top stripe)
    # ─────────────────────────────────────────
    for row in range(int(sc(20))):
        alpha = int(40 * (1 - row / sc(20)))
        d.line(
            [(cx - head_r + sc(10), body_top + sc(10) + row),
             (cx + head_r - sc(10), body_top + sc(10) + row)],
            fill=(255, 255, 255, alpha),
            width=1
        )

    return img


def generate_all():
    sizes = [16, 32, 48, 64, 128, 256]
    for s in sizes:
        icon = draw_ghost(s)
        filename = f"icon_{s}.png"
        path = os.path.join(ICONS_DIR, filename)
        icon.save(path, "PNG")
        print(f"  ✓ {filename}  ({s}x{s})")

    # Main icon copy
    main_icon = os.path.join(ICONS_DIR, "icon.png")
    draw_ghost(256).save(main_icon, "PNG")
    print(f"  ✓ icon.png  (256x256) — main")

    print(f"\n👻 All icons saved to: {ICONS_DIR}")


if __name__ == "__main__":
    print("Generating DotGhostBoard icons...")
    generate_all()
