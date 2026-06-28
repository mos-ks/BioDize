# Deploying BioDize (laptop-free, for the jury)

One repo, two auto-deploy targets. The jury just opens the website and uploads a
PDF — no team laptop, no local tunnel.

```
Frontend  →  GitHub Pages   (static, auto-deploys on push)   https://mos-ks.github.io/BioDize/
Backend   →  Render         (Docker, deploys from this repo) https://<your-app>.onrender.com
```

The backend does **no local computation** — every model (OpenAI VLM, Mistral OCR)
is a remote API — so a free instance is plenty (no GPU).

---

## 1. Backend → Render (one-time, ~5 min)

[Render](https://render.com) is a cloud host that runs your Docker container and
gives it a public HTTPS URL. It reads [`render.yaml`](render.yaml)
and redeploys automatically on every push.

1. Create a **free** account at render.com (sign in with GitHub).
2. **New → Blueprint** → connect the `mos-ks/BioDize` repo. Render finds
   `render.yaml` (repo root) and proposes the `biodize-backend` web service.
3. Set the secret env vars in the dashboard (the keys never go in git):
   - `OPENAI_API_KEY` — your OpenAI key
   - `MISTRAL_API_KEY` — your Mistral key
   - `OPENAI_MODEL` — your exact vision model id (match your local `.env`)
4. **Apply / Deploy.** When it's live, copy the URL, e.g.
   `https://biodize-backend.onrender.com`. Check `…/health` returns `{"status":"ok"}`.

## 2. Point the website at the backend

1. In GitHub: **repo → Settings → Secrets and variables → Actions → Variables →
   New variable**: `VITE_API_BASE` = your Render URL.
2. Re-run the Pages deploy (push any commit, or **Actions → Deploy to GitHub Pages
   → Run workflow**). The static build now bakes in the backend URL.

Done. The jury opens `https://mos-ks.github.io/BioDize/`, uploads a batch-record
PDF, and reviews the results. (No `VITE_API_BASE`? Visitors can still point the app
at any backend via the in-app gear, or `…/go.html?api=<backend-url>`.)

---

## Free-tier caveats (fine for a live demo)

- **Cold start:** a free service sleeps after ~15 min idle; the first request then
  takes ~30–60 s. Hit `/health` once before judging to warm it.
- **Memory:** Render free is 512 MB. Rendering a 46-page PDF is the heaviest local
  step; if it OOMs, upload a smaller PDF or bump the plan.
- **Ephemeral storage:** the uploaded PDF, rendered page images and the SQLite DB
  live on the container's disk and reset on restart/redeploy. That's fine *within a
  judging session* (upload → process → review). For persistence across restarts,
  set `DATABASE_URL` to a free Supabase Postgres (slot already in `render.yaml`) and
  attach a persistent disk for `./var` (paid).

## Alternatives

- **Hugging Face Spaces (Docker):** also free, no 15-min spin-down — same image,
  needs an `app_port: 8000` Space config.
- **Desktop installer** (`installer/`): bundles the backend into an Electron app the
  user runs locally — fully offline, no cloud account, but needs install + keys.
