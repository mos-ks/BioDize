# BioDize — Frontend

Review UI for digitized handwritten pharma **batch production records**. Upload/process a scanned
record, then work a confidence-gated **review queue** (errors → warnings → low-confidence), jump to the
exact spot on the page via a bounding box, **confirm or correct** each value (audit-logged), inspect the
**flag dashboard** and **role distributions**, and export to Excel.

> Promise: *right or it asks — never silently wrong.* Most fields auto-accept; only the uncertain or
> rule-violating ones reach a human.

React 18 + TypeScript + Vite + Tailwind CSS + react-router. A **static SPA** — no server, no CMS, no
WordPress. Builds to `dist/` and hosts directly on Cloudflare Pages (target domain **biodize.tech**).

## Quick start (dev)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The app talks to the FastAPI backend described in [`../docs/API.md`](../docs/API.md). Point it at a backend
in either of two ways:

- **In-app (no rebuild):** click the **gear / API chip** in the top bar, paste the base URL
  (e.g. `https://<your-tunnel>.trycloudflare.com` or `https://api.biodize.tech`), **Test**, then
  **Save & reload**. This persists to `localStorage`, so a single deployed build can target any backend.
- **Build-time default:** copy `.env.example` to `.env` and set `VITE_API_BASE`.

The API base resolution order is: `localStorage` (in-app setting) → `VITE_API_BASE` → baked-in default.

## Build

```bash
npm run build        # typecheck + vite build -> dist/
npm run preview      # serve the production build locally
```

## Deploy to Cloudflare Pages (biodize.tech)

This is a plain static build — ideal for Cloudflare Pages.

**Option A — Pages Git integration (recommended)**
1. Push this repo to GitHub/GitLab.
2. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**.
3. Build settings:
   - **Framework preset:** Vite
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
   - **Root directory:** `biodize/frontend` (set this if the repo root is the monorepo)
   - **Environment variable:** `VITE_API_BASE = https://api.biodize.tech` (or your tunnel URL for now)
4. **Custom domains → Set up a domain → `biodize.tech`** (and `www`). Because the DNS is already on
   Cloudflare, Pages adds the `CNAME`/records automatically and provisions TLS.

**Option B — Wrangler (direct upload)**
```bash
npm run build
npx wrangler pages deploy dist --project-name biodize
```
Then attach `biodize.tech` under the project's **Custom domains**.

**SPA routing:** `public/_redirects` contains `/* /index.html 200`, so deep links like
`/documents/<id>` resolve correctly on Pages.

### Backend / CORS
The FastAPI backend sets permissive CORS, so the browser app can call it cross-origin. For production,
expose the API at a stable origin (e.g. **`api.biodize.tech`** via a Cloudflare DNS record / tunnel) and
set `VITE_API_BASE` to it. During the hackathon a `cloudflared` quick tunnel works as a temporary base.

## Structure

```
src/
  api/
    types.ts        DTOs mirroring the backend schema (frozen)
    client.ts       typed fetch client; runtime-configurable base URL
  lib/
    ui.tsx          enum metadata (severity/status/category/role), formatters, hooks (useApi, useAsyncAction)
  components/
    atoms.tsx       badges, confidence meter/gauge, states, cards (frozen)
    Layout.tsx      app shell: brand, live health chip, API-settings dialog
  pages/
    DocumentsPage.tsx   library + process/upload + aggregate tallies
    ReviewPage.tsx      the review workspace: queue · all-fields · flags + field detail + bbox locate + confirm/correct
    StatsPage.tsx       flag dashboard + role value distributions
  App.tsx           routes
  main.tsx          entry
```

## Tech notes
- Bounding boxes are normalized `[x0,y0,x1,y1]` (0–1, origin top-left). The review **PageViewer** draws
  the box over the rendered page image, and **falls back to a schematic page** when the backend serves no
  image (the offline stub renders none) — the reviewer always sees *where* a value sits.
- No charting dependency: the distribution histogram is hand-rolled SVG.
