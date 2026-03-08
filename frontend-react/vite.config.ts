import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';

// GitHub Pages 部署在 https://<user>.github.io/<repo>/
// 本地开发 base 为 '/'，构建时可通过 BASE_PATH 指定，如 '/Ami-React/'
const base = process.env.BASE_PATH ?? '/';

/** 构建结束后复制 index.html 为 404.html，使 GitHub Pages 下直接访问子路径也能加载 SPA */
function copy404Plugin() {
  return {
    name: 'copy-404',
    closeBundle() {
      const outDir = path.resolve(__dirname, 'dist');
      const index = path.join(outDir, 'index.html');
      const notFound = path.join(outDir, '404.html');
      if (fs.existsSync(index)) {
        fs.copyFileSync(index, notFound);
      }
    },
  };
}

export default defineConfig({
  base,
  plugins: [react(), copy404Plugin()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 5173,
  },
});
