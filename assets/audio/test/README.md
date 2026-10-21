# 測試台詞

| 檔案 | 說明 |
|---|---|
| `raw/test_line.wav` | 原始輸入：eSpeak NG 合成，混入粉紅噪音，44.1 kHz 立體聲 |
| `test_line.wav` | `scripts/prep_audio.py` 的輸出：降噪、-16 LUFS、48 kHz 單聲道 |
| `test_line.json` | 同上，faster-whisper small 的逐字時間戳 |

重新產生原始檔：

```bash
espeak-ng -v en-us -s 150 -w /tmp/tts.wav "To be, or not to be, that is the question. Welcome to our reader's theater."
ffmpeg -y -i /tmp/tts.wav -f lavfi -i "anoisesrc=color=pink:amplitude=0.02:sample_rate=22050" \
  -filter_complex "[0:a]apad=pad_dur=0.5,adelay=400[s];[s][1:a]amix=inputs=2:duration=first:normalize=0,volume=0.5" \
  -ac 2 -ar 44100 raw/test_line.wav
```

再處理：

```bash
uv run scripts/prep_audio.py assets/audio/test/raw/test_line.wav -o assets/audio/test/test_line.wav
```
