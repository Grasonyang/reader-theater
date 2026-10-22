// 把劇本的一場（或整齣）逐格算圖成影片。
//
// 用法：node scripts/record_scene.mjs <劇本名稱> [場次 id] [-o 輸出.mp4] [--page comic.html]
//   例：node scripts/record_scene.mjs missing-duck s1 -o scene1.mp4
// 劇本在 assets/scripts/<名稱>.json，台詞要先用 scripts/align_lines.py 對齊過。
//
// 做法同 record_preview.mjs：page.clock 凍住頁面時間，每推進 1/25 秒拍一張。
// 音訊不是錄下來的，而是把每句的 wav 放到它實際開口的時間點混在一起：
// 每句講到第二個字時頁面記下時間（window.theater.lineSync），扣掉該字的時間戳
// 就是那句音訊的起點。

import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { chromium } from 'playwright';
import { createServer } from 'vite';

const FPS = 25;
const FRAME_MS = 1000 / FPS;
const SIZE = { width: 1280, height: 720 };

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: { output: { type: 'string', short: 'o' }, page: { type: 'string', default: '' } },
});
const [scriptName, sceneId] = positionals;
if (!scriptName) {
  console.error('用法：node scripts/record_scene.mjs <劇本名稱> [場次 id] [-o 輸出.mp4]');
  process.exit(1);
}
const output = resolve(values.output ?? `${scriptName}${sceneId ? `-${sceneId}` : ''}.mp4`);

const server = await createServer({ server: { port: 5173, strictPort: false }, logLevel: 'error' });
await server.listen();
const query = new URLSearchParams({ script: scriptName, mode: 'auto', ...(sceneId ? { scene: sceneId } : {}) });

const frameDir = mkdtempSync(join(tmpdir(), 'scene-'));
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: ['--autoplay-policy=no-user-gesture-required', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});

try {
  const page = await browser.newPage({ viewport: SIZE });
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.error('[browser]', msg.text());
  });

  // 用真實時間載入完才接管時間。不像 record_preview.mjs 在載入前接管：整齣要載入
  // 幾十個音檔，假時鐘在載入期間跟著跑，之後每張截圖都會慢到十幾秒以上。
  // --page comic.html 可以改錄 2D 漫畫版
  await page.goto(`${server.resolvedUrls.local[0]}${values.page}?${query}`);
  await page.waitForFunction(() => window.theater?.ready || window.theater?.error, null, { timeout: 300_000 });
  const loadError = await page.evaluate(() => window.theater.error);
  if (loadError) throw new Error(`頁面載入失敗：${loadError}`);

  // 接管後假的 performance.now() 從 0 起算，比 TalkingHead 記下的真實時間小，
  // 動畫時鐘會停住；先把假時間快轉到真實時間之後
  const realPerf = await page.evaluate(() => performance.now());
  await page.clock.install();
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + FRAME_MS);
  await page.clock.fastForward(Math.ceil(realPerf) + 1000);
  await page.evaluate(() => document.getElementById('play').click());
  const t0 = await page.evaluate(() => window.theater.startedAt);

  const frames = [];
  const began = Date.now();
  while (!(await page.evaluate(() => window.theater.done))) {
    await page.clock.runFor(FRAME_MS);
    const t = await page.evaluate(() => Date.now());
    const file = join(frameDir, `${String(frames.length).padStart(6, '0')}.jpg`);
    await page.screenshot({ path: file, type: 'jpeg', quality: 90 });
    frames.push({ t, file });
    if (frames.length % (FPS * 10) === 0) {
      const sec = Math.round((Date.now() - began) / 1000);
      console.log(`已算 ${frames.length / FPS} 秒（花了 ${sec} 秒）`);
    }
  }
  const { lines, lineSync } = await page.evaluate(() => window.theater);
  const total = (frames.at(-1).t - t0) / 1000;

  const list = [];
  for (let i = 0; i < Math.floor(total * FPS); i++) {
    const t = t0 + i * FRAME_MS;
    const frame = frames.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
    list.push(`file '${frame.file}'`, `duration ${(1 / FPS).toFixed(4)}`);
  }
  const listPath = join(frameDir, 'frames.txt');
  writeFileSync(listPath, list.join('\n') + '\n');

  // 每句音訊放在 (第二個字出現的時間 − 該字在音檔裡的時間)
  const inputs = [];
  const filters = [];
  lines.forEach((ln, i) => {
    if (lineSync[i] == null || ln.syncWordStart == null) {
      console.warn(`略過 ${ln.id}：沒有對時資料`);
      return;
    }
    const delay = Math.max(0, Math.round(lineSync[i] - t0 - ln.syncWordStart * 1000));
    const k = inputs.length / 2 + 1;
    inputs.push('-i', ln.audio);
    filters.push(`[${k}:a]adelay=${delay}|${delay}[a${k}]`);
  });
  const n = inputs.length / 2;
  const mix = `${filters.join(';')};${Array.from({ length: n }, (_, i) => `[a${i + 1}]`).join('')}amix=inputs=${n}:normalize=0:duration=longest[aout]`;

  execFileSync('ffmpeg', [
    '-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'concat', '-safe', '0', '-i', listPath,
    ...inputs,
    '-filter_complex', mix,
    '-map', '0:v', '-map', '[aout]',
    '-t', total.toFixed(2),
    '-vf', `fps=${FPS},format=yuv420p`,
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
    '-c:a', 'aac', '-b:a', '128k',
    '-movflags', '+faststart',
    output,
  ]);  // prettier-ignore
  console.log(`已輸出 ${output}（${total.toFixed(1)} 秒、${n} 句）`);
} finally {
  await browser.close();
  await server.close();
  rmSync(frameDir, { recursive: true, force: true });
}
