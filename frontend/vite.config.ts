import { defineConfig } from 'vite';

export default defineConfig({
  worker: { format: 'es' },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://api:8000', changeOrigin: true },
    },
  },
});
