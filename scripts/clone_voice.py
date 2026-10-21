# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#     "f5-tts>=1.1",
#     "faster-whisper>=1.1",
#     "soundfile",
# ]
# ///
"""用你自己的音色，依劇本把每句台詞合成出來（F5-TTS，零樣本聲音複製）。

建議在有 NVIDIA GPU 的機器上跑（例如 DGX Spark）；CPU 也能跑，但一句要一兩分鐘。

用法：
    uv run scripts/clone_voice.py <已對齊的劇本.json> [--suffix clone] [--only 台詞id,...]

自我檢查：
    每句合成後用 Whisper 聽寫，跟劇本逐字比對。F5-TTS 偶爾會漏字（"Mia! Mia!" 只唸一次）
    或在句首冒出氣音雜訊（"It was" 被聽成 "Shit was"），不一致就換一個亂數種子重合成，
    最多 --attempts 次，保留最接近劇本的一次。仍不一致的句子列在 clone_report.md。

參考音檔：
    每個角色從自己已對齊的台詞裡挑一句當參考，這樣你替每個角色做的語氣也會被複製。
    挑選條件：4 到 11 秒（F5-TTS 會把超過 12 秒的參考截短，截短後參考文字就對不上）、
    念錯的字越少越好、越長越好。挑不到的角色改用旁白（第一個角色）的參考。

輸出（<新名稱> = <劇本名稱>-<suffix>，例如 missing-duck-clone）：
    assets/scripts/<新名稱>.json                     新劇本
    assets/audio/voice/<新名稱>/raw/scene<N>.flac    每場合成結果接起來，句間停 0.8 秒
    接著跑 scripts/prep_scenes.sh <新名稱>，得到每句的 wav 與時間戳。
    新劇本與 raw/ 可以進版控，其他機器 git pull 後跑 prep_scenes.sh 就能重建，
    不必再合成。網頁用 ?script=<新名稱> 演出。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REF_MIN_S, REF_MAX_S = 4.0, 11.0
GAP_S = 0.8
SEED = 1234
VERIFY_MODEL = "large-v3-turbo"

# 與 align_lines.py 用同一套字詞正規化
sys.path.insert(0, str(Path(__file__).parent))
from align_lines import norm


def tokens(text: str) -> list[str]:
    return [t for t in (norm(w) for w in text.split()) if t]


class Verifier:
    """用 Whisper 聽寫合成結果，跟劇本逐字比對。"""

    def __init__(self, sample_rate: int):
        import ctranslate2
        from faster_whisper import WhisperModel

        cuda = ctranslate2.get_cuda_device_count() > 0
        self.model = WhisperModel(
            VERIFY_MODEL,
            device="cuda" if cuda else "cpu",
            compute_type="int8_float16" if cuda else "int8",
        )
        self.sample_rate = sample_rate

    def check(self, wav, text: str) -> tuple[float, str]:
        """回傳（與劇本的相似度，聽到的文字）；1.0 代表逐字相同。"""
        import difflib

        import librosa
        import numpy as np

        audio = librosa.resample(
            np.asarray(wav, dtype=np.float32), orig_sr=self.sample_rate, target_sr=16000
        )
        segments, _ = self.model.transcribe(
            audio, language="en", vad_filter=True, condition_on_previous_text=False
        )
        heard = " ".join(seg.text.strip() for seg in segments)
        want, got = tokens(text), tokens(heard)
        ratio = 1.0 if want == got else difflib.SequenceMatcher(None, want, got).ratio()
        return ratio, heard


def pick_references(script: dict) -> dict[str, dict]:
    """每個角色挑一句參考：念錯越少越好，其次越長越好。"""
    best: dict[str, tuple] = {}
    for scene in script["scenes"]:
        for line in scene["lines"]:
            if "timestamps" not in line:
                continue
            stamps = json.loads(Path(line["timestamps"]).read_text(encoding="utf-8"))
            dur = stamps["duration"]
            if not REF_MIN_S <= dur <= REF_MAX_S:
                continue
            key = (-len(stamps.get("issues", [])), dur)
            if line["speaker"] not in best or key > best[line["speaker"]][0]:
                best[line["speaker"]] = (
                    key,
                    {"audio": line["audio"], "text": line["text"], "id": line["id"]},
                )
    refs = {sp: v[1] for sp, v in best.items()}
    fallback_id = script["characters"][0]["id"]
    if fallback_id not in refs:
        raise SystemExit(
            f"旁白（{fallback_id}）沒有 {REF_MIN_S:.0f} 到 {REF_MAX_S:.0f} 秒的台詞可當參考"
        )
    for c in script["characters"]:
        refs.setdefault(c["id"], refs[fallback_id])
    return refs


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "script", type=Path, help="已對齊的劇本 JSON（台詞要有 audio、timestamps）"
    )
    parser.add_argument(
        "--suffix", default="clone", help="輸出資料夾與新劇本的後綴（預設 clone）"
    )
    parser.add_argument(
        "--only", help="只合成這些台詞（逗號分隔的 id），用來試跑；不做後續對齊"
    )
    parser.add_argument(
        "--model", default="F5TTS_v1_Base", help="F5-TTS 模型（預設 F5TTS_v1_Base）"
    )
    parser.add_argument(
        "--nfe", type=int, default=32, help="取樣步數，越大越細但越慢（預設 32）"
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=5,
        help="聽寫跟劇本不一致時，最多合成幾次（預設 5；1 代表不重試）",
    )
    args = parser.parse_args()

    import numpy as np
    import soundfile as sf
    import torch
    from f5_tts.api import F5TTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(
        f"torch {torch.__version__}，裝置：{device}"
        + (f"（{torch.cuda.get_device_name()}）" if device == "cuda" else "")
    )

    script = json.loads(args.script.read_text(encoding="utf-8"))
    refs = pick_references(script)
    for c in script["characters"]:
        r = refs[c["id"]]
        print(f"參考 {c['id']:10s} ← {r['id']}：{r['text']}")

    only = set(args.only.split(",")) if args.only else None
    first_audio = next(
        ln["audio"] for s in script["scenes"] for ln in s["lines"] if "audio" in ln
    )
    # 跟原始錄音同一層：assets/audio/voice/<新名稱>/raw/，與 prep_scenes.sh 的慣例一致
    name = f"{args.script.stem}-{args.suffix}"
    out_dir = Path(first_audio).parents[2] / name
    raw_dir = out_dir / ("trial" if only else "raw")
    raw_dir.mkdir(parents=True, exist_ok=True)

    tts = F5TTS(model=args.model, device=device)
    sr = tts.target_sample_rate
    verifier = Verifier(sr)
    began = time.time()
    produced = []
    imperfect = []
    for scene in script["scenes"]:
        pieces = []
        for line in scene["lines"]:
            if only and line["id"] not in only:
                continue
            ref = refs[line["speaker"]]
            t = time.time()
            best = None
            for attempt in range(max(1, args.attempts)):
                wav, _, _ = tts.infer(
                    ref_file=ref["audio"],
                    ref_text=ref["text"],
                    gen_text=line["text"],
                    nfe_step=args.nfe,
                    seed=SEED + attempt,
                    show_info=lambda *a, **k: None,
                    progress=None,
                )
                score, heard = verifier.check(wav, line["text"])
                if best is None or score > best[0]:
                    best = (score, heard, wav, attempt + 1)
                if score == 1.0:
                    break
            score, heard, wav, tries = best
            mark = "OK" if score == 1.0 else f"相似度 {score:.2f}，聽到：{heard}"
            print(
                f"{line['id']}（{line['speaker']}）{len(wav) / sr:.1f} 秒，"
                f"第 {tries} 次，花 {time.time() - t:.1f} 秒：{mark}"
            )
            if score < 1.0:
                imperfect.append(
                    f"- **{line['id']}**：{line['text']} → 聽到：{heard}（相似度 {score:.2f}）"
                )
            if only:
                sf.write(raw_dir / f"{line['id']}.wav", wav, sr)
                produced.append(raw_dir / f"{line['id']}.wav")
                continue
            pieces += [wav, np.zeros(int(GAP_S * sr), dtype=wav.dtype)]
        if pieces:
            # 場次 s1 存成 scene1；用 FLAC 無損壓縮，檔案約為 wav 的一半，方便進版控
            path = raw_dir / f"scene{scene['id'].removeprefix('s')}.flac"
            sf.write(path, np.concatenate(pieces), sr)
            produced.append(path)
    print(f"合成完成，共花 {time.time() - began:.0f} 秒")
    report = out_dir / "clone_report.md"
    report.write_text(
        "# 合成檢查\n\n"
        + ("\n".join(imperfect) if imperfect else "全部台詞的聽寫都與劇本一致。")
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(imperfect)} 句與劇本不完全一致，見 {report}")
    if only:
        print("試跑輸出：" + "、".join(map(str, produced)))
        return 0

    # 合成結果當成一份新的錄音，走同一套清晰化、時間戳與對齊
    clone_script = args.script.with_name(f"{name}.json")
    for scene in script["scenes"]:
        for line in scene["lines"]:
            line.pop("audio", None)
            line.pop("timestamps", None)
    clone_script.write_text(
        json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run([str(Path(__file__).parent / "prep_scenes.sh"), name], check=True)
    print(f"新劇本：{clone_script}（網頁用 ?script={clone_script.stem}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
