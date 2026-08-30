import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '');
  const target = env.VITE_API_TARGET || 'http://127.0.0.1:9850';

  return {
    base: '/ui/',
    plugins: [vue(), tailwindcss()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/sessions': { target, changeOrigin: true },
        '/instances': { target, changeOrigin: true },
        '/status': { target, changeOrigin: true },
        '/api': { target, changeOrigin: true },
        '/ws': { target, ws: true, changeOrigin: true },
        '^/chrome\\d+/': { target, ws: true, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      chunkSizeWarningLimit: 1200,
    },
    test: {
      environment: 'happy-dom',
      include: ['tests/unit/**/*.test.ts'],
    },
  };
});
