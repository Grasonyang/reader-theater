# 用自己的聲音演出：變聲與複製聲音

兩種做法都從同一份已對齊的劇本（`assets/scripts/<名稱>.json`，台詞要有 `audio`、`timestamps`）出發，輸出另一份劇本給網頁演出。

| | A. 變聲（一人分飾多角） | B. 複製聲音（語音合成） |
|---|---|---|
| 腳本 | `scripts/role_voices.py` | `scripts/clone_voice.py`（一鍵：`scripts/spark_clone.sh`） |
| 聲音 | 你的錄音，依角色改音高與共振峰 | F5-TTS 以你的錄音為參考，照劇本文字重新合成 |
| 發音 | 你自己的 | 模型的，接近母語者 |
| 硬體 | CPU，幾秒鐘 | 建議 NVIDIA GPU；CPU 一句要一到數分鐘 |
| 輸出劇本 | `<名稱>-voices.json` | `<名稱>-clone.json` |

網頁演出：`?script=<輸出劇本名稱>`，算成影片：`node scripts/record_scene.mjs <輸出劇本名稱> -o <檔名>.mp4`。

## A. 變聲

在劇本的 `characters[].voice` 設定每個角色（單位都是半音，沒設定就不變）：

```json
{ "id": "coach-lee", "name": "Coach Lee", "voice": { "pitch": -3, "formant": -1.5 } }
```

- `pitch`：音高。+12 是高八度。
- `formant`：共振峰，決定聽起來像大人或小孩、男或女。只升音高不動共振峰會像用假音；兩者一起大幅上升會像花栗鼠。經驗值：共振峰約為音高的一半。

```bash
uv run scripts/role_voices.py assets/scripts/missing-duck.json
```

長度不變，所以逐字時間戳沿用原本的。

## B. 複製聲音（DGX Spark）

### 準備
1. 取得程式：`git clone` 本 repo 並切到開發分支，或在既有目錄 `git pull`。原始錄音已在 `assets/audio/voice/missing-duck/raw/`。
2. 需要 `ffmpeg`、`uv`（`curl -LsSf https://astral.sh/uv/install.sh | sh`）。

### 執行
```bash
scripts/spark_clone.sh
```

它會先確認 PyTorch 看得到 GPU，接著清晰化、對齊你的錄音（產生參考音檔），再合成整齣並對齊成 `assets/scripts/missing-duck-clone.json`。只想試一兩句：

```bash
uv run --python 3.12 scripts/clone_voice.py assets/scripts/missing-duck.json --only s3-l22,s4-l36
```

### 參考音檔怎麼挑
每個角色從自己已對齊的台詞挑一句：4 到 11 秒（F5-TTS 會截掉超過 12 秒的部分，截掉後參考文字就對不上）、念錯的字最少、最長。挑不到的角色用旁白的。所以你替各角色做的語氣差別，也會被複製到合成結果。

### PyTorch 看不到 GPU 時
DGX Spark 是 ARM（aarch64）加 Blackwell GPU。`uv` 從 PyPI 裝到的 PyTorch 若沒有 CUDA，改在 NVIDIA 的 NGC PyTorch 容器裡跑（版本選最新的）：

```bash
docker run --gpus all -it --rm -v "$PWD":/work -w /work nvcr.io/nvidia/pytorch:<最新版本>-py3 bash
apt-get update && apt-get install -y ffmpeg
pip install f5-tts soundfile
python scripts/clone_voice.py assets/scripts/missing-duck.json
```

容器裡用的是容器自帶的 PyTorch，不經過 `uv run`。

### 狀態
- 在雲端容器以 CPU 實測過兩句（`s3-l22`、`s4-l36`）：可以執行，Whisper 聽寫完全正確。
- **尚未在 DGX Spark 上實測**；aarch64 上 `f5-tts` 的相依套件（`torchcodec`、`bitsandbytes`）若安裝失敗，請改用上面的容器做法。

## 授權

F5-TTS 程式碼是 MIT，但預訓練模型權重是 CC BY-NC 4.0，只能非商業使用。詳見 `docs/licenses.md`。合成語音若要用在比賽或公開場合，先確認規則允不允許。
