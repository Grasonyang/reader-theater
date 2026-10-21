# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""打包成可以放上 GitHub Pages 的靜態網站。

用法：
    uv run scripts/build_site.py [--script missing-duck-voices] [--base /reader-theater/] [--out dist]

做的事：
    1. `vite build`（base 設成子路徑）
    2. 把劇本用到的每句音訊轉成 mp3、連同時間戳、角色圖、背景複製進 dist/assets/，
       並寫出路徑改好的劇本 JSON
    3. 漫畫版（comic.html）改名為 index.html 當首頁，3D 版改名為 theater3d.html

之後用 scripts/deploy_pages.sh 推到 gh-pages 分支。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MP3_QUALITY = "3"  # libmp3lame VBR，約 150 kbps


def copy_into(src: Path, out: Path) -> Path:
    dst = out / src
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def to_mp3(src: Path, out: Path) -> Path:
    dst = (out / src).with_suffix(".mp3")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
         "-c:a", "libmp3lame", "-q:a", MP3_QUALITY, str(dst)],
        check=True,
    )  # fmt: skip
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--script", default="missing-duck-voices")
    parser.add_argument("--base", default="/reader-theater/")
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args()
    out: Path = args.out

    script_path = Path("assets/scripts") / f"{args.script}.json"
    if not script_path.is_file():
        print(
            f"找不到 {script_path}，先跑 scripts/prep_scenes.sh 與 role_voices.py",
            file=sys.stderr,
        )
        return 1

    shutil.rmtree(out, ignore_errors=True)
    subprocess.run(
        ["npx", "vite", "build"], check=True, env={**os.environ, "BASE_PATH": args.base}
    )

    script = json.loads(script_path.read_text(encoding="utf-8"))
    count = 0
    for scene in script["scenes"]:
        for line in scene["lines"]:
            if "audio" not in line:
                continue
            mp3 = to_mp3(Path(line["audio"]), out)
            line["audio"] = mp3.relative_to(out).as_posix()
            copy_into(Path(line["timestamps"]), out)
            count += 1
    for c in script["characters"]:
        if c.get("comic", {}).get("image"):
            copy_into(Path(c["comic"]["image"]), out)
    for src in (script.get("backgrounds") or {}).values():
        copy_into(Path(src), out)
    dst_script = out / script_path
    dst_script.parent.mkdir(parents=True, exist_ok=True)
    dst_script.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    (out / "index.html").rename(out / "theater3d.html")
    (out / "comic.html").rename(out / "index.html")
    (out / ".nojekyll").touch()
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(f"{count} 句音訊，網站共 {size:.1f} MB → {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
