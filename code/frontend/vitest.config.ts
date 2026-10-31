import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";

// Component tests run in jsdom with api.ts mocked: no test talks to a backend.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
      // styles.test.ts reads the stylesheet as text; without this vitest hands every CSS import back empty.
      css: { include: [/styles\.css/] },
    },
  }),
);
