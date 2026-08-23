"""Generate the FIRE application icon.

Drawn in code rather than kept as a binary blob, so it is reviewable in a diff
and reproducible on any machine.

The mark is a flame, because the product is called FIRE and at 16 pixels in a
taskbar a shape is recognisable where a letter is not. It sits on the same dark
panel and the same orange the terminal uses, so the icon, the application and
the website are visibly one thing.

    python packaging/make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "fire.ico"
SIZES = (256, 128, 64, 48, 32, 24, 16)

GROUND = (13, 17, 23, 255)        # the terminal's own background
FLAME = (240, 136, 62, 255)       # the accent
CORE = (255, 197, 120, 255)       # a lighter core so the shape reads at 16px


def _cubic(p0, p1, p2, p3, steps: int = 40):
    """Cubic bezier, sampled. Cubic and not quadratic because a flame needs an
    S on the way up: narrow near the tip, wide low down. A quadratic curve can
    only bulge one way, which is why the first attempts read as an egg."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        out.append((u**3 * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return out


# The silhouette, in fractions of the canvas. A sharp tip, a narrow upper
# third, the widest point low, and a round base.
TIP = (0.500, 0.070)
RIGHT = (0.760, 0.660)
LEFT = (0.240, 0.660)
OUTLINE = (
    (TIP, (0.545, 0.300), (0.760, 0.460), RIGHT),          # tip down the right
    (RIGHT, (0.760, 0.905), (0.240, 0.905), LEFT),         # round the base
    (LEFT, (0.240, 0.460), (0.455, 0.300), TIP),           # back up the left
)


def _flame(draw: ImageDraw.ImageDraw, s: float, scale: float,
           colour: tuple[int, int, int, int], lift: float = 0.0) -> None:
    cx, cy = 0.5, 0.5 + 0.055 * lift

    def place(point):
        x, y = point
        # Scale about the centre, then lean the whole shape very slightly right.
        return (s * (cx + (x - 0.5) * scale + 0.012 * lift),
                s * (cy + (y - 0.5) * scale))

    points: list[tuple[float, float]] = []
    for p0, p1, p2, p3 in OUTLINE:
        segment = _cubic(place(p0), place(p1), place(p2), place(p3))
        points.extend(segment if not points else segment[1:])
    draw.polygon(points, fill=colour)


def render(size: int) -> Image.Image:
    # Draw large and downsample: the only reliable way to get clean curves at
    # 16 and 24 pixels out of polygon fills.
    ss = 8 if size <= 64 else 4
    s = size * ss
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = s * 0.22
    draw.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=GROUND)

    _flame(draw, s, 1.0, FLAME)
    _flame(draw, s, 0.46, CORE, lift=1.0)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    frames = [render(n) for n in SIZES]
    frames[0].save(OUT, format="ICO",
                   sizes=[(n, n) for n in SIZES],
                   append_images=frames[1:])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(SIZES)} sizes)")

    preview = Path(__file__).resolve().parents[1] / "site" / "img" / "icon.png"
    render(256).save(preview)
    print(f"wrote {preview}")


if __name__ == "__main__":
    main()
