import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 127.0.0.1, not localhost: Node may resolve localhost to IPv6 (::1) while uvicorn listens on IPv4
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
