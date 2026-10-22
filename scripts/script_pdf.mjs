// 把劇本 JSON 排成讀者劇場講義（Reader's Theater Script）PDF。
//
// 用法：
//   node scripts/script_pdf.mjs [劇本名] [-o 輸出.pdf] [--team "成員一、成員二"] [--html]
//
// 版面仿一般英語讀者劇場講義：紫色標題橫幅、Cast / Duration / Target 資訊列、
// 角色分配表（Reader N 彩色徽章）、每場一條黃色 PART 分隔條、
// 台詞以「Reader N (角色):」開頭，情緒與手勢轉成斜體的舞台提示。
// 用 Playwright 的 Chromium 印成 A4 PDF；--html 會把中間的 HTML 也留下來。

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { chromium } from 'playwright';

const args = process.argv.slice(2);
const opt = (flag, fallback) => {
  const k = args.indexOf(flag);
  return k >= 0 ? args[k + 1] : fallback;
};
const name = args.find((a, k) => !a.startsWith('-') && !['-o', '--team'].includes(args[k - 1])) ?? 'missing-duck';
const out = resolve(opt('-o', `docs/handouts/${name}-script.pdf`));
const team = opt('--team', '');
const keepHtml = args.includes('--html');

const script = JSON.parse(await readFile(`assets/scripts/${name}.json`, 'utf8'));

// Reader 編號與顏色：依劇本 characters 的順序，all 不算一個 reader
const PALETTE = ['#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed', '#0891b2', '#db2777'];
const DESCRIPTIONS = {
  narrator: 'Tells the story and sets each scene',
  mia: 'A calm, clever student detective',
  ben: "Mia's nervous best friend",
  'coach-lee': 'The basketball coach, proud of his trophy',
  sam: "Coach Lee's young son",
};
const readers = script.characters
  .filter((c) => c.id !== 'all')
  .map((c, k) => ({
    ...c,
    n: k + 1,
    color: PALETTE[k % PALETTE.length],
    blurb: DESCRIPTIONS[c.id] ?? '',
  }));
const byId = Object.fromEntries(readers.map((r) => [r.id, r]));

// 情緒與手勢 → 舞台提示（照講義慣例放在台詞前，斜體）
const MOOD_CUE = {
  fear: 'nervously',
  angry: 'angrily',
  happy: 'happily',
  sad: 'sadly',
  love: 'gently',
  disgust: 'confused',
};
const GESTURE_CUE = {
  handup: 'raising a hand',
  index: 'pointing',
  shrug: 'shrugging',
  thumbup: 'thumbs up',
  thumbdown: 'shaking head',
  namaste: 'bowing',
  side: 'looking around',
};
function cue(line) {
  const parts = [];
  if (MOOD_CUE[line.emotion]) parts.push(MOOD_CUE[line.emotion]);
  if (GESTURE_CUE[line.gesture?.name]) parts.push(GESTURE_CUE[line.gesture.name]);
  return parts.length ? `(${parts.join(', ')})` : '';
}

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function lineHtml(line) {
  const r = byId[line.speaker];
  const label = r ? `Reader ${r.n} (${esc(r.name)}):` : 'ALL READERS:';
  const color = r ? r.color : '#111827';
  const c = cue(line);
  return `<p class="line${r ? '' : ' all'}"><span class="who" style="color:${color}">${label}</span> ${
    c ? `<em class="cue">${esc(c)}</em> ` : ''
  }${esc(line.text)}</p>`;
}

const totalLines = script.scenes.reduce((n, s) => n + s.lines.length, 0);
const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${esc(script.title)} – Reader's Theater Script</title>
<style>
  @page { size: A4; margin: 14mm 15mm 16mm; }
  html { font-family: 'Liberation Sans', 'DejaVu Sans', 'WenQuanYi Zen Hei', Arial, sans-serif; }
  body { margin: 0; color: #1f2937; font-size: 11pt; line-height: 1.4; }
  .banner {
    background: linear-gradient(135deg, #6d28d9, #8b5cf6 60%, #a78bfa);
    color: #fff; border-radius: 10px; padding: 16px 22px; text-align: center;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .banner h1 { margin: 0; font-size: 24pt; letter-spacing: 0.01em; }
  .banner .sub { margin-top: 4px; font-size: 13pt; opacity: 0.95; }
  .banner .edition { margin-top: 2px; font-size: 10.5pt; opacity: 0.9; font-style: italic; }
  .info {
    display: flex; justify-content: space-around; gap: 12px;
    margin: 10px 0 4px; padding: 8px 12px; background: #f3f0ff; border: 1px solid #ddd6fe;
    border-radius: 8px; font-size: 10.5pt;
  }
  .info b { color: #6d28d9; }
  .team {
    margin: 0 0 12px; padding: 7px 12px; text-align: center; font-size: 10.5pt;
    background: #fafafa; border: 1px dashed #d1d5db; border-radius: 8px;
    font-family: 'Liberation Sans', 'WenQuanYi Zen Hei', sans-serif;
  }
  .team b { color: #374151; margin-right: 6px; }
  .team span { margin: 0 8px; white-space: nowrap; }
  h2 { font-size: 14pt; color: #4c1d95; margin: 14px 0 6px; }
  table.cast { width: 100%; border-collapse: collapse; font-size: 10.5pt; }
  table.cast th, table.cast td { border: 1px solid #e5e7eb; padding: 4px 8px; text-align: left; }
  table.cast th { background: #ede9fe; color: #4c1d95; }
  .badge {
    display: inline-block; padding: 1px 9px; border-radius: 999px; color: #fff; font-weight: 700;
    font-size: 9.5pt; -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .part {
    margin: 16px 0 8px; padding: 6px 12px; background: #fde68a; border-left: 6px solid #f59e0b;
    border-radius: 4px; font-weight: 700; font-size: 12.5pt; color: #78350f;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
    page-break-after: avoid; break-after: avoid;
  }
  .line { margin: 0 0 5px; padding-left: 14px; text-indent: -14px; page-break-inside: avoid; break-inside: avoid; }
  .who { font-weight: 700; }
  .cue { color: #6b7280; }
  .all .who { color: #111827; }
  .tips { margin-top: 12px; page-break-inside: avoid; padding: 10px 14px; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; font-size: 10pt; }
  .tips h3 { margin: 0 0 4px; font-size: 11pt; color: #065f46; }
  .tips ul { margin: 0; padding-left: 18px; }
  .end { margin-top: 14px; text-align: center; font-weight: 700; color: #6d28d9; letter-spacing: 0.2em; }
</style>
</head>
<body>
  <div class="banner">
    <h1>${esc(script.title)}</h1>
    <div class="sub">5-Minute Reader's Theater Script</div>
    <div class="edition">Easy Vocabulary Edition</div>
  </div>
  <div class="info">
    <div><b>Cast:</b> ${readers.length} Readers</div>
    <div><b>Duration:</b> ~5 Minutes</div>
    <div><b>Target:</b> Beginner–Intermediate English</div>
    <div><b>Lines:</b> ${totalLines}</div>
  </div>
  ${
    team
      ? `<div class="team"><b>Team</b>${team
          .split(/[、,，/]/)
          .map((t) => `<span>${esc(t.trim())}</span>`)
          .join('')}</div>`
      : ''
  }

  <h2>Cast of Characters</h2>
  <table class="cast">
    <tr><th style="width:18%">Reader</th><th style="width:22%">Character</th><th>Description</th></tr>
    ${readers
      .map(
        (r) =>
          `<tr><td><span class="badge" style="background:${r.color}">Reader ${r.n}</span></td><td><b style="color:${r.color}">${esc(
            r.name,
          )}</b></td><td>${esc(r.blurb)}</td></tr>`,
      )
      .join('\n    ')}
  </table>

  ${script.scenes
    .map(
      (s, k) => `<div class="part">PART ${k + 1}: ${esc(s.title ?? s.id)}</div>
  ${s.lines.map(lineHtml).join('\n  ')}`,
    )
    .join('\n\n  ')}

  <div class="end">— THE END —</div>

  <div class="tips">
    <h3>Reading Tips</h3>
    <ul>
      <li>Readers do not memorize: read from the script, but look up at the audience when you can.</li>
      <li>The words in <em>(italics)</em> are stage cues. Do not read them aloud; act them with your voice and face.</li>
      <li>Narrator sets the mood of each part. Characters react to each other, not to the paper.</li>
      <li>Pause briefly after each PART heading so the audience knows the scene has changed.</li>
    </ul>
  </div>
</body>
</html>
`;

await mkdir(dirname(out), { recursive: true });
if (keepHtml) await writeFile(out.replace(/\.pdf$/i, '.html'), html);

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
try {
  const page = await browser.newPage();
  await page.setContent(html, { waitUntil: 'load' });
  await page.emulateMedia({ media: 'print' });
  await page.pdf({
    path: out,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate:
      '<div style="width:100%;text-align:center;font-size:8pt;color:#9ca3af;font-family:sans-serif">' +
      `${esc(script.title)} · Reader's Theater · <span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
    margin: { top: '14mm', right: '15mm', bottom: '16mm', left: '15mm' },
  });
} finally {
  await browser.close();
}
console.log(`→ ${out}`);
