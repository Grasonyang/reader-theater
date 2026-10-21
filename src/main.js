import { TalkingHead } from '@met4citizen/talkinghead';
import { LipsyncEn } from '@met4citizen/talkinghead/modules/lipsync-en.mjs';
import audioUrl from '../assets/audio/test/test_line.wav?url';
import timestamps from '../assets/audio/test/test_line.json';
import { loadScript, play, SYNC_WORD_INDEX as SCRIPT_SYNC_WORD_INDEX } from './script-player.js';

const playButton = document.getElementById('play');
const subtitles = document.getElementById('subtitles');
const speaker = document.getElementById('speaker');

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
  const head = new TalkingHead(document.getElementById('avatar'), {
    // lipsync 模組改成自己 import：套件預設用相對路徑動態載入，經過 Vite 打包會找不到
    lipsyncModules: [],
    cameraView: 'upper',
  });
  head.lipsync.en = new LipsyncEn();

  await head.showAvatar({
    url: '/avatars/brunette.glb',
    body: 'F',
    avatarMood: 'neutral',
    lipsyncLang: 'en',
  });

  if (scriptName) return setupScript(head);

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

async function setupScript(head) {
  const show = await loadScript(head.audioCtx, scriptName, sceneId);
  window.theater.lineSync = [];
  window.theater.lines = show.items.map((it) => ({
    id: it.line.id,
    audio: it.line.audio,
    syncWordStart: it.words[SCRIPT_SYNC_WORD_INDEX]?.start ?? null,
  }));

  const start = async () => {
    playButton.hidden = true;
    await head.audioCtx.resume();
    window.theater.speaking = true;
    window.theater.startedAt = Date.now();
    play(head, show, {
      onLine: (item) => {
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
