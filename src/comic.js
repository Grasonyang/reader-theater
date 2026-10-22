// 2D 漫畫版演出：背景一張圖，角色站成一排，講者亮起、微微彈動，旁邊出現對話氣泡；
// 旁白用說明框。動畫全部在 requestAnimationFrame 裡用時間算，record_scene.mjs
// 凍住時間逐格截圖時才會一致。
//
// 兩種模式（?mode=）：
//   click（預設）：點畫面或按空白鍵唸下一句，像視覺小說
//   auto：照時間表自動演完，錄影用
import { BASE, fromRoot, loadScript, SYNC_WORD_INDEX } from './script-player.js';

const W = 1280;
const H = 720;
const DIM = 0.45;
const BOUNCE_MS = 160;
const BOUNCE_PX = 10;
const FADE_MS = 600;
const TITLE_MS = 1800;
const INTRO_S = 5.0;
const OUTRO_S = 6.0;
const AUTO_TIMING = { firstLineAt: INTRO_S, lineGap: 1.0, sceneGap: 4.0 };
const SHOUT = new Set(['fear', 'angry']);
const DEFAULT_SCRIPT = 'missing-duck-voices';

const params = new URLSearchParams(location.search);
const scriptName = params.get('script') ?? DEFAULT_SCRIPT;
const sceneId = params.get('scene');
const autoMode = params.get('mode') === 'auto';

const $ = (id) => document.getElementById(id);
const playButton = $('play');
const bubble = $('bubble');
const bubbleText = $('bubble-text');
const caption = $('caption');
const nametag = $('nametag');
const titleCard = $('title-card');
const intro = $('intro');
const hint = $('hint');
const loading = $('loading');
const loadingText = $('loading-text');
const prevButton = $('prev');
const nextButton = $('next');
const bgs = [$('bg-a'), $('bg-b')];

window.theater = { ready: false, speaking: false, done: false, error: null };

function fit() {
  const s = Math.min(innerWidth / W, innerHeight / H);
  document.documentElement.style.setProperty('--fit', s);
}
addEventListener('resize', fit);
fit();

const now = () => performance.now();

async function main() {
  const audioCtx = new AudioContext();
  const onProgress = (n, total) => {
    loadingText.textContent = `載入台詞 ${n} / ${total}`;
  };
  const show = await loadScript(audioCtx, scriptName, sceneId, {
    ...(autoMode ? AUTO_TIMING : {}),
    onProgress,
  });
  loadingText.textContent = '載入圖片…';
  const script = await fetch(fromRoot(`assets/scripts/${scriptName}.json`)).then((r) => r.json());
  const backgrounds = script.backgrounds ?? {};

  // 角色圖（與背景一起平行載入）
  const actors = new Map();
  const roles = script.characters.filter((c) => c.comic?.image);
  const images = await Promise.all(
    roles.map(async (c) => {
      const img = new Image();
      img.src = fromRoot(c.comic.image);
      await img.decode();
      return img;
    }),
  );
  for (const [k, c] of roles.entries()) {
    const el = document.createElement('div');
    el.className = 'actor';
    el.append(images[k]);
    el.style.height = `${Math.round((c.comic.height ?? 0.7) * H)}px`;
    el.style.left = `${Math.round(c.comic.x * W)}px`;
    el.style.transform = 'translateX(-50%)';
    $('cast').append(el);
    actors.set(c.id, {
      el,
      x: c.comic.x,
      name: c.name,
      brightness: 1,
      scale: 1,
      wantBright: 1,
      wantScale: 1,
      lastWord: -1e9,
    });
  }

  // 背景：兩層交叉淡入淡出
  let bgIndex = 0;
  let bgFadeAt = -1e9;
  let currentBg = null;
  const setBackground = (sceneKey) => {
    const src = backgrounds[sceneKey];
    if (!src || src === currentBg) return;
    currentBg = src;
    bgIndex ^= 1;
    bgs[bgIndex].style.backgroundImage = `url(${fromRoot(src)})`;
    bgFadeAt = now();
  };
  await Promise.all(
    Object.values(backgrounds).map((src) => {
      const img = new Image();
      img.src = fromRoot(src);
      return img.decode().catch(() => {});
    }),
  );
  const firstScene = show.items[0].scene.id;
  bgs[0].style.backgroundImage = `url(${fromRoot(backgrounds[firstScene] ?? '')})`;
  bgs[0].style.opacity = 1;
  currentBg = backgrounds[firstScene] ?? null;

  // 片頭：劇名與角色表
  intro.innerHTML = `
    <div class="intro-title">${show.title}</div>
    <div class="intro-sub">A Reader's Theater</div>
    <div class="intro-cast">${[...actors.values()].map((a) => `<span>${a.name}</span>`).join('')}</div>`;

  let titleAt = -1e9;
  const showTitle = (scene) => {
    titleCard.textContent = `Scene ${scene.id.replace(/^s/, '')} · ${scene.title}`;
    titleAt = now();
  };

  // 氣泡放在講者旁邊：講者在左半邊就放右邊，反之放左邊
  const placeBubble = (speakerId) => {
    const a = actors.get(speakerId);
    bubble.classList.remove('tail-left', 'tail-right');
    bubble.style.left = bubble.style.right = nametag.style.left = nametag.style.right = '';
    if (!a) {
      bubble.style.left = `${W / 2 - 220}px`;
      bubble.style.top = '80px';
      bubble.classList.add('tail-left');
      nametag.style.left = bubble.style.left;
      nametag.style.top = '32px';
      return;
    }
    const top = Math.max(36, H - parseInt(a.el.style.height) - 170);
    bubble.style.top = `${top}px`;
    nametag.style.top = `${top - 46}px`;
    if (a.x < 0.5) {
      bubble.style.left = nametag.style.left = `${Math.round(a.x * W) + 30}px`;
      bubble.classList.add('tail-left');
    } else {
      bubble.style.right = nametag.style.right = `${W - Math.round(a.x * W) + 30}px`;
      bubble.classList.add('tail-right');
    }
  };

  let timers = [];
  let source = null;
  let currentScene = null;
  const clearLine = () => {
    for (const t of timers) clearTimeout(t);
    timers = [];
    try {
      source?.stop();
    } catch {
      /* 已經停了 */
    }
    source = null;
  };

  const startLine = (item, index) => {
    clearLine();
    const { line } = item;
    if (item.scene !== currentScene) {
      currentScene = item.scene;
      setBackground(item.scene.id);
      showTitle(item.scene);
    }
    const isNarrator = !actors.has(line.speaker) && line.speaker !== 'all';
    for (const [id, a] of actors) {
      const lit = line.speaker === 'all' || id === line.speaker || isNarrator;
      a.wantBright = lit ? 1 : DIM;
      a.wantScale = id === line.speaker ? 1.04 : lit ? 1 : 0.96;
    }
    caption.classList.toggle('hidden', !isNarrator);
    bubble.classList.toggle('hidden', isNarrator);
    nametag.classList.toggle('hidden', isNarrator);
    if (isNarrator) {
      caption.textContent = '';
    } else {
      bubbleText.textContent = '';
      bubble.classList.toggle('shout', SHOUT.has(line.emotion) || /!$/.test(line.text));
      nametag.textContent = item.speaker;
      placeBubble(line.speaker);
    }

    source = audioCtx.createBufferSource();
    source.buffer = item.audio;
    source.connect(audioCtx.destination);
    source.start();

    // 逐字：字幕、彈動、對時
    const target = isNarrator ? caption : bubbleText;
    item.words.forEach((w, n) => {
      timers.push(
        setTimeout(() => {
          target.textContent += (n ? ' ' : '') + w.word;
          if (n === SYNC_WORD_INDEX) window.theater.lineSync[index] = Date.now();
          const t = now();
          for (const [id, a] of actors) {
            if (line.speaker === 'all' || id === line.speaker) a.lastWord = t;
          }
        }, w.start * 1000),
      );
    });
  };

  const finish = () => {
    clearLine();
    bubble.classList.add('hidden');
    nametag.classList.add('hidden');
    caption.classList.add('hidden');
    for (const a of actors.values()) {
      a.wantBright = 1;
      a.wantScale = 1;
    }
    intro.innerHTML = `<div class="intro-title">The End</div>
      <div class="intro-sub">${show.title}</div>
      <div class="intro-cast">${[...actors.values()].map((a) => `<span>${a.name}</span>`).join('')}</div>`;
    intro.classList.remove('hidden');
    hint.classList.add('hidden');
    window.theater.speaking = false;
    // 自動模式由 startAuto 在片尾卡顯示完才標記 done（錄影要錄到片尾）
    if (!autoMode) window.theater.done = true;
  };

  // 動畫迴圈：亮度、縮放、彈動、背景淡入、標題
  const tick = () => {
    const t = now();
    for (const a of actors.values()) {
      a.brightness += (a.wantBright - a.brightness) * 0.18;
      a.scale += (a.wantScale - a.scale) * 0.18;
      const dt = t - a.lastWord;
      const bounce = dt < BOUNCE_MS ? Math.sin((dt / BOUNCE_MS) * Math.PI) * BOUNCE_PX : 0;
      a.el.style.transform = `translateX(-50%) translateY(${-bounce}px) scale(${a.scale})`;
      a.el.style.filter = `brightness(${a.brightness})`;
      a.el.style.zIndex = a.wantBright === 1 ? 2 : 1;
    }
    const f = Math.min(1, (t - bgFadeAt) / FADE_MS);
    bgs[bgIndex].style.opacity = f;
    bgs[bgIndex ^ 1].style.opacity = 1 - f;
    const tt = t - titleAt;
    const titleOpacity =
      tt < 0 ? 0 : tt < 300 ? tt / 300 : tt < TITLE_MS ? 1 : Math.max(0, 1 - (tt - TITLE_MS) / 400);
    titleCard.style.opacity = titleOpacity;
    titleCard.classList.toggle('hidden', titleOpacity <= 0);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);

  window.theater.lineSync = [];
  window.theater.lines = show.items.map((it) => ({
    id: it.line.id,
    audio: it.line.audio,
    syncWordStart: it.words[SYNC_WORD_INDEX]?.start ?? null,
  }));

  // 自動模式：照時間表
  const startAuto = () => {
    window.theater.startedAt = Date.now();
    setTimeout(() => intro.classList.add('hidden'), (INTRO_S - 0.6) * 1000);
    for (const [index, item] of show.items.entries()) {
      setTimeout(() => startLine(item, index), item.at * 1000);
    }
    setTimeout(finish, show.end * 1000);
    setTimeout(() => {
      window.theater.done = true;
    }, (show.end + OUTRO_S) * 1000);
  };

  // 點按模式：點畫面或「下一句」唸下一句，「上一句」回頭重聽
  let cursor = -1;
  const go = (index) => {
    if (index >= show.items.length) return finish();
    cursor = Math.max(0, index);
    intro.classList.add('hidden');
    hint.textContent = `${cursor + 1} / ${show.items.length} · 點一下繼續 ▸`;
    prevButton.disabled = cursor === 0;
    nextButton.textContent = cursor === show.items.length - 1 ? '結束 ▶' : '下一句 ▶';
    startLine(show.items[cursor], cursor);
  };
  const next = () => go(cursor + 1);
  const prev = () => go(cursor - 1);

  const start = async () => {
    playButton.hidden = true;
    await audioCtx.resume();
    window.theater.speaking = true;
    // 場次標題由第一句觸發（startLine 看到換場才顯示），不跟片頭疊在一起
    if (autoMode) return startAuto();
    hint.classList.remove('hidden');
    hint.textContent = '點一下開始 ▸';
    prevButton.classList.remove('hidden');
    nextButton.classList.remove('hidden');
    prevButton.disabled = true;
    $('stage').addEventListener('click', next);
    nextButton.addEventListener('click', next);
    prevButton.addEventListener('click', prev);
    addEventListener('keydown', (e) => {
      if (e.code === 'Space' || e.code === 'Enter' || e.code === 'ArrowRight') {
        e.preventDefault();
        next();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        prev();
      }
    });
  };

  document.title = `${show.title} – Reader Theater`;
  loading.classList.add('hidden');
  playButton.textContent = autoMode ? '開始演出' : '開始';
  playButton.disabled = false;
  playButton.addEventListener('click', start);
  window.theater.ready = true;
}

main().catch((err) => {
  console.error(err);
  window.theater.error = String(err);
  loadingText.textContent = `載入失敗：${err.message ?? err}`;
  playButton.textContent = '載入失敗';
});

export { BASE };
