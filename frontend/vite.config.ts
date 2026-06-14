import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API base URLs come from env at build time (VITE_INTAKE_URL / VITE_RESULTS_URL).
// In local dev they default to the docker-compose host ports.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
