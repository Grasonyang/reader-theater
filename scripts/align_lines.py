# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""把一場戲的錄音切成一句一句，對回劇本。

用法：
    uv run scripts/align_lines.py <劇本.json> <場次 id> <prep_audio 輸出的 wav>
                                  [--out <輸出資料夾>] [--report <報告.md>]

輸入的 wav 旁邊要有 prep_audio.py 產生的同名 .json（逐段聽寫的逐字時間戳與分段）。

做法：
    - prep_audio.py 在停頓處把錄音切成一段段（chunk），每段分開聽寫
    - 每句劇本對應一串連續的段：以字母層級比對（"attack" 也能對上 "a duck"），
      多出來的段、少掉的字都扣分；整場用動態規劃一次決定，句子順序不變，
      沒用到的段（重唸、說錯重來、開場自報場次）直接略過
    - 分數相同時取較晚的段，也就是重唸時保留最後一次
    - 段內緊接著重複的字（"glass glass case"）剪掉其中一個，接縫做短淡入淡出
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
# 一句最多跨幾段（句中停頓、逗號都會切段）
MAX_SPAN = 8
# 分數低於這句字母數的這個比例，視為沒唸
MIN_CHAR_RATIO = 0.35
# 同分時偏好較晚的段（每往後一段加這麼多），用來保留最後一次重唸
LATER_BONUS = 1e-3
SPLICE_FADE = 0.015

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


def range_score(line: str, heard: str) -> float:
    """字母層級的相符程度：對上的字母數，扣掉多出來與少掉的一半。"""
    if not heard:
        return float("-inf")
    sm = difflib.SequenceMatcher(None, line, heard, autojunk=False)
    m = sum(block.size for block in sm.get_matching_blocks())
    return m - 0.5 * (len(heard) - m) - 0.5 * (len(line) - m)


def assign(
    lines: list[list[str]], chunks: list[list[str]]
) -> list[tuple[int, int] | None]:
    """每句對應到哪一串連續的段 [a, b)；沒唸的句子是 None。"""
    n_lines, n_chunks = len(lines), len(chunks)
    line_chars = ["".join(t) for t in lines]
    chunk_chars = ["".join(t) for t in chunks]
    neg = float("-inf")
    dp = [[neg] * (n_chunks + 1) for _ in range(n_lines + 1)]
    back: list[list[tuple | None]] = [
        [None] * (n_chunks + 1) for _ in range(n_lines + 1)
    ]
    dp[0][0] = 0.0

    def relax(i, j, value, how):
        if value > dp[i][j]:
            dp[i][j], back[i][j] = value, how

    for i in range(n_lines + 1):
        for j in range(n_chunks + 1):
            cur = dp[i][j]
            if cur == neg:
                continue
            if j < n_chunks:
                relax(i, j + 1, cur, ("skip", i, j))
            if i == n_lines:
                continue
            relax(i + 1, j, cur, ("missing", i, j))
            floor = MIN_CHAR_RATIO * len(line_chars[i])
            for k in range(j + 1, min(n_chunks, j + MAX_SPAN) + 1):
                score = range_score(line_chars[i], "".join(chunk_chars[j:k]))
                if score >= floor:
                    relax(i + 1, k, cur + score + LATER_BONUS * j, ("take", i, j, k))

    end = max(range(n_chunks + 1), key=lambda j: dp[n_lines][j])
    result: list[tuple[int, int] | None] = [None] * n_lines
    i, j = n_lines, end
    while back[i][j]:
        how = back[i][j]
        if how[0] == "take":
            result[how[1]] = (how[2], how[3])
        i, j = how[1], how[2]
    return result


def word_times(
    n_tokens: int, pairs, words: list[dict], bounds: tuple[float, float]
) -> list[tuple[float, float]]:
    """每個劇本字的 (start, end)；沒對上的字用前後內插。

    句首、句尾沒對上的字，分配到 bounds（這句的切點）與最近一個對上的字之間。
    """
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
        t0 = times[prev][1] if prev is not None else bounds[0]
        t1 = times[nxt][0] if nxt is not None else bounds[1]
        # 同一段空隙裡的字平均分配
        gap_lo = prev if prev is not None else -1
        gap_hi = nxt if nxt is not None else n_tokens
        k, total = i - gap_lo, gap_hi - gap_lo
        step = (t1 - t0) / total
        times[i] = (t0 + step * (k - 0.5), t0 + step * (k + 0.5))
    return times  # type: ignore[return-value]


def to_line_time(t: float, start: float, removed: list[tuple[float, float]]) -> float:
    """整場時間換成切好的這句裡的時間（扣掉句首與剪掉的部分）。"""
    gone = sum(max(0.0, min(t, r1) - r0) for r0, r1 in removed if t > r0)
    return max(0.0, t - start - gone)


def cut(src: Path, dst: Path, keep: list[tuple[float, float]]) -> None:
    """切出 keep 這幾段接起來；多段時每個接縫做短淡入淡出。"""
    if len(keep) == 1:
        (start, end), parts = keep[0], None
        args = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src)]
    else:
        parts = []
        for k, (start, end) in enumerate(keep):
            fade_out = max(0.0, end - start - SPLICE_FADE)
            parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={SPLICE_FADE},afade=t=out:st={fade_out:.3f}:d={SPLICE_FADE}[p{k}]"
            )
        labels = "".join(f"[p{k}]" for k in range(len(keep)))
        graph = ";".join(parts) + f";{labels}concat=n={len(keep)}:v=0:a=1"
        args = ["-i", str(src), "-filter_complex", graph]
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args,
         "-c:a", "pcm_s16le", str(dst)],
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
    chunks = stamps.get("chunks")
    if chunks is None:
        print(
            "時間戳 JSON 沒有分段資料，請用新版 prep_audio.py 重新處理", file=sys.stderr
        )
        return 1
    heard = [norm(w["word"]) for w in words]
    out_dir = args.out or args.audio.parent / "lines"
    out_dir.mkdir(parents=True, exist_ok=True)

    display = [ln["text"].split() for ln in scene["lines"]]
    tokens = [[t for t in (norm(w) for w in d)] for d in display]
    chunk_tokens = [
        [t for t in heard[c["first_word"] : c["last_word"] + 1] if t] for c in chunks
    ]
    ranges = assign(tokens, chunk_tokens)
    used = {k for r in ranges if r for k in range(*r)}

    report = [f"## {scene['id']} {scene['title']}", ""]
    for ln, disp, toks, rng in zip(scene["lines"], display, tokens, ranges):
        if not rng:
            report.append(
                f"- **{ln['id']}**（{ln['speaker']}）：沒找到，可能沒唸或聽不出來"
            )
            ln.pop("audio", None)
            ln.pop("timestamps", None)
            continue
        a, b = rng
        w_lo, w_hi = chunks[a]["first_word"], chunks[b - 1]["last_word"]
        # 範圍已由分段決定，段內的字全部納入比對（多出來的字算插入）
        _, back = align(toks, heard[w_lo : w_hi + 1])
        pairs = [
            (i, None if k is None else w_lo + k)
            for i, k in traceback(back, len(toks), w_hi + 1 - w_lo)
        ]

        # 切點：段的前後留一點空間，但不超過與相鄰段（不論有沒有用到）之間的中點
        start = chunks[a]["start"] - PAD_BEFORE
        end = chunks[b - 1]["end"] + PAD_AFTER
        if a > 0:
            start = max(start, (chunks[a - 1]["end"] + chunks[a]["start"]) / 2)
        if b < len(chunks):
            end = min(end, (chunks[b - 1]["end"] + chunks[b]["start"]) / 2)
        start, end = max(0.0, start), min(end, stamps["duration"])

        # 段內緊接著重複的字：剪掉沒對上劇本的那一個
        matched = {k for _, k in pairs if k is not None}
        removed: list[tuple[float, float]] = []
        spliced = []
        for k in range(w_lo, w_hi + 1):
            if k in matched or not heard[k]:
                continue
            # 只剪「重複了一個已對上劇本的字」；劇本本身就重複的字（Squeak. Squeak.）
            # 會各自對上，不會被剪
            nxt_same = k < w_hi and k + 1 in matched and similar(heard[k], heard[k + 1])
            prv_same = k > w_lo and k - 1 in matched and similar(heard[k], heard[k - 1])
            if nxt_same or prv_same:
                cut_to = words[k + 1]["start"] if k < w_hi else words[k]["end"]
                removed.append((words[k]["start"], cut_to))
                spliced.append(words[k]["word"])
        keep, cursor = [], start
        for r0, r1 in removed:
            if r0 > cursor:
                keep.append((cursor, r0))
            cursor = max(cursor, r1)
        keep.append((cursor, end))

        wav = out_dir / f"{ln['id']}.wav"
        cut(args.audio, wav, keep)
        times = word_times(
            len(toks), pairs, words, (chunks[a]["start"], chunks[b - 1]["end"])
        )
        issues = []
        for i, k in pairs:
            if k is None:
                issues.append(f"「{disp[i]}」沒聽到")
            elif not similar(toks[i], heard[k]):
                issues.append(f"「{disp[i]}」聽成「{words[k]['word']}」")
        duration = sum(e - s for s, e in keep)
        line_json = {
            "audio": wav.name,
            "sample_rate": stamps["sample_rate"],
            "source": args.audio.name,
            "offset": round(start, 3),
            "duration": round(duration, 3),
            "removed": [[round(r0, 3), round(r1, 3)] for r0, r1 in removed],
            "text": ln["text"],
            # 念錯或漏念的字，clone_voice.py 挑參考音檔時用
            "issues": issues,
            "words": [
                {
                    "word": w,
                    "start": round(to_line_time(t0, start, removed), 3),
                    "end": round(to_line_time(t1, start, removed), 3),
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

        notes = issues + [f"剪掉重複的「{w}」" for w in spliced]
        mark = "；".join(notes) if notes else "OK"
        report.append(f"- **{ln['id']}**（{ln['speaker']}，{duration:.1f} 秒）：{mark}")

    skipped = [c["text"] for k, c in enumerate(chunks) if k not in used]
    if skipped:
        report += ["", "略過的段（重唸、說錯重來或不在劇本裡）："]
        report += [f"- {t}" for t in skipped]

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
