// 依劇本 JSON（docs/script-schema.md）依序演出台詞。
//
// 每句的開始時間事先排好（上一句結束後停 LINE_GAP_S 秒），用 setTimeout 觸發，
// 不靠 TalkingHead 的語音佇列等上一句播完：佇列要等音訊的 onended，那是真實時間，
// record_scene.mjs 逐格算圖時頁面的時間被凍住，兩者會對不上。

const LINE_GAP_S = 0.6;
const FIRST_LINE_AT_S = 0.8;
// 與 record_scene.mjs 一致：第一個字的事件會延遲觸發，用第二個字對時
export const SYNC_WORD_INDEX = 1;

// 劇本裡的路徑相對於專案根目錄，dev server 直接提供
const fromRoot = (path) => `/${path.replace(/^\/+/, '')}`;

async function fetchJson(path) {
  const res = await fetch(fromRoot(path));
  if (!res.ok) throw new Error(`讀不到 ${path}（${res.status}）`);
  return res.json();
}

// 載入劇本與每句音訊，排好時間表。sceneId 省略時演整齣
export async function loadScript(audioCtx, name, sceneId) {
  const script = await fetchJson(`assets/scripts/${name}.json`);
  const characters = Object.fromEntries(script.characters.map((c) => [c.id, c]));
  const scenes = sceneId ? script.scenes.filter((s) => s.id === sceneId) : script.scenes;
  if (!scenes.length) throw new Error(`劇本裡沒有場次 ${sceneId}`);

  const items = [];
  let at = FIRST_LINE_AT_S;
  let camera = 'upper';
  for (const scene of scenes) {
    for (const line of scene.lines) {
      if (!line.audio || !line.timestamps) continue;
      const [buf, stamps] = await Promise.all([
        fetch(fromRoot(line.audio)).then((r) => r.arrayBuffer()),
        fetchJson(line.timestamps),
      ]);
      const audio = await audioCtx.decodeAudioData(buf);
      camera = line.camera?.view ?? camera;
      items.push({
        line,
        scene,
        speaker: characters[line.speaker]?.name ?? line.speaker,
        camera,
        audio,
        words: stamps.words,
        at,
      });
      at += audio.duration + LINE_GAP_S;
    }
  }
  if (!items.length) throw new Error('這一場沒有任何已對齊的台詞（先跑 scripts/align_lines.py）');
  return { title: script.title, items, end: at };
}

// 演出。cast 是角色 id → TalkingHead 實例；director 是 stage.js 的鏡頭與燈光（可省略）。
// 講者是 "all" 時，第一個角色放出聲音，其他人用等長的靜音一起對嘴。
// onLine(item) 在每句開始時呼叫，onWord(index, n, word) 在每個字出現時呼叫
export function play(cast, director, show, { onLine, onWord, onDone }) {
  const everyone = [...cast.values()];
  for (const [index, item] of show.items.entries()) {
    setTimeout(() => {
      const { line } = item;
      const speakers = line.speaker === 'all' ? everyone : [cast.get(line.speaker) ?? everyone[0]];
      director?.shot(item.camera, line.speaker);
      director?.light(line.speaker);
      onLine?.(item, index);
      const lipsync = {
        words: item.words.map((w) => w.word),
        wtimes: item.words.map((w) => Math.round(w.start * 1000)),
        wdurations: item.words.map((w) => Math.round((w.end - w.start) * 1000)),
      };
      speakers.forEach((head, k) => {
        head.setMood(line.emotion ?? 'neutral');
        if (!director) head.setView(item.camera);
        const audio =
          k === 0
            ? item.audio
            : head.audioCtx.createBuffer(1, item.audio.length, item.audio.sampleRate);
        let spoken = 0;
        head.speakAudio(
          { audio, ...lipsync },
          { lipsyncLang: 'en' },
          k === 0 ? (word) => onWord?.(index, spoken++, word) : null,
        );
        const g = line.gesture;
        if (g) {
          setTimeout(
            () => head.playGesture(g.name, g.duration ?? 2, g.mirror ?? false),
            (g.at ?? 0) * 1000,
          );
        }
      });
    }, item.at * 1000);
  }
  setTimeout(() => onDone?.(), show.end * 1000);
}
