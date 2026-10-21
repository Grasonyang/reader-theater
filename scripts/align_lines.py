# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把一場戲的錄音切成一句一句，對回劇本。

用法：
    uv run scripts/align_lines.py <劇本.json> <場次 id> <prep_audio 輸出的 wav>
                                  [--out <輸出資料夾>] [--report <報告.md>]

輸入的 wav 旁邊要有 prep_audio.py 產生的同名 .json（逐字時間戳）。

做法：
    - 每一句劇本跟逐字結果做半全域對齊（劇本整句都要對上，錄音前後可以多出
      別的字），拼法相近的字也算對上
    - 同一句唸了好幾次（重唸）時，取最後一次
    - 對不到的劇本字，時間用前後的字內插

輸出（每一句）：
    <輸出資料夾>/<台詞 id>.wav   切好的音檔
    <輸出資料夾>/<台詞 id>.json  逐字時間戳；字用劇本原文，時間用實際錄音，
                                 格式與 prep_audio.py 相同
並把 audio、timestamps 路徑寫回劇本 JSON，另輸出念錯、漏念的報告。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

MATCH, MISMATCH, GAP = 2.0, -1.0, -1.0
# 字的拼法相似度到這裡就當成同一個字（例如 trophy / trophies）
SIMILAR = 0.8
# 分數在最佳值的這個比例以內，都算同一句的候選（用來挑最後一次重唸）
RETAKE_MARGIN = 0.85
# 分數低於滿分的這個比例，視為沒唸或聽不出來
MIN_SCORE_RATIO = 0.3
PAD_BEFORE, PAD_AFTER = 0.12, 0.25

NUMBERS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
    "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten",
}  # fmt: skip


def norm(word: str) -> str:
    w = re.sub(r"[^a-z0-9']", "", word.lower()).strip("'")
    return NUMBERS.get(w, w)


def similar(a: str, b: str) -> bool:
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR


def align(line: list[str], heard: list[str]):
    """半全域對齊：line 全部對上，heard 前後免費略過。

    回傳每個結束位置的分數，以及用來回溯的矩陣。
    """
    n, m = len(line), len(heard)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0] + GAP
        back[i][0] = "up"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = score[i - 1][j - 1] + (
                MATCH if similar(line[i - 1], heard[j - 1]) else MISMATCH
            )
            up = score[i - 1][j] + GAP  # 劇本的字沒唸
            left = score[i][j - 1] + GAP  # 多唸的字
            score[i][j], back[i][j] = max((diag, "diag"), (up, "up"), (left, "left"))
    return score, back


def traceback(back, n: int, j_end: int) -> list[tuple[int, int | None]]:
    """回傳 (劇本字 index, 錄音字 index 或 None) 的配對。"""
    pairs = []
    i, j = n, j_end
    while i > 0:
        step = back[i][j]
        if step == "diag":
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif step == "up":
            pairs.append((i - 1, None))
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def best_match(line: list[str], heard: list[str], lo: int, hi: int, latest: bool):
    """在 heard[lo:hi] 找這句的位置。latest=True 時在接近最佳分數的候選中取最後一個。"""
    window = heard[lo:hi]
    if not window:
        return None
    score, back = align(line, window)
    ends = [(score[len(line)][j], j) for j in range(1, len(window) + 1)]
    top = max(s for s, _ in ends)
    if top < MIN_SCORE_RATIO * MATCH * len(line):
        return None
    if latest:
        floor = top * RETAKE_MARGIN if top > 0 else top
        j_end = max(j for s, j in ends if s >= floor)
    else:
        j_end = next(j for s, j in ends if s == top)
    pairs = traceback(back, len(line), j_end)
    matched = [k for _, k in pairs if k is not None]
    if not matched:
        return None
    return {
        "score": score[len(line)][j_end],
        "start": lo + matched[0],
        "end": lo + matched[-1],
        "pairs": [(a, None if b is None else lo + b) for a, b in pairs],
    }


def locate(lines: list[list[str]], heard: list[str]) -> list[dict | None]:
    # 第一輪：依序取最早的最佳位置，得到不交錯的順序
    first: list[dict | None] = []
    pos = 0
    for toks in lines:
        hit = best_match(toks, heard, pos, len(heard), latest=False)
        first.append(hit)
        if hit:
            pos = hit["end"] + 1
    # 第二輪：每句在「上一句結束」到「下一句開始」之間取最後一次重唸
    result: list[dict | None] = []
    lo = 0
    for i, toks in enumerate(lines):
        nxt = next((h for h in first[i + 1 :] if h), None)
        hi = nxt["start"] if nxt else len(heard)
        hit = best_match(toks, heard, lo, hi, latest=True) or first[i]
        result.append(hit)
        if hit:
            lo = hit["end"] + 1
    return result


def word_times(n_tokens: int, pairs, words: list[dict]) -> list[tuple[float, float]]:
    """每個劇本字的 (start, end)；沒對上的字用前後內插。"""
    times: list[tuple[float, float] | None] = [None] * n_tokens
    for a, b in pairs:
        if b is not None:
            times[a] = (words[b]["start"], words[b]["end"])
    known = [i for i, t in enumerate(times) if t]
    for i in range(n_tokens):
        if times[i]:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        t0 = times[prev][1] if prev is not None else times[nxt][0]
        t1 = times[nxt][0] if nxt is not None else times[prev][1]
        # 同一段空隙裡的字平均分配
        gap_lo = prev if prev is not None else -1
        gap_hi = nxt if nxt is not None else n_tokens
        k, total = i - gap_lo, gap_hi - gap_lo
        step = (t1 - t0) / total
        times[i] = (t0 + step * (k - 0.5), t0 + step * (k + 0.5))
    return times  # type: ignore[return-value]


def cut(src: Path, dst: Path, start: float, end: float) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
         "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src), "-c:a", "pcm_s16le", str(dst)],
        check=True,
    )  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("script", type=Path, help="劇本 JSON（docs/script-schema.md）")
    parser.add_argument("scene", help="場次 id，例如 s1")
    parser.add_argument("audio", type=Path, help="prep_audio.py 輸出的整場 wav")
    parser.add_argument("--out", type=Path, help="輸出資料夾，預設為 wav 旁邊的 lines/")
    parser.add_argument(
        "--report", type=Path, help="念錯、漏念的報告（Markdown），預設不輸出"
    )
    args = parser.parse_args()

    script = json.loads(args.script.read_text(encoding="utf-8"))
    scene = next((s for s in script["scenes"] if s["id"] == args.scene), None)
    if scene is None:
        print(f"劇本裡沒有場次 {args.scene}", file=sys.stderr)
        return 1
    stamps = json.loads(args.audio.with_suffix(".json").read_text(encoding="utf-8"))
    words = stamps["words"]
    heard = [norm(w["word"]) for w in words]
    out_dir = args.out or args.audio.parent / "lines"
    out_dir.mkdir(parents=True, exist_ok=True)

    display = [ln["text"].split() for ln in scene["lines"]]
    tokens = [[norm(w) for w in d] for d in display]
    hits = locate(tokens, heard)

    # 每句的切點：前後留一點空間，但不超過與鄰句之間的中點
    spans = []
    for i, hit in enumerate(hits):
        if not hit:
            spans.append(None)
            continue
        start = words[hit["start"]]["start"] - PAD_BEFORE
        end = words[hit["end"]]["end"] + PAD_AFTER
        prev = next((h for h in reversed(hits[:i]) if h), None)
        nxt = next((h for h in hits[i + 1 :] if h), None)
        if prev:
            start = max(
                start, (words[prev["end"]]["end"] + words[hit["start"]]["start"]) / 2
            )
        if nxt:
            end = min(
                end, (words[hit["end"]]["end"] + words[nxt["start"]]["start"]) / 2
            )
        spans.append((max(0.0, start), min(end, stamps["duration"])))

    report = [f"## {scene['id']} {scene['title']}", ""]
    for ln, disp, toks, hit, span in zip(scene["lines"], display, tokens, hits, spans):
        if not hit:
            report.append(
                f"- **{ln['id']}**（{ln['speaker']}）：沒找到，可能沒唸或聽不出來"
            )
            ln.pop("audio", None)
            ln.pop("timestamps", None)
            continue
        start, end = span
        wav = out_dir / f"{ln['id']}.wav"
        cut(args.audio, wav, start, end)
        times = word_times(len(toks), hit["pairs"], words)
        issues = []
        for a, b in hit["pairs"]:
            if b is None:
                issues.append(f"「{disp[a]}」沒聽到")
            elif not similar(toks[a], heard[b]):
                issues.append(f"「{disp[a]}」聽成「{words[b]['word']}」")
        line_json = {
            "audio": wav.name,
            "sample_rate": stamps["sample_rate"],
            "source": args.audio.name,
            "offset": round(start, 3),
            "duration": round(end - start, 3),
            "text": ln["text"],
            # 念錯或漏念的字，clone_voice.py 挑參考音檔時用
            "issues": issues,
            "words": [
                {
                    "word": w,
                    "start": round(max(0.0, t0 - start), 3),
                    "end": round(max(0.0, t1 - start), 3),
                }
                for w, (t0, t1) in zip(disp, times)
            ],
        }
        json_path = wav.with_suffix(".json")
        json_path.write_text(
            json.dumps(line_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        ln["audio"] = Path(wav).resolve().relative_to(Path.cwd()).as_posix()
        ln["timestamps"] = json_path.resolve().relative_to(Path.cwd()).as_posix()

        mark = "；".join(issues) if issues else "OK"
        report.append(
            f"- **{ln['id']}**（{ln['speaker']}，{end - start:.1f} 秒）：{mark}"
        )

    args.script.write_text(
        json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    text = "\n".join(report) + "\n"
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
