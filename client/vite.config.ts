import path from "node:path";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendSrc = path.resolve(__dirname, "../frontend/src");
const clientNodeModules = path.resolve(__dirname, "node_modules");
const appVersion = JSON.parse(
  readFileSync(path.resolve(__dirname, "package.json"), "utf-8"),
).version as string;

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(appVersion),
  },
  resolve: {
    alias: {
      "@": frontendSrc,
      "@tauri-apps/api": path.join(clientNodeModules, "@tauri-apps/api"),
      "@tauri-apps/plugin-opener": path.join(
        clientNodeModules,
        "@tauri-apps/plugin-opener",
      ),
      "@tauri-apps/plugin-http": path.join(
        clientNodeModules,
        "@tauri-apps/plugin-http",
      ),
      react: path.join(clientNodeModules, "react"),
      "react-dom": path.join(clientNodeModules, "react-dom"),
      "react/jsx-runtime": path.join(clientNodeModules, "react/jsx-runtime"),
      "react/jsx-dev-runtime": path.join(
        clientNodeModules,
        "react/jsx-dev-runtime",
      ),
    },
    dedupe: ["react", "react-dom"],
  },
  server: {
    port: 1420,
    strictPort: true,
    fs: {
      allow: [path.resolve(__dirname, "..")],
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  optimizeDeps: {
    include: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime"],
  },
});
