import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

import { cloudflare } from "@cloudflare/vite-plugin";

// Static SPA build (Cloudflare Pages friendly). Output -> dist/.
export default defineConfig({
  plugins: [react(), cloudflare()],
  server: { port: 5173, host: true },
  preview: { port: 4173, host: true },
  build: { outDir: "dist", sourcemap: false },
});