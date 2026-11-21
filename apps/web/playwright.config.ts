import { defineConfig, devices } from '@playwright/test';

const sharedServer = process.env.SPARK_TEST_BASE_URL;
const baseURL = sharedServer ?? 'http://127.0.0.1:3101';

export default defineConfig({
  testDir: 'tests',
  testMatch: '*.spec.ts',
  workers: 1,
  timeout: 30_000,
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    trace: 'retain-on-failure',
    contextOptions: { reducedMotion: 'reduce' },
  },
  webServer: sharedServer
    ? undefined
    : {
        command: 'npm run dev -- --hostname 127.0.0.1 --port 3101',
        url: baseURL,
        env: { NEXT_TELEMETRY_DISABLED: '1' },
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
