import { fileURLToPath } from "node:url";
import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

// Component tests run in jsdom with api.ts mocked: no test talks to a backend.
export default mergeConfig(
  viteConfig,
  defineConfig({
    // folderScan.test.ts reads the vaults seed_vaults.py registers, so the browser parse is checked against them.
    server: { fs: { allow: [".", fileURLToPath(new URL("../../testdata/vaults", import.meta.url))] } },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
      // styles.test.ts reads the stylesheet as text; without this vitest hands every CSS import back empty.
      css: { include: [/styles\.css/] },
    },
  }),
);
