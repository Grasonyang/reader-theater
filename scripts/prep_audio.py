# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "faster-whisper>=1.1",
#     "numpy",
# ]
# ///
"""台詞音訊前處理：降噪、響度統一、逐字時間戳。

用法：
    uv run scripts/prep_audio.py <輸入音檔> [-o 輸出.wav] [--json 輸出.json]

輸出：
    - 48 kHz、單聲道、16-bit PCM WAV，響度 -16 LUFS（EBU R128，誤差 ±0.5 LU）
    - 逐字時間戳 JSON（faster-whisper，CPU、small 模型），時間單位為秒
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

# 高通去掉低頻隆隆聲，afftdn 做頻域降噪（nf 為估計的噪音底，dB）
DENOISE_FILTER = "highpass=f=80,afftdn=nf=-25"


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


def normalize(src: Path, dst: Path) -> tuple[float, float]:
    """降噪、轉 48 kHz 單聲道，再把響度調到 TARGET_LUFS。

    不用 loudnorm：短台詞需要的增益常讓峰值超標，loudnorm 會退回
    dynamic 模式，而 dynamic 模式在幾秒長的音檔上明顯拉不到目標。
    這裡改用線性增益加限制器，量測後補差值，直到誤差在容許範圍內。
    回傳（降噪後的輸入響度，輸出響度）。
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean.wav"
        run_ffmpeg(
            [
                "-i",
                str(src),
                "-af",
                DENOISE_FILTER,
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                "1",
                "-c:a",
                "pcm_f32le",
                str(clean),
            ]
        )
        input_lufs = measure_lufs(clean)
        limit = 10 ** (PEAK_LIMIT_DB / 20)
        gain = TARGET_LUFS - input_lufs
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


def transcribe(path: Path, model_size: str, language: str) -> dict:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        load_for_whisper(path), language=language, word_timestamps=True
    )
    words = []
    texts = []
    for seg in segments:
        texts.append(seg.text.strip())
        for w in seg.words or []:
            words.append(
                {
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 3),
                }
            )
    return {
        "language": info.language,
        "duration": round(info.duration, 3),
        "text": " ".join(texts),
        "words": words,
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
        "--model", default="small", help="faster-whisper 模型大小（預設 small）"
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

    input_lufs, lufs = normalize(src, out)
    print(
        f"降噪與響度：{src} -> {out}（輸入 {input_lufs:.1f} LUFS，輸出 {lufs:.1f} LUFS）"
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
