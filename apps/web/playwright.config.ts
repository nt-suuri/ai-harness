import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080" },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command:
          "cd ../.. && uv run uvicorn api.main:app --host 127.0.0.1 --port 8080",
        url: "http://127.0.0.1:8080/api/ping",
        reuseExistingServer: false,
        timeout: 60_000,
      },
});
