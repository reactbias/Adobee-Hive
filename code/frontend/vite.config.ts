import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api, /mcp and /.well-known are proxied to the FastAPI backend.
const backend = process.env.VITE_DEV_BACKEND ?? "http://localhost:8000";

// GitHub Pages serves the site under /<repo>/; VITE_BASE sets that path at build time.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": backend, "/mcp": backend, "/.well-known": backend },
  },
});
