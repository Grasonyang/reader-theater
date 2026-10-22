# 原稿與素材：在哪裡、怎麼取得

下一階段（Three.js 角色建構、改用 GPT 產生語音）要用到的東西都在這裡列出位置、格式與重建方式。路徑都相對於 repo 根目錄。

## 一覽

| 素材 | 位置 | 進版控 | 怎麼取得或重建 |
|---|---|---|---|
| 劇本原稿 | `assets/scripts/missing-duck.json` | 是 | 直接讀；格式見 `docs/script-schema.md` |
| 原始錄音（你的聲音） | `assets/audio/voice/missing-duck/raw/scene1~4.m4a` | 是 | 直接讀 |
| 每句音訊與時間戳（原聲） | `assets/audio/voice/missing-duck/lines/` | 否 | `scripts/prep_scenes.sh missing-duck` |
| 變聲版（A） | `assets/audio/voice/missing-duck/lines/voices/`、`assets/scripts/missing-duck-voices.json` | 否 | 先重建上一列，再 `uv run scripts/role_voices.py assets/scripts/missing-duck.json` |
| 複製聲音版（B）合成原檔 | `assets/audio/voice/missing-duck-clone/raw/scene1~4.flac`、`assets/scripts/missing-duck-clone.json` | 是 | GPU 上 `scripts/spark_clone.sh`；每句音訊用 `scripts/prep_scenes.sh missing-duck-clone --no-clarity` 重建 |
| 對齊報告（念錯、略過的重唸） | `assets/audio/voice/<名稱>/report_s<N>.md` | 否 | 跟著 `prep_scenes.sh` 產生 |
| 角色模型（3D） | `public/avatars/brunette.glb` | 否 | `scripts/fetch_avatar.sh`（CC BY-NC 4.0） |
| 漫畫版背景（4 場） | `assets/art/backgrounds/s1~4.jpg` | 是 | AI 生成，原圖在 `assets/art/source/` |
| 漫畫版角色（去背 PNG） | `assets/art/characters/<角色 id>.png` | 是 | 由 `assets/art/source/characters-sheet.webp` 經 `scripts/cut_sheet.py` 切出 |
| 測試台詞 | `assets/audio/test/` | 是 | 見該資料夾的 README |

不進版控的檔案都能從進版控的檔案重建；clone 下來後先跑 `npm ci`、`scripts/fetch_avatar.sh`、`scripts/prep_scenes.sh missing-duck`。

## 劇本原稿

`assets/scripts/missing-duck.json` 是唯一的原稿來源，網頁、對齊、變聲、合成都從它讀。結構（細節見 `docs/script-schema.md`）：

- `characters[]`：`id`、`name`、`avatar`（GLB 路徑）、`body`、`voice`（變聲設定）
- `scenes[].lines[]`：`id`（例如 `s3-l25`）、`speaker`、`text`、`emotion`、`gesture`、`camera`，以及對齊後寫入的 `audio`、`timestamps`

只要台詞文字（例如交給 GPT 產生語音）：

```bash
python3 -c "
import json
d = json.load(open('assets/scripts/missing-duck.json'))
for s in d['scenes']:
    for l in s['lines']:
        print(l['id'], l['speaker'], l['emotion'], l['text'], sep='\t')
"
```

`all` 是全員一起說的台詞（目前只有最後一句 "Thank you!"）。

## 錄音與時間戳

`scripts/prep_scenes.sh <名稱>` 對 `assets/audio/voice/<名稱>/raw/scene<N>.*` 依序做：

1. `prep_audio.py`：清晰化與響度（-16 LUFS、48 kHz 單聲道），分窗聽寫（faster-whisper large-v3-turbo），輸出 `scene<N>.wav` 與 `scene<N>.json`（`words` 逐字時間戳、`chunks` 細分段）。合成語音加 `--no-clarity`，只調響度。
2. `align_lines.py`：把段對回劇本，切出 `lines/<台詞 id>.wav` 與 `lines/<台詞 id>.json`，並把路徑寫回劇本 JSON。

每句的 `lines/<台詞 id>.json`：

```json
{
  "audio": "s3-l25.wav",
  "source": "scene3.wav",
  "offset": 48.0,
  "duration": 9.6,
  "removed": [],
  "text": "Inside the storage room sat a little white duck. ...",
  "issues": ["「sat」聽成「set」"],
  "words": [{ "word": "Inside", "start": 0.12, "end": 0.48 }, "..."]
}
```

`words` 的字是劇本原文、時間是實際錄音（秒，相對這句的開頭），網頁直接拿來對嘴與上字幕。

## 漫畫版（2D，目前的主線）

`comic.html` + `src/comic.js`：背景一張圖、角色站成一排，講者亮起並隨每個字微彈，其他人變暗；對話用漫畫氣泡（驚恐、生氣或驚嘆句用鋸齒框），旁白用黃色說明框，換場時交叉淡入新背景並顯示場次標題。角色位置與大小在劇本 `characters[].comic`（`image`、`x`、`height`），背景在 `backgrounds`。

圖片的生成 prompt 記在 `docs/art-prompts.md`。要加嘴型，只要補一張同角色張嘴的表，切成 `<角色 id>-open.png`，再在 `comic.js` 依字的時間切換。

## Three.js 角色

目前的做法：

- `src/main.js` 建立一個 TalkingHead 實例（它內含 Three.js 場景、相機、燈光），`showAvatar()` 載入 `public/avatars/brunette.glb`。
- `src/script-player.js` 依時間表演出每句：`setMood`（情緒）、`setView`（鏡頭）、`playGesture`（手勢）、`speakAudio`（對嘴）。
- 五個角色共用同一個模型，靠畫面上的講者名稱區分。

換成每個角色各自一個模型時要準備：

- **模型格式**：GLB，Ready Player Me 相容的全身骨架（Mixamo 骨骼命名），並帶 ARKit 52 個 blend shapes 與 Oculus 15 個視素（viseme）blend shapes。少了視素就無法對嘴。
- **取得管道**：TalkingHead 範例用的是 Ready Player Me；其他來源（Avaturn、Avatar SDK MetaPerson、自己在 Blender 做）要用 TalkingHead repo 的 `blender/` 腳本改骨骼名稱或補 blend shapes。各服務目前是否仍開放、授權條件為何，使用前要再確認，並記到 `docs/licenses.md`。
- **放哪裡**：`public/avatars/<角色 id>.glb`，劇本 `characters[].avatar` 改成對應路徑。
- **多個角色同台**：TalkingHead 的 `avatarOnly` 模式（README 的 Appendix H）可以把多個角色放進同一個 Three.js 場景，各自 `animate()`；`script-player.js` 要改成依 `speaker` 找對應的實例。

## 改用 GPT 產生語音

目標：用 OpenAI 的語音合成，依劇本文字為每個角色產生台詞，再走同一套時間戳與對齊，網頁不用改。

輸入都在劇本 JSON 裡：

| 劇本欄位 | 用途 |
|---|---|
| `text` | 要唸的台詞 |
| `speaker` | 對應到一個固定的聲音（每個角色選一個 voice） |
| `emotion` | 轉成語氣指示（例如 `fear` → 「緊張、聲音發抖」） |

建議的接法，比照 `clone_voice.py`：

1. 每句呼叫一次 TTS，存下音檔；同一場的台詞依序接起來、句間留 0.8 秒，存成 `assets/audio/voice/missing-duck-gpt/raw/scene<N>.wav`。
2. 複製一份劇本、拿掉 `audio` 與 `timestamps`，存成 `assets/scripts/missing-duck-gpt.json`。
3. `scripts/prep_scenes.sh missing-duck-gpt --no-clarity`，得到每句音訊與時間戳。
4. 網頁開 `?script=missing-duck-gpt`，或 `node scripts/record_scene.mjs missing-duck-gpt`。

要注意：

- **API 金鑰**：放在環境變數 `OPENAI_API_KEY`，不要寫進程式或 commit。雲端環境要在環境設定的 secrets 加上。
- **模型與聲音**：撰寫時可用的是支援語氣指示（`instructions`）的語音模型（例如 `gpt-4o-mini-tts`）與一組內建聲音；型號、聲音清單與價格會變，動手前查 OpenAI 的官方文件。
- **使用規範**：OpenAI 的條款要求讓聽眾知道聲音是 AI 產生的；作品若公開或參賽，片頭片尾要註明，也要先確認比賽規則允不允許合成語音。
- **來源記錄**：產生的音檔記下模型名稱、聲音、日期，寫進 `docs/licenses.md`。

## 已知的待辦

- `s2-l14` 的 "Clues, Ben." 錄音裡沒有，需要補錄這一句。
- 整齣目前約 3 分 54 秒；要到 5 分鐘需要拉長句間停頓、加場次標題，或增加台詞。
