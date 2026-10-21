# 第三方授權

核對日期：2026-10-21。版本以 `package-lock.json` 與實際安裝為準，升級後請回來改這份。

## 前端（npm）

| 套件 | 版本 | 授權 | 用途 | 備註 |
|---|---|---|---|---|
| `@met4citizen/talkinghead` | 1.7.0 | MIT（Copyright (c) 2023-2024 Mika Suominen） | 3D 角色、對嘴、表情 | 授權全文在 `node_modules/@met4citizen/talkinghead/LICENSE`。散布時要附上版權聲明與授權全文。 |
| `three` | 0.180.0 | MIT | WebGL 算圖 | 版本釘在 TalkingHead 相依的 `^0.180.0`，避免裝出兩份 three |
| `vite` | 8.3.5 | MIT | 開發伺服器、打包 | dev 依賴 |
| `playwright` | 1.56.1 | Apache-2.0 | 無頭瀏覽器錄預覽 | dev 依賴；版本見下方「環境備註」 |

TalkingHead 的 npm 套件只含程式碼（`modules/`），**不含**範例角色、動畫或其他素材。

## 角色與素材

| 素材 | 來源 | 授權 | 限制 |
|---|---|---|---|
| `public/avatars/brunette.glb` | [TalkingHead repo](https://github.com/met4citizen/TalkingHead/tree/main/avatars)，由 Ready Player Me 製作 | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) | **只能非商業使用**，要標示出處。商業用途要另外註冊 Ready Player Me 開發者。檔案不進版控，用 `scripts/fetch_avatar.sh` 下載。 |
| `assets/audio/test/raw/test_line.wav` | 本專案用 eSpeak NG 1.51 合成，再混入粉紅噪音 | 本專案自產 | eSpeak NG 程式本身是 GPL-3.0，但它合成出來的音訊不受 GPL 約束；我們沒有散布 eSpeak NG。 |

TalkingHead README 提到的其他素材（Mixamo 動畫 `walking.fbx`、`dance.fbx`）本專案沒有使用。Mixamo 的原始動畫檔不能散布到專案團隊以外，之後若要用要注意。

## 音訊處理（Python，`scripts/prep_audio.py`）

以 PEP 723 內嵌依賴，`uv run` 時安裝。

| 套件或模型 | 版本 | 授權 |
|---|---|---|
| `faster-whisper` | 1.2.1 | MIT |
| `ctranslate2` | 4.8.3 | MIT |
| `onnxruntime` | 1.31.0 | MIT |
| `tokenizers` | 0.23.3 | Apache-2.0 |
| `huggingface_hub` | 2.2.0 | Apache-2.0 |
| `av`（faster-whisper 的相依；腳本不使用它解碼） | 19.0.2 | BSD-3-Clause |
| `numpy` | 2.5.4 | BSD-3-Clause 等 |
| 模型 `mobiuslabsgmbh/faster-whisper-large-v3-turbo`（預設） | 首次執行時從 Hugging Face 下載，約 1.6 GB | 原模型 `openai/whisper-large-v3-turbo` 為 MIT；轉換版的模型卡授權欄位未能自動查到，待人工確認 |
| 模型 `Systran/faster-whisper-small`（`--model small`） | 同上 | MIT（由 OpenAI Whisper small 轉換，原模型為 MIT） |

## 複製聲音（`scripts/clone_voice.py`，選用）

| 套件或模型 | 授權 | 備註 |
|---|---|---|
| `f5-tts` 1.1.22（程式碼） | MIT | |
| 模型權重 `SWivid/F5-TTS`（F5TTS_v1_Base） | **CC BY-NC 4.0** | 只能非商業使用 |
| 聲碼器 `charactr/vocos-mel-24khz` | MIT | |
| PyTorch | BSD-3-Clause | |

## 系統工具（不隨專案散布）

| 工具 | 授權 | 備註 |
|---|---|---|
| FFmpeg 6.1 | LGPL-2.1+ 或 GPL（依編譯選項，Ubuntu 套件含 GPL 元件） | 只在本機呼叫，不打包進產品；變聲用到其中的 rubberband（GPL-2.0+） |
| eSpeak NG 1.51 | GPL-3.0 | 只用來產生測試台詞 |

## 環境備註

雲端容器預裝的 Chromium 是 Playwright 1.56.1 對應的版本（chromium-1194、ffmpeg-1011），所以 `playwright` 釘在 1.56.1。在自己的機器上第一次使用要先跑 `npx playwright install chromium`。
