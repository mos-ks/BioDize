import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static SPA build (Cloudflare Pages friendly). Output -> dist/.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true },
  preview: { port: 4173, host: true },
  build: { outDir: "dist", sourcemap: false },
});
