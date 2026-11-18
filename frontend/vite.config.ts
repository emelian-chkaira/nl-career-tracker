import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const api = process.env.API_URL ?? "http://localhost:8787";
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 5173, proxy: { "/api": api, "/logos": api } },
});
