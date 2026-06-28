import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages build — no Cloudflare plugin, base path = /biodize/
export default defineConfig({
  plugins: [react()],
  base: "/biodize/",
  build: { outDir: "dist", sourcemap: false },
});
