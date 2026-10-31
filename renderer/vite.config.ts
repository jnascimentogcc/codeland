import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vendor groups keep three.js (the bulk of the bundle) in its own long-lived cache entry,
// so an app change does not make the browser download it again.
const vendor = (name: string, packages: string[]) => ({
  name,
  test: new RegExp(`node_modules[\\/](${packages.join("|")})[\\/]`),
});

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    // three.js alone is ~800 kB minified and has no lighter build; the app itself is ~55 kB.
    chunkSizeWarningLimit: 900,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            vendor("react", ["react", "react-dom", "scheduler"]),
            vendor("three", ["three", "postprocessing"]),
            vendor("r3f", [
              "@react-three",
              "troika-three-text",
              "troika-three-utils",
              "troika-worker-utils",
            ]),
          ],
        },
      },
    },
  },
});
