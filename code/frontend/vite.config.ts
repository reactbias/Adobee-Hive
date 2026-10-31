import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api, /mcp and /.well-known are proxied to the FastAPI backend.
const backend = process.env.VITE_DEV_BACKEND ?? "http://localhost:8000";

// `vite preview` serves a built app and does NOT use `server.proxy`, so a LAN demo ends up
// calling the backend cross-origin. Chrome then applies Private Network Access: it sends
// `Access-Control-Request-Private-Network` on the preflight and refuses unless the server
// answers `Access-Control-Allow-Private-Network: true`. Starlette's CORS middleware does not,
// so Chrome fails while Safari — which does not send that header — works. Proxying here keeps
// the app same-origin, so there is no preflight to fail.
const previewBackend = process.env.VITE_PREVIEW_BACKEND ?? backend;
const proxy = { "/api": previewBackend, "/mcp": previewBackend, "/.well-known": previewBackend };

// GitHub Pages serves the site under /<repo>/; VITE_BASE sets that path at build time.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": backend, "/mcp": backend, "/.well-known": backend },
  },
  preview: { host: true, proxy },
});
