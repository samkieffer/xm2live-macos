#!/usr/bin/env python3
"""Génère AppIcon.icns pour XM2Live (squircle dégradé + barres d'égaliseur)."""
import os
import subprocess
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ICONSET = os.path.join(HERE, "icon", "AppIcon.iconset")
ICNS = os.path.join(HERE, "icon", "AppIcon.icns")
S = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def master():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Dégradé vertical indigo -> bleu cyan.
    top, bottom = (76, 70, 200), (40, 150, 235)
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        grad.putpixel((0, y), lerp(top, bottom, y / S))
    grad = grad.resize((S, S))

    # Masque squircle (coins arrondis style macOS).
    radius = int(S * 0.225)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=255)

    img.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(img)

    # Barres d'égaliseur / pattern tracker.
    heights = [0.42, 0.66, 0.30, 0.80, 0.52, 0.92, 0.38]
    n = len(heights)
    margin = S * 0.20
    span = S - 2 * margin
    gap = span * 0.045
    bw = (span - gap * (n - 1)) / n
    cy = S * 0.5
    for i, h in enumerate(heights):
        x0 = margin + i * (bw + gap)
        bh = h * S * 0.46
        y0, y1 = cy - bh / 2, cy + bh / 2
        r = bw * 0.45
        draw.rounded_rectangle([x0, y0, x0 + bw, y1], radius=r, fill=(255, 255, 255, 235))

    return img


def main():
    os.makedirs(ICONSET, exist_ok=True)
    base = master()
    specs = [
        (16, "16x16"), (32, "16x16@2x"),
        (32, "32x32"), (64, "32x32@2x"),
        (128, "128x128"), (256, "128x128@2x"),
        (256, "256x256"), (512, "256x256@2x"),
        (512, "512x512"), (1024, "512x512@2x"),
    ]
    for size, name in specs:
        base.resize((size, size), Image.LANCZOS).save(
            os.path.join(ICONSET, f"icon_{name}.png"))
    subprocess.run(["iconutil", "-c", "icns", ICONSET, "-o", ICNS], check=True)
    print("Écrit:", ICNS)


if __name__ == "__main__":
    main()
