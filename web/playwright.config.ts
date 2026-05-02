import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/browser",
  outputDir: "test-artifacts",
  use: {
    baseURL: "http://localhost:3099",
    screenshot: "on",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    { name: "mobile", use: { viewport: { width: 375, height: 812 } } },
  ],
  webServer: {
    command: "npm run build && cp -r .next/static .next/standalone/.next/static && PORT=3099 node .next/standalone/server.js",
    port: 3099,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
