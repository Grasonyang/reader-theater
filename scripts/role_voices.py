# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""一人分飾多角：依角色設定改變每句台詞的音高、共振峰與語速。

用法：
    uv run scripts/role_voices.py <劇本.json> [--suffix voices]

劇本 characters[].voice 設定每個角色的變聲（沒設定就不變）：
    "voice": { "pitch": 7, "formant": 3, "tempo": 1.05 }
    - pitch：音高，半音。+12 是高八度
    - formant：共振峰，半音。決定聲音聽起來像大人或小孩、男或女；
      只升音高不動共振峰，聽起來像用假音
    - tempo：語速倍率。1.1 是快 10%，0.9 是慢 10%；不改音高

輸出：
    - 每句變聲後的 wav，放在原音檔旁的 <suffix>/ 資料夾
    - 新劇本 <劇本名稱>-<suffix>.json，audio 指向變聲後的檔案；
      tempo 不是 1 時，逐字時間戳依倍率縮放，另存在同一個資料夾
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SAMPLE_RATE = 48000
# 變聲後的峰值上限（線性），避免升調後破音
PEAK_LIMIT = 0.89


def voice_filter(pitch: float, formant: float, tempo: float = 1.0) -> str:
    """音高、共振峰、語速分開調。

    asetrate 會讓音高、共振峰、速度一起變 r 倍；接著用 rubberband 把速度
    調成想要的語速（tempo/r），並在保留共振峰的模式下補上剩下的音高。
    """
    r = 2 ** (formant / 12)
    rest = 2 ** ((pitch - formant) / 12)
    return (
        f"asetrate={SAMPLE_RATE * r:.2f},aresample={SAMPLE_RATE},"
        # detector=soft、transients=mixed：給人聲用的設定，子音不會被當成打擊音處理而變得刺耳
        f"rubberband=tempo={tempo / r:.6f}:pitch={rest:.6f}:formant=preserved"
        ":transients=mixed:detector=soft,"
        f"alimiter=limit={PEAK_LIMIT}:level=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("script", type=Path, help="已對齊的劇本 JSON（台詞要有 audio）")
    parser.add_argument(
        "--suffix", default="voices", help="輸出資料夾與新劇本的後綴（預設 voices）"
    )
    args = parser.parse_args()

    script = json.loads(args.script.read_text(encoding="utf-8"))
    voices = {c["id"]: c.get("voice") or {} for c in script["characters"]}
    count = 0
    for scene in script["scenes"]:
        for line in scene["lines"]:
            if "audio" not in line:
                continue
            voice = voices.get(line["speaker"], {})
            pitch, formant = voice.get("pitch", 0), voice.get("formant", 0)
            tempo = voice.get("tempo", 1.0)
            if not pitch and not formant and tempo == 1.0:
                continue
            src = Path(line["audio"])
            dst = src.parent / args.suffix / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
                 "-af", voice_filter(pitch, formant, tempo), "-ar", str(SAMPLE_RATE), "-ac", "1",
                 "-c:a", "pcm_s16le", str(dst)],
                check=True,
            )  # fmt: skip
            line["audio"] = dst.as_posix()
            if tempo != 1.0:
                stamps = json.loads(
                    Path(line["timestamps"]).read_text(encoding="utf-8")
                )
                stamps["duration"] = round(stamps["duration"] / tempo, 3)
                for w in stamps["words"]:
                    w["start"] = round(w["start"] / tempo, 3)
                    w["end"] = round(w["end"] / tempo, 3)
                stamps_dst = dst.with_suffix(".json")
                stamps_dst.write_text(
                    json.dumps(stamps, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                line["timestamps"] = stamps_dst.as_posix()
            count += 1

    out = args.script.with_name(f"{args.script.stem}-{args.suffix}.json")
    out.write_text(
        json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"變聲 {count} 句，新劇本：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
