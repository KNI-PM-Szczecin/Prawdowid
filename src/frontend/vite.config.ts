import preact from "@preact/preset-vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The dev server forwards /api to the Go backend, so the browser needs no CORS (docs/api.md §7).
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:3001";

export default defineConfig({
  plugins: [preact(), tailwindcss()],
  server: {
    proxy: {
      "/api": backendUrl,
    },
  },
});
