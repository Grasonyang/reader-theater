# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "faster-whisper>=1.1",
#     "numpy",
# ]
# ///
"""台詞音訊前處理：人聲清晰化、響度統一、逐字時間戳。

用法：
    uv run scripts/prep_audio.py <輸入音檔> [-o 輸出.wav] [--json 輸出.json]
                                 [--denoise] [--no-clarity] [--model small]

處理順序：
    1. 先把音量拉到 -23 LUFS，讓後面的濾波器與壓縮器在固定的音量下工作
       （手機錄音常常只有 -35 到 -40 LUFS）
    2. 高通去低頻嗡聲，EQ 減 300 Hz 悶聲、補 3 kHz 與高頻的咬字，
       壓縮器拉平句子之間的音量差，去齒音
    3. 線性增益加限制器，把響度調到 -16 LUFS

輸出：
    - 48 kHz、單聲道、16-bit PCM WAV，響度 -16 LUFS（EBU R128，誤差 ±0.5 LU）
    - 逐字時間戳 JSON（faster-whisper，CPU），時間單位為秒
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TARGET_LUFS = -16.0
TOLERANCE_LU = 0.5
# 限制器上限（樣本峰值），留一點空間給 true peak
PEAK_LIMIT_DB = -2.0
MAX_PASSES = 4
SAMPLE_RATE = 48000
# 清晰化之前先把音量拉到這裡，壓縮器門檻以此為準
PRE_GAIN_LUFS = -23.0

# 人聲清晰化：去嗡聲、去悶、補咬字、拉平音量、去齒音
CLARITY_FILTER = (
    "highpass=f=90,"
    "equalizer=f=300:t=q:w=1:g=-2,"
    "equalizer=f=3000:t=q:w=0.8:g=5,"
    "highshelf=f=6000:g=3,"
    "acompressor=threshold=-24dB:ratio=3:attack=5:release=120:makeup=1,"
    "deesser"
)
# 選用的頻域降噪，接在高通之後。nf 是絕對音量（dBFS），一定要在拉音量之後做，
# 否則小聲的錄音整段人聲都會被當成噪音；tn=1 讓它自己追蹤噪音底
DENOISE_FILTER = "afftdn=nf=-60:tn=1"


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def measure_lufs(path: Path) -> float:
    """量測整合響度（EBU R128，LUFS）。"""
    proc = run_ffmpeg(["-i", str(path), "-af", "ebur128", "-f", "null", "-"])
    summary = proc.stderr[proc.stderr.rindex("Summary:") :]
    for line in summary.splitlines():
        line = line.strip()
        if line.startswith("I:"):
            return float(line.split()[1])
    raise RuntimeError("ebur128 沒有回報整合響度")


def normalize(
    src: Path, dst: Path, denoise: bool = False, clarity: bool = True
) -> tuple[float, float]:
    """轉 48 kHz 單聲道、清晰化，再把響度調到 TARGET_LUFS。

    不用 loudnorm：短台詞需要的增益常讓峰值超標，loudnorm 會退回
    dynamic 模式，而 dynamic 模式在幾秒長的音檔上明顯拉不到目標。
    這裡改用線性增益加限制器，量測後補差值，直到誤差在容許範圍內。
    回傳（原始輸入響度，輸出響度）。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        mono = Path(tmp) / "mono.wav"
        clean = Path(tmp) / "clean.wav"
        to_f32 = ["-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_f32le"]
        run_ffmpeg(["-i", str(src), *to_f32, str(mono)])
        input_lufs = measure_lufs(mono)
        # 合成語音（clone_voice.py）不做清晰化：EQ 會放大聲碼器的金屬聲
        chain = CLARITY_FILTER if clarity else "anull"
        if denoise:
            chain = chain.replace("highpass=f=90,", f"highpass=f=90,{DENOISE_FILTER},")
        af = f"volume={PRE_GAIN_LUFS - input_lufs:.2f}dB,{chain}"
        run_ffmpeg(["-i", str(mono), "-af", af, *to_f32, str(clean)])
        limit = 10 ** (PEAK_LIMIT_DB / 20)
        gain = TARGET_LUFS - measure_lufs(clean)
        for _ in range(MAX_PASSES):
            af = f"volume={gain:.2f}dB,alimiter=limit={limit:.4f}:level=false"
            run_ffmpeg(["-i", str(clean), "-af", af, "-c:a", "pcm_s16le", str(dst)])
            output_lufs = measure_lufs(dst)
            if abs(output_lufs - TARGET_LUFS) <= TOLERANCE_LU:
                break
            gain += TARGET_LUFS - output_lufs
    return input_lufs, output_lufs


def load_for_whisper(path: Path):
    """用 ffmpeg 解成 16 kHz float32 陣列。

    不走 faster-whisper 內建的 PyAV 解碼：av 15 起移除了它用到的
    open(metadata_errors=...)，而舊版 av 在新 Python 上沒有 wheel。
    """
    import numpy as np

    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-f",
            "f32le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32)


# 語音分段：先估背景噪音（短時能量的低百分位），比它高 SPEECH_ABOVE_FLOOR_DB 才算有聲。
# 用相對門檻，因為清晰化會把停頓的音量一起拉高，固定的 -40 dB 會找不到任何停頓
FRAME_S = 0.02
SPEECH_ABOVE_FLOOR_DB = 10.0
MIN_PAUSE_S = 0.3
MIN_CHUNK_S = 0.15
CHUNK_PAD_S = 0.1
# 聽寫的窗：只在長停頓切開（通常是句與句之間、重唸前的停頓），讓 Whisper 有足夠上下文；
# 太短的段單獨聽寫容易聽錯（"trophy in the glass case" 變成 "Trust me is let's kiss"）
WINDOW_PAUSE_S = 0.8
# 段內字與字的停頓超過這個長度也切開
WORD_GAP_S = 0.35
WINDOW_MAX_S = 20.0


def speech_chunks(audio, sr: int = 16000) -> list[tuple[float, float]]:
    """以停頓切出有聲段（秒）。"""
    import numpy as np

    hop = int(FRAME_S * sr)
    n = len(audio) // hop
    if n == 0:
        return []
    frames = audio[: n * hop].reshape(n, hop)
    db = 10 * np.log10(np.mean(frames**2, axis=1) + 1e-12)
    floor = np.percentile(db, 10)
    voiced = db > floor + SPEECH_ABOVE_FLOOR_DB
    chunks: list[list[float]] = []
    for i, v in enumerate(voiced):
        if not v:
            continue
        t = i * FRAME_S
        if chunks and t - chunks[-1][1] < MIN_PAUSE_S:
            chunks[-1][1] = t + FRAME_S
        else:
            chunks.append([t, t + FRAME_S])
    return [(a, b) for a, b in chunks if b - a >= MIN_CHUNK_S]


def transcribe(path: Path, model_size: str, language: str) -> dict:
    """分窗聽寫，輸出逐字時間戳與細分段。

    整檔一次聽寫時，Whisper 會把重唸、卡住的字（"you should help, you should, oh, Sam,
    you should have asked"）併成一次，切句時就看不出重複。改成在長停頓處分窗、每窗
    分開聽寫，重唸會照實出現。align_lines.py 用較細的段（0.3 秒停頓）當對齊單位，
    每個字依時間歸到它所在的段。
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    audio = load_for_whisper(path)
    sr = 16000
    pieces = speech_chunks(audio, sr)

    windows: list[list[float]] = []
    for a, b in pieces:
        if (
            windows
            and a - windows[-1][1] < WINDOW_PAUSE_S
            and b - windows[-1][0] <= WINDOW_MAX_S
        ):
            windows[-1][1] = b
        else:
            windows.append([a, b])

    words = []
    for a, b in windows:
        lo = max(0.0, a - CHUNK_PAD_S)
        hi = min(len(audio) / sr, b + CHUNK_PAD_S)
        segments, _ = model.transcribe(
            audio[int(lo * sr) : int(hi * sr)],
            language=language,
            word_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        for seg in segments:
            # 太像靜音的段落常是 Whisper 捏造的（例如呼吸聲變成 "Thank you."）
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                continue
            for w in seg.words or []:
                words.append(
                    {
                        "word": w.word.strip(),
                        "start": round(lo + w.start, 3),
                        "end": round(lo + w.end, 3),
                        "probability": round(w.probability, 3),
                    }
                )

    # 每個字歸到它所在（或最近）的細分段
    chunks = [
        {"start": round(a, 3), "end": round(b, 3), "words": []} for a, b in pieces
    ]
    for k, w in enumerate(words):
        # 用字尾時間：Whisper 的字首常黏在前一個字的結尾，字尾比較準
        mid = w["end"] - 0.05
        best = min(
            range(len(chunks)),
            key=lambda c: (
                0.0
                if chunks[c]["start"] <= mid <= chunks[c]["end"]
                else min(abs(mid - chunks[c]["start"]), abs(mid - chunks[c]["end"]))
            ),
        )
        chunks[best]["words"].append(k)
    # 段內再依句尾標點（. ? !）與字間停頓細分：兩句之間停頓太短時，仍能分給不同台詞
    out_chunks = []
    for c in chunks:
        if not c["words"]:
            continue
        ks = sorted(c["words"])
        start, first = c["start"], ks[0]
        for k in ks:
            ends_sentence = words[k]["word"].rstrip("\"'").endswith((".", "?", "!"))
            # Whisper 有時不標句號（"answer thank you"），字與字之間的停頓也當分界
            gap = k < ks[-1] and words[k + 1]["start"] - words[k]["end"] >= WORD_GAP_S
            if k == ks[-1] or ends_sentence or gap:
                end = (
                    c["end"]
                    if k == ks[-1]
                    else round((words[k]["end"] + words[k + 1]["start"]) / 2, 3)
                )
                out_chunks.append(
                    {
                        "start": start,
                        "end": end,
                        "first_word": first,
                        "last_word": k,
                        "text": " ".join(w["word"] for w in words[first : k + 1]),
                    }
                )
                start, first = end, k + 1
    return {
        "language": language,
        "duration": round(len(audio) / sr, 3),
        "text": " ".join(w["word"] for w in words),
        "words": words,
        "chunks": out_chunks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input", type=Path, help="原始音檔（任何 ffmpeg 能讀的格式）")
    parser.add_argument(
        "-o", "--output", type=Path, help="輸出 WAV，預設為輸入檔名加 .prep.wav"
    )
    parser.add_argument(
        "--json", type=Path, help="輸出時間戳 JSON，預設與輸出 WAV 同名"
    )
    parser.add_argument(
        "--model",
        default="large-v3-turbo",
        help="faster-whisper 模型（預設 large-v3-turbo；small 較快但較常聽錯）",
    )
    parser.add_argument(
        "--denoise", action="store_true", help="加頻域降噪，錄音環境吵雜時再開"
    )
    parser.add_argument(
        "--no-clarity",
        action="store_true",
        help="不做 EQ、壓縮、去齒音，只調響度（給合成語音用）",
    )
    parser.add_argument("--language", default="en", help="語言代碼（預設 en）")
    args = parser.parse_args()

    src: Path = args.input
    if not src.is_file():
        print(f"找不到輸入檔：{src}", file=sys.stderr)
        return 1
    out: Path = args.output or src.with_suffix(".prep.wav")
    if out.resolve() == src.resolve():
        print("輸出檔不能覆蓋輸入檔", file=sys.stderr)
        return 1
    json_out: Path = args.json or out.with_suffix(".json")

    input_lufs, lufs = normalize(
        src, out, denoise=args.denoise, clarity=not args.no_clarity
    )
    print(
        f"清晰化與響度：{src} -> {out}（輸入 {input_lufs:.1f} LUFS，輸出 {lufs:.1f} LUFS）"
    )

    result = transcribe(out, args.model, args.language)
    result = {
        "audio": out.name,
        "sample_rate": SAMPLE_RATE,
        "loudness_lufs": lufs,
        "model": f"faster-whisper/{args.model}",
        **result,
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"時間戳：{json_out}（{len(result['words'])} 個字）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
