import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built files are served by Django under /static/ (STATICFILES_DIRS -> frontend/dist).
// In development, `npm run dev` serves the app with hot reload and proxies /api to Django.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
