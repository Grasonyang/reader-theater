// 用 Playwright 無頭瀏覽器錄 5 秒預覽影片，驗證角色能載入並對嘴。
//
// 用法：npm run record [-- 輸出.mp4]
// 瀏覽器版本與 playwright 套件不符時，設 CHROMIUM_PATH 指向既有的 Chromium。
//
// 做法是逐格算圖，不是即時錄影：用 page.clock 接管並凍住頁面的時間（Date、
// performance.now、requestAnimationFrame），每推進 1/25 秒拍一張截圖，再用
// ffmpeg 接成 25 fps 並混進處理過的台詞音訊。無頭環境用 CPU 算圖只有十幾 fps，
// 即時錄影（recordVideo 或 CDP screencast）的時間軸會漂一兩秒，對不上音訊。
//
// 對時：頁面講到第二個字時記下 Date.now()（window.theater.syncAt），扣掉該字的
// 時間戳就是音訊起點。第一個字的事件會延遲觸發，不拿來對時。

import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { chromium } from 'playwright';
import { createServer } from 'vite';

const DURATION_S = 5;
const FPS = 25;
const FRAME_MS = 1000 / FPS;
const SIZE = { width: 1280, height: 720 };
const AUDIO = 'assets/audio/test/test_line.wav';
const TIMESTAMPS = 'assets/audio/test/test_line.json';
// 與 src/main.js 的 SYNC_WORD_INDEX 一致
const SYNC_WORD_INDEX = 1;
const output = resolve(process.argv[2] ?? 'preview.mp4');

const server = await createServer({ server: { port: 5173, strictPort: false }, logLevel: 'error' });
await server.listen();

const frameDir = mkdtempSync(join(tmpdir(), 'preview-'));
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: [
    '--autoplay-policy=no-user-gesture-required',
    // 無頭環境沒有 GPU，用 SwiftShader 跑 WebGL
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
  ],
});

try {
  const page = await browser.newPage({ viewport: SIZE });
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.error('[browser]', msg.text());
  });

  // 載入前就接管時間：TalkingHead 啟動時記下 performance.now()，之後才接管的話，
  // 假時鐘比它早，動畫時鐘會停住直到追上
  await page.clock.install();
  await page.goto(server.resolvedUrls.local[0]);
  const loadDeadline = Date.now() + 120_000;
  while (!(await page.evaluate(() => window.theater?.ready || window.theater?.error))) {
    if (Date.now() > loadDeadline) throw new Error('頁面 120 秒內沒有載入完成');
    await page.clock.runFor(100);
  }
  const loadError = await page.evaluate(() => window.theater.error);
  if (loadError) throw new Error(`頁面載入失敗：${loadError}`);

  // 凍住時間，之後只由 runFor 推進；否則截圖花掉的真實時間也會算進動畫
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + FRAME_MS);
  // 不用 page.click：它要等 requestAnimationFrame 確認元素穩定，時間凍住後會卡住
  await page.evaluate(() => document.getElementById('play').click());

  const frames = [];
  const shoot = async () => {
    const t = await page.evaluate(() => Date.now());
    const file = join(frameDir, `${String(frames.length).padStart(5, '0')}.png`);
    await page.screenshot({ path: file });
    frames.push({ t, file });
  };

  // 先推進到第二個字出現，才知道音訊起點
  let syncAt = null;
  while (!syncAt) {
    await page.clock.runFor(FRAME_MS);
    await shoot();
    syncAt = await page.evaluate(() => window.theater.syncAt);
    if (frames.length > FPS * 10) throw new Error('10 秒內沒有開口');
  }
  const syncWord = JSON.parse(readFileSync(TIMESTAMPS, 'utf8')).words[SYNC_WORD_INDEX];
  const start = syncAt - syncWord.start * 1000;
  while (frames.at(-1).t < start + DURATION_S * 1000) {
    await page.clock.runFor(FRAME_MS);
    await shoot();
  }
  const spoken = await page.evaluate(() => document.getElementById('subtitles').textContent.trim());

  // 每個輸出格取時間上最接近的截圖
  const list = [];
  for (let i = 0; i < DURATION_S * FPS; i++) {
    const t = start + i * FRAME_MS;
    const frame = frames.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
    list.push(`file '${frame.file}'`, `duration ${(1 / FPS).toFixed(4)}`);
  }
  const listPath = join(frameDir, 'frames.txt');
  writeFileSync(listPath, list.join('\n') + '\n');

  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'concat', '-safe', '0', '-i', listPath,
    '-i', AUDIO,
    '-t', String(DURATION_S),
    '-map', '0:v', '-map', '1:a',
    '-vf', `fps=${FPS},format=yuv420p`,
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26',
    '-c:a', 'aac', '-b:a', '128k',
    '-movflags', '+faststart',
    output,
  ]);
  console.log(`已輸出 ${output}（${DURATION_S} 秒、${FPS} fps）`);
  console.log(`字幕：${spoken}`);
} finally {
  await browser.close();
  await server.close();
  rmSync(frameDir, { recursive: true, force: true });
}
