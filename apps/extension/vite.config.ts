import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { crx } from "@crxjs/vite-plugin";
import manifest from "./manifest.json";

// .env lives at the monorepo root, not in this package.
const repoRoot = fileURLToPath(new URL("../../", import.meta.url));

export default defineConfig({
  envDir: repoRoot,
  plugins: [react(), crx({ manifest })],
});
