import { TalkingHead } from '@met4citizen/talkinghead';
import { LipsyncEn } from '@met4citizen/talkinghead/modules/lipsync-en.mjs';
import audioUrl from '../assets/audio/test/test_line.wav?url';
import timestamps from '../assets/audio/test/test_line.json';

const playButton = document.getElementById('play');
const subtitles = document.getElementById('subtitles');

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

main().catch((err) => {
  console.error(err);
  window.theater.error = String(err);
  playButton.textContent = '載入失敗';
});
