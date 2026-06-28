"""Generate BioDize installer icons from frontend/public/logo.svg.

Renders the actual pill-pixel logo and places it on a light-indigo
rounded-card background, producing:
  icon.png   — 512 × 512 PNG  (Linux AppImage / desktop entry)
  icon.ico   — 7-resolution ICO using PNG-in-ICO (Windows NSIS + taskbar)
  icon.icns  — Apple icon bundle  (macOS Dock + Finder)

Rendering strategies (tried in order):
  1. cairosvg      — pip install cairosvg   (needs libcairo system lib; works on Linux CI)
  2. @resvg/resvg-js via Node.js subprocess — auto-installed to a temp dir if missing
  3. Pillow-only programmatic pill fallback — no external dependencies

Run:
  pip install Pillow
  python installer/build/make-icon.py
"""
from __future__ import annotations

import io
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow is required:  pip install Pillow")

REPO    = Path(__file__).parent.parent.parent.resolve()
SVG     = REPO / "frontend" / "public" / "logo.svg"
OUT     = Path(__file__).parent

# Icon background — very light indigo to complement the blue logo
ICON_BG = (238, 242, 255, 255)   # #EEF2FF  (indigo-50)


# ── SVG rendering ─────────────────────────────────────────────────────────────

def _render_cairosvg(width: int) -> bytes | None:
    try:
        import cairosvg  # type: ignore
        return cairosvg.svg2png(
            url=str(SVG),
            output_width=width,
            background_color="transparent",
        )
    except (ImportError, OSError):
        return None


_RESVG_TMPDIR: Path | None = None   # created once, reused for all sizes


def _get_resvg_dir() -> Path | None:
    """Return (or lazily create) a temp dir with @resvg/resvg-js installed."""
    global _RESVG_TMPDIR
    if _RESVG_TMPDIR is not None:
        return _RESVG_TMPDIR

    node_bin = _find_node()
    if node_bin is None:
        return None

    td = Path(tempfile.mkdtemp())
    # Write a minimal package.json so npm install works without warnings
    (td / "package.json").write_text('{"name":"icon-build","private":true}')

    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    print("  [resvg] installing @resvg/resvg-js (once)...")
    r = subprocess.run([npm, "install", "--save", "@resvg/resvg-js"],
                       cwd=str(td), capture_output=True)
    if r.returncode != 0:
        return None

    _RESVG_TMPDIR = td
    return td


def _render_resvg_node(width: int) -> bytes | None:
    """Use @resvg/resvg-js via Node.js subprocess (single install, cached)."""
    node_bin = _find_node()
    if node_bin is None:
        return None

    td = _get_resvg_dir()
    if td is None:
        return None

    svg_path_json = json.dumps(str(SVG).replace("\\", "/"))
    script = (
        "const {Resvg}=require('@resvg/resvg-js'),fs=require('fs');"
        f"const r=new Resvg(fs.readFileSync({svg_path_json},'utf8'),"
        f"{{fitTo:{{mode:'width',value:{width}}}}});"
        "process.stdout.write(r.render().asPng());"
    )
    script_file = td / "render.js"
    script_file.write_text(script)

    result = subprocess.run([str(node_bin), str(script_file)],
                            cwd=str(td), capture_output=True)
    if result.returncode == 0 and len(result.stdout) > 100:
        return result.stdout
    return None


def _find_node() -> Path | None:
    for name in ("node", "node.exe"):
        found = _which(name)
        if found:
            return Path(found)
    return None


def _which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


_SVG_CACHE: dict[int, bytes] = {}   # width -> PNG bytes


def render_svg(width: int) -> bytes | None:
    """Return raw PNG bytes for logo.svg rendered at the given pixel width.
    Results are cached so the SVG is only rendered once per width."""
    if width in _SVG_CACHE:
        return _SVG_CACHE[width]

    if not SVG.exists():
        print(f"  [warn] logo.svg not found at {SVG}")
        return None

    for fn in (_render_cairosvg, _render_resvg_node):
        data = fn(width)
        if data:
            _SVG_CACHE[width] = data
            return data

    print("  [warn] Could not render SVG (no cairosvg or Node.js available). Using fallback icon.")
    return None


# ── Icon composition ──────────────────────────────────────────────────────────

_LOGO_SRC: Image.Image | None = None   # rendered once at 1024px


def _get_logo_src() -> Image.Image | None:
    """Render logo.svg at 1024px and cache the result as an RGBA Image."""
    global _LOGO_SRC
    if _LOGO_SRC is not None:
        return _LOGO_SRC
    data = render_svg(1024)
    if data:
        _LOGO_SRC = Image.open(io.BytesIO(data)).convert("RGBA")
    return _LOGO_SRC


def make_icon_image(size: int) -> Image.Image:
    """Return a square RGBA image of the given pixel size.

    Tries to use the real logo SVG; falls back to a programmatic pill drawing.
    """
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d      = ImageDraw.Draw(canvas)
    r      = max(1, int(size * 0.18))
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=ICON_BG)

    logo_src = _get_logo_src()
    if logo_src:
        logo = logo_src   # will be resized below
        # The SVG is portrait (~1:1.19). Fit logo so it fills 84% of height.
        pad    = int(size * 0.08)
        target_h = size - pad * 2
        target_w = int(target_h * logo.width / logo.height)
        if target_w > size - pad * 2:
            target_w = size - pad * 2
            target_h = int(target_w * logo.height / logo.width)
        logo = logo.resize((target_w, target_h), Image.LANCZOS)
        x = (size - target_w) // 2
        y = (size - target_h) // 2
        canvas.alpha_composite(logo, (x, y))
    else:
        _draw_fallback_pill(canvas, size)

    return canvas


def _draw_fallback_pill(canvas: Image.Image, size: int) -> None:
    """Pillow-only fallback: draw a simplified pill + pixel art icon."""
    d   = ImageDraw.Draw(canvas)
    s   = size / 100

    NAVY  = (25,  21,  87,  255)
    MID   = (30,  80,  180, 255)
    BLUE  = (56,  107, 222, 255)
    LIGHT = (100, 149, 237, 255)

    # Pill body — bottom half
    pill_l  = int(20 * s)
    pill_r  = int(80 * s)
    pill_t  = int(55 * s)
    pill_b  = int(82 * s)
    pill_rx = int((pill_b - pill_t) / 2)
    d.rounded_rectangle([pill_l, pill_t, pill_r, pill_b], radius=pill_rx, fill=MID)

    # Divider line on pill
    mid_x = (pill_l + pill_r) // 2
    d.rectangle([mid_x - 1, pill_t + 3, mid_x + 1, pill_b - 3], fill=LIGHT)

    # Capsule upper half (rounded top)
    cap_l = int(22 * s)
    cap_r = int(62 * s)
    cap_t = int(14 * s)
    cap_b = int(58 * s)
    cap_r2 = int((cap_r - cap_l) / 2)
    d.rounded_rectangle([cap_l, cap_t, cap_r, cap_b], radius=cap_r2, fill=NAVY)

    # Pixel art dissolve (step-grid of squares, bottom-left)
    pixel = max(2, int(4.5 * s))
    gap   = max(1, int(1.2 * s))
    grid_step = pixel + gap
    PIXEL_MAP = [
        (0,0),(1,0),(2,0),(3,0),
        (0,1),(1,1),      (3,1),
        (0,2),            (3,2),(4,2),
        (0,3),(1,3),      (3,3),
              (1,4),(2,4),(3,4),
              (1,5),      (3,5),
    ]
    ox = int(12 * s)
    oy = int(44 * s)
    for gx, gy in PIXEL_MAP:
        px = ox + gx * grid_step
        py = oy + gy * grid_step
        col = LIGHT if (gx + gy) % 2 == 0 else BLUE
        d.rectangle([px, py, px + pixel - 1, py + pixel - 1], fill=col)


# ── PNG export ────────────────────────────────────────────────────────────────

def save_png(path: Path, size: int = 512) -> None:
    img = make_icon_image(size)
    # Flatten onto white for formats that don't support alpha
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    white.alpha_composite(img)
    white.convert("RGB").save(str(path), format="PNG", optimize=True)
    print(f"  icon.png   -> {path}  ({size}x{size})")


# ── ICO export (PNG-in-ICO) ───────────────────────────────────────────────────

def save_ico(path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    blobs: list[bytes] = []
    for s in sizes:
        img = make_icon_image(s)
        # Flatten transparent pixels onto white for Windows shell compatibility
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white.alpha_composite(img)
        buf = io.BytesIO()
        white.convert("RGBA").save(buf, format="PNG", optimize=True)
        blobs.append(buf.getvalue())

    n      = len(sizes)
    header = struct.pack("<HHH", 0, 1, n)
    offset = 6 + 16 * n
    entries = b""
    for s, blob in zip(sizes, blobs):
        w = h = 0 if s == 256 else s
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset)
        offset  += len(blob)

    with open(path, "wb") as fh:
        fh.write(header + entries + b"".join(blobs))
    print(f"  icon.ico   -> {path}  ({sizes})")


# ── ICNS export ───────────────────────────────────────────────────────────────

ICNS_TYPES = {16: b"icp4", 32: b"icp5", 64: b"icp6", 128: b"ic07",
              256: b"ic08", 512: b"ic09", 1024: b"ic10"}


def save_icns(path: Path) -> None:
    entries: list[bytes] = []
    for size, type_id in ICNS_TYPES.items():
        img = make_icon_image(size)
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white.alpha_composite(img)
        buf = io.BytesIO()
        white.convert("RGBA").save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        entries.append(type_id + struct.pack(">I", 8 + len(data)) + data)

    body  = b"".join(entries)
    total = 8 + len(body)
    with open(path, "wb") as fh:
        fh.write(b"icns" + struct.pack(">I", total) + body)
    print(f"  icon.icns  -> {path}  ({list(ICNS_TYPES.keys())})")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating BioDize icons from logo.svg ...")
    # Clean stale test file
    stale = OUT / "logo_test.png"
    if stale.exists():
        stale.unlink()

    save_png(OUT / "icon.png", size=512)
    save_ico(OUT / "icon.ico")
    save_icns(OUT / "icon.icns")
    print("Done.")
