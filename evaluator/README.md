# BioDize Evaluator

Desktop toolkit for reviewing, correcting and debugging digitized pharmaceutical batch records.

## Quick Start

**Windows:** Double-click `BioDize Launcher.bat`

**Requirements:** Python 3.10+ (ARM64 Windows compatible), Node.js 18+

## Tools

| File | Purpose |
|------|---------|
| `launcher.pyw` | Desktop GUI launcher with step-by-step workflow |
| `reviewer.py` | Interactive batch record reviewer — scan images, bbox editor, keybindings |
| `start.py` | Starts backend (FastAPI) + frontend (Vite) with auto-update from GitHub |
| `load_results.py` | Imports pre-extracted field data into the local database |
| `debugger.py` | Interactive validation rule debugger (REPL) |
| `autopatch.py` | Generates analysis prompts for each validation error |
| `bulk_review.py` | Bulk-confirm all fields in the review queue |
| `export_csv.py` | Exports all fields + flags as UTF-8 CSV |

## Reviewer Features

- **Auto-starts backend** on launch — no manual setup
- **Full-resolution** page images cached in RAM for instant navigation
- **Configurable keybindings** (Enter=confirm, E=correct, Space=next)
- **Zoom:** mouse wheel to zoom, drag to pan, double-click to reset
- **Bbox editor:** draw, move, resize, delete field boxes — Ctrl+Z to undo
- **Multi-batch:** dropdown to switch between documents; "+ Laden" to import new JSON

## ARM64 Windows Notes

PyMuPDF is not available on ARM64 Windows. The evaluator uses `pypdfium2` + `Pillow`
for PDF rendering. `wrangler`/`workerd` (Cloudflare) is skipped via `npm install --ignore-scripts`.
A local `frontend/vite.config.dev.ts` is auto-created to avoid the `@cloudflare/vite-plugin`.
