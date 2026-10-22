import { TalkingHead } from '@met4citizen/talkinghead';
import { LipsyncEn } from '@met4citizen/talkinghead/modules/lipsync-en.mjs';
import audioUrl from '../assets/audio/test/test_line.wav?url';
import timestamps from '../assets/audio/test/test_line.json';
import { loadScript, play, SYNC_WORD_INDEX as SCRIPT_SYNC_WORD_INDEX } from './script-player.js';
import { blocking, buildStage, dress, place } from './stage.js';
import { fromRoot } from './script-player.js';

const playButton = document.getElementById('play');
const subtitles = document.getElementById('subtitles');
const speaker = document.getElementById('speaker');
const sceneTitle = document.getElementById('scene-title');
const avatarNode = document.getElementById('avatar');

// ?script=<名稱>[&scene=<場次 id>]：演 assets/scripts/<名稱>.json；沒給就播測試台詞
const params = new URLSearchParams(location.search);
const scriptName = params.get('script');
const sceneId = params.get('scene');

// 讓 Playwright 讀取進度
window.theater = { ready: false, speaking: false, done: false, error: null };

// 把 prep_audio.py 的逐字時間戳（秒）轉成 speakAudio 要的格式（毫秒）
function toSpeakAudioWords(json) {
  return {
    words: json.words.map((w) => w.word),
    wtimes: json.words.map((w) => Math.round(w.start * 1000)),
    wdurations: json.words.map((w) => Math.round((w.end - w.start) * 1000)),
  };
}

// 錄影對時用：講到第 SYNC_WORD_INDEX 個字（從 0 起算）時記下時間，
// record_preview.mjs 由此扣掉該字的時間戳，回推音訊起點
const SYNC_WORD_INDEX = 1;

async function main() {
  if (scriptName) return setupScript();

  const head = new TalkingHead(avatarNode, {
    // lipsync 模組改成自己 import：套件預設用相對路徑動態載入，經過 Vite 打包會找不到
    lipsyncModules: [],
    cameraView: 'upper',
  });
  head.lipsync.en = new LipsyncEn();

  await head.showAvatar({
    url: fromRoot('avatars/brunette.glb'),
    body: 'F',
    avatarMood: 'neutral',
    lipsyncLang: 'en',
  });

  const response = await fetch(audioUrl);
  const audio = await head.audioCtx.decodeAudioData(await response.arrayBuffer());
  const line = { audio, ...toSpeakAudioWords(timestamps) };

  const speak = async () => {
    await head.audioCtx.resume();
    subtitles.textContent = '';
    window.theater.speaking = true;
    let spoken = 0;
    head.speakAudio(line, { lipsyncLang: 'en' }, (word) => {
      subtitles.textContent += word;
      spoken += 1;
      // 第一個字的事件會延遲觸發，改用第二個字對時
      if (spoken === SYNC_WORD_INDEX + 1) window.theater.syncAt = Date.now();
    });
    head.speakMarker(() => {
      window.theater.speaking = false;
      window.theater.done = true;
    });
  };

  playButton.textContent = '播放台詞';
  playButton.disabled = false;
  playButton.addEventListener('click', speak);
  window.theater.ready = true;
}

// 劇本模式：舞台上每個角色一個 TalkingHead。第一個角色（旁白）是主實例，持有 Three.js
// 場景、鏡頭與渲染器；其他角色用 avatarOnly 模式加進同一個場景，由主實例的 update 驅動
async function setupScript() {
  const res = await fetch(fromRoot(`assets/scripts/${scriptName}.json`));
  if (!res.ok) throw new Error(`讀不到劇本 ${scriptName}（${res.status}）`);
  const script = await res.json();
  const roles = script.characters.filter((c) => c.id !== 'all');
  const spots = blocking(script.characters);

  const cast = new Map();
  const others = [];
  let director = null;
  const avatarFor = (c) => ({
    url: fromRoot(c.avatar),
    body: c.body ?? 'F',
    avatarMood: 'neutral',
    lipsyncLang: 'en',
  });

  const host = new TalkingHead(avatarNode, {
    lipsyncModules: [],
    cameraView: 'full',
    update: (dt) => {
      for (const h of others) h.animate(dt);
      director?.update(dt);
    },
  });
  host.lipsync.en = new LipsyncEn();
  await host.showAvatar(avatarFor(roles[0]));
  cast.set(roles[0].id, host);

  for (const c of roles.slice(1)) {
    const h = new TalkingHead(avatarNode, {
      lipsyncModules: [],
      avatarOnly: true,
      avatarOnlyScene: host.scene,
      avatarOnlyCamera: host.camera,
    });
    h.lipsync.en = new LipsyncEn();
    await h.showAvatar(avatarFor(c));
    cast.set(c.id, h);
    others.push(h);
  }
  for (const c of roles) {
    dress(cast.get(c.id), c.look);
    place(cast.get(c.id), spots[c.id]);
  }
  director = buildStage(host, spots);
  director.shot('full');

  const show = await loadScript(host.audioCtx, scriptName, sceneId);
  window.theater.lineSync = [];
  window.theater.lines = show.items.map((it) => ({
    id: it.line.id,
    audio: it.line.audio,
    syncWordStart: it.words[SCRIPT_SYNC_WORD_INDEX]?.start ?? null,
  }));

  let currentScene = null;
  const showSceneTitle = (scene) => {
    sceneTitle.textContent = `Scene ${scene.id.replace(/^s/, '')} · ${scene.title}`;
    sceneTitle.classList.add('visible');
    setTimeout(() => sceneTitle.classList.remove('visible'), 2500);
  };

  const start = async () => {
    playButton.hidden = true;
    await Promise.all([...cast.values()].map((h) => h.audioCtx.resume()));
    window.theater.speaking = true;
    window.theater.startedAt = Date.now();
    play(cast, director, show, {
      onLine: (item) => {
        if (item.scene !== currentScene) {
          currentScene = item.scene;
          showSceneTitle(item.scene);
        }
        speaker.textContent = item.speaker;
        subtitles.textContent = '';
      },
      onWord: (index, n, word) => {
        subtitles.textContent += word;
        if (n === SCRIPT_SYNC_WORD_INDEX) window.theater.lineSync[index] = Date.now();
      },
      onDone: () => {
        window.theater.speaking = false;
        window.theater.done = true;
        director.shot('full');
        director.light('all');
        playButton.hidden = false;
      },
    });
  };

  document.title = `${show.title} – Reader Theater`;
  playButton.textContent = '開始演出';
  playButton.disabled = false;
  playButton.addEventListener('click', start);
  window.theater.ready = true;
}

main().catch((err) => {
  console.error(err);
  window.theater.error = String(err);
  playButton.textContent = '載入失敗';
});
