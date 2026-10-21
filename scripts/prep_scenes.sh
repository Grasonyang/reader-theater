#!/usr/bin/env bash
# 從 repo 裡的原始錄音重建一齣劇本的處理結果：每場清晰化、時間戳、切句對回劇本。
# clone 下來或 git pull 之後跑一次，網頁才有台詞音訊可以演。不需要 GPU。
#
# 用法：scripts/prep_scenes.sh [劇本名稱，預設 missing-duck] [傳給 prep_audio.py 的參數...]
#   例：scripts/prep_scenes.sh missing-duck-clone --no-clarity
#   原始錄音：assets/audio/voice/<劇本名稱>/raw/scene<N>.*（N 對應場次 s<N>）
#   劇本：    assets/scripts/<劇本名稱>.json
set -euo pipefail

cd "$(dirname "$0")/.."
name=${1:-missing-duck}
shift || true
script=assets/scripts/$name.json
dir=assets/audio/voice/$name

shopt -s nullglob
raws=("$dir"/raw/scene*.*)
[[ ${#raws[@]} -gt 0 ]] || { echo "找不到 $dir/raw/scene*.*"; exit 1; }
for f in "${raws[@]}"; do
  base=$(basename "$f")
  n=${base#scene}
  n=${n%%.*}
  uv run scripts/prep_audio.py "$f" -o "$dir/scene$n.wav" "$@"
  uv run scripts/align_lines.py "$script" "s$n" "$dir/scene$n.wav" --out "$dir/lines" --report "$dir/report_s$n.md" >/dev/null
  echo "s$n 對齊完成，報告：$dir/report_s$n.md"
done
