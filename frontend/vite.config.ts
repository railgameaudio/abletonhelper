import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Talk to the FastAPI process in dev; in production the API serves
    // the built bundle and this proxy is not used.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
