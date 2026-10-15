import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: { environment: 'jsdom', setupFiles: ['./src/tests/setup.ts'], maxWorkers: 2 },
  worker: { format: 'es' },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://api:8000', changeOrigin: true },
    },
  },
});
