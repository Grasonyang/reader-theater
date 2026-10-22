import { defineConfig } from 'vite';

export default defineConfig({
  // GitHub Pages 部署在 /<repo>/ 子路徑：BASE_PATH=/reader-theater/ npx vite build
  base: process.env.BASE_PATH ?? '/',
  build: {
    rollupOptions: {
      input: { main: 'index.html', comic: 'comic.html' },
    },
  },
  optimizeDeps: {
    // TalkingHead 用 new URL('./playback-worklet.js', import.meta.url) 找 worklet，
    // 預先打包會改掉模組位置，所以保持原樣由 node_modules 提供
    exclude: ['@met4citizen/talkinghead'],
  },
});
