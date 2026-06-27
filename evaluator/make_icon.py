"""Erstellt biodize.ico — BioDize App-Icon (multi-resolution)."""
import sys, os, subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

from PIL import Image, ImageDraw, ImageFont
import math

def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    p   = size / 64  # scale factor (base = 64px)

    # Hintergrund — abgerundetes Rechteck
    bg = (15, 23, 42)   # slate-900
    r  = int(12 * p)
    d.rounded_rectangle([0, 0, size-1, size-1], radius=r, fill=bg)

    # Kreuz aus zwei Linien ("+" Form) — Molekül-/Pharma-Symbol
    cx, cy = size / 2, size / 2
    arm = size * 0.28
    lw  = max(2, int(4 * p))

    # Vertikaler Balken
    d.line([(cx, cy - arm), (cx, cy + arm)], fill=(79, 142, 247), width=lw)
    # Horizontaler Balken
    d.line([(cx - arm, cy), (cx + arm, cy)], fill=(79, 142, 247), width=lw)

    # 4 Kreise an den Enden (Atome)
    cr = max(2, int(5.5 * p))
    atom = (34, 197, 94)   # grün
    for dx, dy in [(0, -arm), (0, arm), (-arm, 0), (arm, 0)]:
        ax, ay = cx + dx, cy + dy
        d.ellipse([ax-cr, ay-cr, ax+cr, ay+cr], fill=atom)

    # Mittelpunkt
    mc = max(3, int(7 * p))
    d.ellipse([cx-mc, cy-mc, cx+mc, cy+mc], fill=(255, 255, 255))

    # "BD" Text unten rechts (nur ab 48px)
    if size >= 48:
        fs = max(8, int(11 * p))
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", fs)
        except Exception:
            font = ImageFont.load_default()
        tx, ty = size * 0.62, size * 0.72
        d.text((tx, ty), "BD", font=font, fill=(148, 163, 184))

    return img


# Multi-Resolution ICO
sizes = [16, 24, 32, 48, 64, 128, 256]
frames = [draw_icon(s) for s in sizes]

ico_path = ROOT / "biodize.ico"
frames[0].save(
    str(ico_path),
    format="ICO",
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:],
)
print(f"Icon gespeichert: {ico_path}")
