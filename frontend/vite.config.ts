import {defineConfig} from 'vite';

export default defineConfig({
  server: {
    allowedHosts: ['frontend'],
    proxy: {
      '/api': {target: process.env.API_PROXY_TARGET || 'http://localhost:8000', changeOrigin: true},
    },
  },
});
