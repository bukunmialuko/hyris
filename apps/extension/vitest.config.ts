import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests only: the pure logic at the API seam. Anything needing a real Chrome runtime or a
// live backend belongs in the manual pass documented in the README, not here.
export default defineConfig({
  resolve: {
    alias: {
      "@hyris/contracts": fileURLToPath(new URL("../../packages/contracts/ts/quiz.ts", import.meta.url)),
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
