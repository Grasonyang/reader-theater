import { defineConfig } from 'vite';

export default defineConfig({
  optimizeDeps: {
    // TalkingHead 用 new URL('./playback-worklet.js', import.meta.url) 找 worklet，
    // 預先打包會改掉模組位置，所以保持原樣由 node_modules 提供
    exclude: ['@met4citizen/talkinghead'],
  },
});
