import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// PORT and BASE_PATH are required on Replit but optional locally.
const rawPort = process.env.PORT;
const port = rawPort ? Number(rawPort) : 5173;
const basePath = process.env.BASE_PATH ?? "/";

export default defineConfig({
  base: basePath,
  plugins: [
    react(),
    tailwindcss(),
    // Replit-only plugins — only loaded when running inside Replit
    ...(process.env.REPL_ID !== undefined
      ? [
          // @ts-ignore — optional Replit plugin
          ...(await import("@replit/vite-plugin-runtime-error-modal")
            .then((m) => [m.default()])
            .catch(() => [])),
          ...(process.env.NODE_ENV !== "production"
            ? await import("@replit/vite-plugin-cartographer")
                .then((m) => [
                  m.cartographer({
                    root: path.resolve(import.meta.dirname, ".."),
                  }),
                ])
                .catch(() => [])
            : []),
          ...(process.env.NODE_ENV !== "production"
            ? await import("@replit/vite-plugin-dev-banner")
                .then((m) => [m.devBanner()])
                .catch(() => [])
            : []),
        ]
      : []),
  ],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
      "@assets": path.resolve(
        import.meta.dirname,
        "..",
        "..",
        "attached_assets"
      ),
    },
    dedupe: ["react", "react-dom"],
  },
  root: path.resolve(import.meta.dirname),
  build: {
    outDir: path.resolve(import.meta.dirname, "dist/public"),
    emptyOutDir: true,
  },
  server: {
    port,
    host: "0.0.0.0",
    allowedHosts: true,
    fs: {
      strict: true,
      deny: ["**/.*"],
    },
  },
  preview: {
    port,
    host: "0.0.0.0",
    allowedHosts: true,
  },
});
